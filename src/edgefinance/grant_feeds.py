"""Weekly official grant feeds: enumerate first, checkpoint, then fetch bounded detail."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET

from .core import digest, dumps, jsonfile, now, readjson

DETAIL_VERSION = 2


def epo_entries(raw, publication_date):
    entries = []
    for a in BeautifulSoup(raw, "html.parser").select("a[href]"):
        match = re.search(r"/patents/(EP\d+)NW(B[12389])$", a["href"])
        if not match:
            continue
        number, kind = match.groups()
        entries.append({"id": number + kind, "publication_number": number + kind,
            "kind_code": kind, "event": "new_grant" if kind == "B1" else "amendment_or_correction",
            "published_at": publication_date, "url": urljoin("https://data.epo.org", a["href"]),
            "detail_status": "pending", "title": "", "assignees": []})
    return entries


def epo_grants(project, fetch, store, source, as_of, cap, emit, state):
    from .collectors import parse_epo, local_name
    path = project.data / "patent-feeds" / "epo-grants.json"
    feed = readjson(path) if path.exists() else {"entries": {}, "batches": {}, "last_discovery_as_of": None}
    since = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
    if feed["last_discovery_as_of"]:
        since = min(since, (date.fromisoformat(feed["last_discovery_as_of"]) - timedelta(days=7)).isoformat())
    base = "https://data.epo.org/publication-server/rest/v1.2/"
    raw, _ = fetch.get(base + "publication-dates")
    store.blob(raw)
    dates = sorted({(a.get_text(strip=True).replace("/", "-"), urljoin(base, a["href"]))
        for a in BeautifulSoup(raw, "html.parser").select("a[href]")
        if since <= a.get_text(strip=True).replace("/", "-") <= as_of})
    for when, listing in dates:
        raw, _ = fetch.get(listing)
        batch = epo_entries(raw, when)
        feed["batches"][when] = {"url": listing, "raw_path": store.blob(raw),
            "new_grants": sum(e["event"] == "new_grant" for e in batch),
            "amendments_or_corrections": sum(e["event"] != "new_grant" for e in batch)}
        for entry in batch:
            # Event date is part of identity: a re-publication must remain distinguishable.
            feed["entries"].setdefault(entry["id"] + "-" + when, entry)
        jsonfile(path, feed)
    feed["last_discovery_as_of"] = as_of
    jsonfile(path, feed)
    pending = sorted([(key, e) for key, e in feed["entries"].items()
        if (e["detail_status"] != "complete" or e.get("parser_version") != DETAIL_VERSION) and e["published_at"] <= as_of],
        key=lambda pair: (pair[1]["event"] != "new_grant", pair[1]["published_at"], pair[1]["id"]))
    details = min(cap, project.settings["collection"].get("grant_details_per_run", 2))
    for key, entry in pending[:details]:
        try:
            url = entry["url"] + "/document.xml"
            raw, _ = fetch.get(url)
            root = ET.fromstring(raw)
            if root.get("kind") != entry["kind_code"] or root.get("date-publ") != entry["published_at"].replace("-", ""):
                raise ValueError("EPO detail does not match listed kind/date")
            doc = parse_epo(raw, url, entry["published_at"])
            # The original XML remains archived; selected claims are the first analysis stage.
            selected = []
            for node in root.iter():
                if local_name(node.tag).lower() in {"abstract", "claims"} and node.get("lang", "en").lower() in {"en", "eng"}:
                    selected.append(local_name(node.tag) + ": " + " ".join(node.itertext()).strip())
            owners = [" ".join(n.itertext()).strip() for n in root.iter() if local_name(n.tag).lower() == "b731"]
            doc["metadata"].update(publication_number=entry["publication_number"], kind_code=entry["kind_code"],
                patent_event=entry["event"], assignees=owners, first_grant_date=entry["published_at"] if entry["event"] == "new_grant" else None)
            doc["metadata"].update(application_date=root.findtext(".//B220/date"),
                priority_dates=[n.text for n in root.findall(".//B320/date")],
                grant_publication_verified=True, currently_in_force=None)
            heading = dumps({"title": doc["title"], "patent": doc["metadata"],
                "scope": "Bibliography and English claims/abstract only; full description is archived but not included in this analysis stage."})
            doc.update(text=heading + "\n" + "\n\n".join(selected), coverage="grant_bibliography_and_claims" if selected else "bibliographic_only",
                url=url, kind="patent", stable_id=key)
            emit(doc, raw)
            entry.update(detail_status="complete", parser_version=DETAIL_VERSION, title=doc["title"], assignees=owners)
        except Exception as e:
            entry.update(detail_status="failed", last_error=type(e).__name__)
            state["failed"] += 1
        jsonfile(path, feed)
    current = [e for e in feed["entries"].values() if since <= e["published_at"] <= as_of]
    remaining = sum(e["detail_status"] != "complete" for e in feed["entries"].values())
    state.update(discovered=len(current), new_grants_discovered=sum(e["event"] == "new_grant" for e in current),
        pending_details=remaining, status="partial" if remaining else "complete",
        notes=[f"Full B-document enumeration for available batches {since} to {as_of}; B1=new grant, B2/B3/B8/B9=amendment/correction.",
            f"{remaining} details pending across retained batches. Downloaded XML is archived; analysis initially selects bibliography and English claims/abstract."])


def uspto_grant_files(payload, since, as_of):
    """Locate official weekly grant ZIP records; never guess a download URL."""
    found = {}
    def visit(value):
        if isinstance(value, dict):
            name, url = value.get("fileName", ""), value.get("fileDownloadURI", "")
            match = re.fullmatch(r"ipg(\d{2})(\d{2})(\d{2})\.zip", name, re.I)
            if match and url:
                yy, mm, dd = match.groups()
                when = f"20{yy}-{mm}-{dd}"
                date.fromisoformat(when)
                host = urlsplit(url)
                if host.scheme != "https" or host.hostname != "api.uspto.gov" or host.username or host.password or host.query:
                    raise ValueError("Grant download URL requires official API host without credentials in URL")
                if since <= when <= as_of:
                    found[name] = {"name": name, "url": url, "grant_date": when, "status": "pending"}
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(payload)
    return list(found.values())


def download_grant_zip(fetch, url, destination, api_key, max_bytes):
    """Restart interrupted download, never treat .part as a complete archive."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".zip.part")
    if destination.exists():
        import zipfile
        with zipfile.ZipFile(destination) as z:
            if not z.infolist(): raise ValueError("Empty ZIP")
        return
    # Redirects cannot forward the credential to a different host.
    with fetch.client.stream("GET", url, headers={"x-api-key": api_key}, follow_redirects=False) as response:
        response.raise_for_status()
        if int(response.headers.get("content-length", "0")) > max_bytes:
            raise ValueError("Grant ZIP exceeds configured download budget")
        size = 0
        with partial.open("wb") as out:
            for block in response.iter_bytes(1024 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise ValueError("Grant ZIP exceeds configured download budget")
                out.write(block)
    import zipfile
    with zipfile.ZipFile(partial) as z:
        if not z.infolist(): raise ValueError("Empty ZIP")
    partial.replace(destination)


def uspto_grants(project, fetch, store, source, as_of, state):
    from .uspto import import_bulk
    path = project.data / "patent-feeds" / "uspto-grants.json"
    feed = readjson(path) if path.exists() else {"files": {}, "last_discovery_as_of": None}
    since = (date.fromisoformat(as_of) - timedelta(days=7)).isoformat()
    if feed["last_discovery_as_of"]:
        since = min(since, (date.fromisoformat(feed["last_discovery_as_of"]) - timedelta(days=7)).isoformat())
    url = "https://api.uspto.gov/api/v1/datasets/products/PTGRXML"
    raw, _ = fetch.get(url, headers={"x-api-key": project.secrets["USPTO_API_KEY"]})
    feed["catalog_raw_path"] = store.blob(raw)
    payload = json.loads(raw)
    if "bulkDataProductBag" not in payload:
        raise ValueError("Unexpected ODP product schema; live credential validation required")
    discovered = uspto_grant_files(payload, since, as_of)
    for item in discovered:
        feed["files"].setdefault(item["name"], item)
    feed["last_discovery_as_of"] = as_of
    jsonfile(path, feed)
    pending = sorted([f for f in feed["files"].values() if f["status"] != "complete"], key=lambda f:f["grant_date"])
    cfg = project.settings["collection"]
    for item in pending[:cfg.get("uspto_zip_files_per_run", 1)]:
        try:
            dest = project.data / "inbox" / "uspto" / item["name"]
            download_grant_zip(fetch, item["url"], dest, project.secrets["USPTO_API_KEY"], cfg.get("uspto_download_mb", 1024) * 1024**2)
            source_url = "https://data.uspto.gov/bulkdata/datasets/ptgrxml"
            jsonfile(dest.with_suffix(".zip.json"), {"source_url": source_url})
            result = import_bulk(project, dest, source_url, cfg.get("uspto_records_per_file", 500), as_of=as_of)
            item.update(status=result["status"], records_processed=result["cursor"], file_sha256=result["file_sha256"])
            state["fetched"] += result["processed_this_run"]
            state["new"] += result["new_this_run"]
        except Exception as e:
            item.update(status="failed", last_error=type(e).__name__)
            state["failed"] += 1
        jsonfile(path, feed)
    remaining = sum(f["status"] != "complete" for f in feed["files"].values())
    state.update(discovered=len(discovered), status="partial" if remaining else "complete",
        notes=[f"PTGRXML weekly grant ZIP batches, {since} to {as_of}. {remaining} retained batches pending completion.",
            "API path needs a valid USPTO key; schema mismatches and redirects stop safely. Counts here are batches/processed records, not a claim of nationwide complete ingestion."])
