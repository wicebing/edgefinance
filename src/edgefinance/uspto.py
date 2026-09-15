"""Offline USPTO Red Book XML/ZIP ingestion, including concatenated XML records."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree as ET

from .core import digest, jsonfile, now, public_url, readjson

DATASETS = "https://data.uspto.gov/bulkdata/datasets"
START = re.compile(rb"<us-patent-(?:grant|application)\b")
END = re.compile(rb"</us-patent-(?:grant|application)\s*>")


def records(stream, max_document_bytes=20 * 1024 * 1024):
    """Bounded streaming split; declarations/DTDs are not executed or downloaded."""
    buf, inside, count = b"", False, 0
    while True:
        block = stream.read(65536)
        buf += block
        while True:
            if not inside:
                start = START.search(buf)
                if not start:
                    if len(buf) > 65536:
                        buf = buf[-65536:]
                    break
                buf, inside = buf[start.start():], True
            end = END.search(buf)
            if not end:
                if len(buf) > max_document_bytes:
                    raise ValueError("Patent exceeds per-document byte limit")
                break
            raw, buf, inside = buf[:end.end()], buf[end.end():], False
            if len(raw) > max_document_bytes:
                raise ValueError("Patent exceeds per-document byte limit")
            count += 1
            yield raw
        if not block:
            if inside:
                raise ValueError("Truncated USPTO XML record")
            if not count:
                raise ValueError("No supported USPTO Red Book XML records")
            break


def parse_patent(raw, source_url, project):
    root = ET.fromstring(raw)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    def text(node):
        return " ".join(" ".join(node.itertext()).split()) if node is not None else ""
    def first(path):
        return text(root.find(path))
    pub = root.find(".//publication-reference/document-id")
    if pub is None:
        raise ValueError("Missing publication identity")
    publication = "".join(text(pub.find(k)) for k in ["country", "doc-number", "kind"])
    when = text(pub.find("date"))
    if not publication.startswith("US") or not re.fullmatch(r"\d{8}", when):
        raise ValueError("Invalid US publication identity/date")
    date = f"{when[:4]}-{when[4:6]}-{when[6:8]}"
    title = first(".//invention-title") or publication
    sections = [f"Publication: {publication}\nPublished: {date}\nTitle: {title}"]
    assignees = list(dict.fromkeys(text(n) for n in root.findall(".//assignees/assignee/addressbook/orgname") if text(n)))
    applicants = list(dict.fromkeys(text(n) for n in root.findall(".//us-applicants/us-applicant/addressbook/orgname") if text(n)))
    if assignees or applicants:
        sections.append("Recorded organizations: " + "; ".join(assignees + applicants))
    for tag in ["abstract", "description", "claims"]:
        sections += [tag.title() + "\n" + text(n) for n in root.findall(".//" + tag) if text(n)]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    entities = [c["ticker"] for c in project.companies if any(norm(a) == norm(b)
        for a in assignees + applicants for b in [c["name"], *c.get("aliases", [])])]
    fulltext = "\n\n".join(sections)
    return {"source_id": "uspto-local", "origin": "uspto", "stable_id": publication,
        "url": public_url(source_url), "title": title, "published_at": date, "text": fulltext,
        "kind": "patent", "coverage": "bulk_xml_text", "entities": entities,
        "topics": project.topic_ids(fulltext), "metadata": {"publication_number": publication,
            "kind_code": text(pub.find("kind")),
            "patent_event": "new_grant" if root.tag == "us-patent-grant" and text(pub.find("kind")) in {"B1", "B2"} else ("other_grant_publication" if root.tag == "us-patent-grant" else "application_publication"),
            "application_date": first(".//application-reference/document-id/date"),
            "assignees": assignees, "applicants": applicants,
            "cpc": [text(n) for n in root.findall(".//classification-cpc")],
            "family_id": None, "legal_status_verified": False,
            "mapping_status": "exact_name_candidate" if entities else "unresolved"}}


def import_bulk(project, path: Path, source_url=DATASETS, max_records=500, topic_only=False, as_of=None):
    path = path.resolve()
    public_url(source_url)
    if max_records < 1:
        raise ValueError("max_records must be positive")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    file_sha = h.hexdigest()
    policy = digest("parser-v2|" + str(topic_only) + str(project.topics) + str(project.companies))[:12]
    journal = project.data / "imports" / f"{file_sha}-{policy}.json"
    state = readjson(journal) if journal.exists() else {"id": file_sha + "-" + policy,
        "file_sha256": file_sha, "file_name": path.name, "source_url": source_url,
        "cursor": 0, "imported": 0, "filtered": 0, "errors": [], "status": "partial", "started_at": now()}
    if state["status"] == "complete":
        return {**state, "new_this_run": 0, "processed_this_run": 0}
    cursor, processed, new = state["cursor"], 0, 0
    store = project.store()
    def sources():
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                members = [i for i in archive.infolist() if i.filename.lower().endswith(".xml")]
                if not members or sum(i.file_size for i in members) > 8 * 1024**3:
                    raise ValueError("Missing XML or archive exceeds 8 GiB uncompressed budget")
                for info in members:
                    name = PurePosixPath(info.filename.replace("\\", "/"))
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError("Invalid ZIP member name")
                    with archive.open(info) as stream:
                        yield from records(stream)
        elif path.suffix.lower() == ".xml":
            with path.open("rb") as stream:
                yield from records(stream)
        else:
            raise ValueError("Expected XML or ZIP")
    try:
        for index, raw in enumerate(sources()):
            if index < cursor:
                continue
            if processed >= max_records:
                break
            doc = parse_patent(raw, source_url, project)
            if as_of and doc["published_at"] > as_of:
                # Keep cursor before a post-cutoff record so the next run can read it.
                state["status"] = "awaiting_publication_date"
                break
            processed += 1
            if topic_only and not doc["topics"] and not doc["entities"]:
                state["filtered"] += 1
            else:
                doc["metadata"].update(archive_sha256=file_sha, archive_record=index)
                _, added = store.add(doc, raw)
                new += int(added)
                state["imported"] += 1
            state["cursor"] = index + 1
            state["status"] = "partial"
            jsonfile(journal, state)
        else:
            state["status"] = "complete"
        state.update(updated_at=now())
        jsonfile(journal, state)
        return {**state, "new_this_run": new, "processed_this_run": processed}
    except Exception as e:
        state["status"] = "failed"
        state["errors"].append({"cursor": state["cursor"], "type": type(e).__name__, "at": now()})
        jsonfile(journal, state)
        raise
    finally:
        store.close()


def import_inbox(project, as_of):
    inbox = project.data / "inbox" / "uspto"
    inbox.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(inbox.iterdir()):
        if path.suffix.lower() not in {".xml", ".zip"}:
            continue
        sidecar = path.with_suffix(path.suffix + ".json")
        meta = readjson(sidecar) if sidecar.exists() else {}
        results.append(import_bulk(project, path, meta.get("source_url", DATASETS),
            max_records=project.settings["collection"].get("uspto_records_per_file", 500), as_of=as_of))
    return results
