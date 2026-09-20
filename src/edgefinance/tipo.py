"""Taiwan Intellectual Property Office grant discovery and case enrichment."""
from __future__ import annotations

import json
import re
import ssl
from datetime import date
from urllib.parse import urlsplit

import httpx

from .core import dumps, jsonfile, readjson

GAZETTE_API = "https://cloud.tipo.gov.tw/S220/gazette/api/patents/grants"
CASE_API = "https://tiponet.tipo.gov.tw/S092_API/opd1/"
DETAIL_VERSION = 1


def roc_date(value: str) -> str:
    """Convert ROC dates used by TIPO (115.09.11 or 1150911) to ISO dates."""
    text = str(value or "").strip()
    parts = re.findall(r"\d+", text)
    if len(parts) == 1 and len(parts[0]) in {7, 8}:
        compact = parts[0]
        width = 4 if len(compact) == 8 else 3
        parts = [compact[:width], compact[width:width + 2], compact[width + 2:]]
    if len(parts) != 3:
        raise ValueError("Unrecognized TIPO date")
    year, month, day = map(int, parts)
    if year < 1911:
        year += 1911
    return date(year, month, day).isoformat()


def _official_download(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "cloud.tipo.gov.tw" or parsed.username or parsed.password:
        raise ValueError("TIPO download link is not on the official HTTPS host")
    return url


def grant_issues(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected TIPO issue schema")
    issues = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Unexpected TIPO issue row")
        vol, no = int(row["vol"]), int(row["no"])
        if vol <= 0 or no <= 0:
            raise ValueError("Invalid TIPO issue number")
        issues.append({"vol": vol, "no": no, "published_at": roc_date(row["publicationDate"])})
    return issues


def _name(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def company_candidates(project, applicants: list[str]) -> list[str]:
    applicant_names = {_name(value) for value in applicants if _name(value)}
    return [company["ticker"] for company in project.companies
        if applicant_names & {_name(value) for value in [company["name"], *company.get("aliases", [])] if _name(value)}]


def grant_page(payload: dict, issue: dict, project) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unexpected TIPO grant page schema")
    rows = []
    for item in payload["data"]:
        application_no = str(item.get("applicationNo", "")).strip()
        certificate_no = str(item.get("certificateNo", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9-]{5,30}", application_no) or not re.fullmatch(r"[A-Za-z0-9-]{2,30}", certificate_no):
            raise ValueError("Invalid TIPO patent identifier")
        url = _official_download(item.get("pdfUrl", ""))
        title = str(item.get("title", "")).strip()
        applicants = [str(x).strip() for x in item.get("applicants", []) if str(x).strip()]
        topics = project.topic_ids(title)
        entities = company_candidates(project, applicants)
        stable_id = f"{issue['vol']:03d}{issue['no']:03d}-{application_no}-{certificate_no}"
        rows.append({
            "id": stable_id,
            "publication_number": certificate_no,
            "application_number": application_no,
            "kind_code": certificate_no[:1].upper(),
            "event": "new_grant",
            "published_at": issue["published_at"],
            "url": url,
            "title": title,
            "assignees": applicants,
            "inventors": [str(x).strip() for x in item.get("inventors", []) if str(x).strip()],
            "topics": topics,
            "entities": entities,
            "detail_status": "pending" if topics or entities else "not_selected",
            "parser_version": DETAIL_VERSION,
            "issue": {"vol": issue["vol"], "no": issue["no"]},
        })
    expected = int(payload.get("size", len(rows)))
    if expected != len(rows):
        raise ValueError("TIPO grant page count mismatch")
    return rows


def _safe_case(payload: dict) -> dict:
    if str(payload.get("code")) != "00":
        raise ValueError("TIPO case API returned a non-success code")
    applicants = []
    for person in payload.get("applicants", []):
        if isinstance(person, dict):
            applicants.append({k: str(person.get(k, "")).strip() for k in ["chineseTitle", "englishTitle"]})
    priorities = []
    for priority in payload.get("priorityInfoList", []):
        if isinstance(priority, dict):
            priorities.append({k: priority.get(k) for k in ["countryCode", "countryName", "date", "priorityNumber"]})
    return {k: payload.get(k) for k in ["caseNo", "publishNo", "announcementNo", "applicationDate", "title",
        "classification", "caseStatus", "caseType", "twisFlag"]} | {"applicants": applicants, "priorities": priorities}


def _safe_relations(payload: dict) -> list[dict]:
    if str(payload.get("code")) != "00":
        raise ValueError("TIPO relation API returned a non-success code")
    fields = ["relationCaseApplicationDate", "relationCaseId", "relationCaseReasonName", "relationCaseTitle", "relationNewOrOld"]
    return [{k: row.get(k) for k in fields} for row in payload.get("relationCase", []) if isinstance(row, dict)]


def _safe_history(payload: dict) -> list[dict]:
    if str(payload.get("code")) != "00":
        raise ValueError("TIPO file-list API returned a non-success code")
    fields = ["caseReasonName", "category", "documentDate", "documentNumber"]
    return [{k: row.get(k) for k in fields} for row in payload.get("resultFileList", []) if isinstance(row, dict)]


class CaseClient:
    """Use the user-issued credentials only on TIPO's fixed case API host."""

    def __init__(self, project):
        username = project.secrets.get("TIPO_API_USERNAME")
        password = project.secrets.get("TIPO_API_PASSWORD")
        if not username or not password:
            raise ValueError("TIPO case API credentials are not configured")
        cfg = project.settings["collection"]
        self.username, self.password = username, password
        self.max_bytes = cfg["max_response_mb"] * 1024 * 1024
        self.client = httpx.Client(timeout=cfg["timeout_seconds"], follow_redirects=False,
            verify=ssl.create_default_context(), headers={"User-Agent": cfg["user_agent"]})
        self.token = None

    def authenticate(self):
        response = self.client.get(CASE_API + "getAuth", auth=(self.username, self.password))
        if response.status_code != 200 or len(response.content) > 16_384:
            raise ValueError("TIPO authentication failed")
        token = response.text.strip()
        if len(token) < 16 or len(token) > 8192 or any(ch.isspace() or ord(ch) < 32 for ch in token):
            raise ValueError("TIPO authentication returned an invalid token")
        self.token = token

    def _get(self, endpoint: str, case_id: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9-]{3,30}", case_id):
            raise ValueError("Invalid TIPO case identifier")
        if not self.token:
            self.authenticate()
        response = self.client.get(CASE_API + endpoint + "/" + case_id,
            headers={"Authorization": "Bearer " + self.token})
        if response.status_code != 200 or len(response.content) > self.max_bytes:
            raise ValueError("TIPO case endpoint failed")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected TIPO case endpoint schema")
        return payload

    def bundle(self, case_id: str) -> dict:
        case = _safe_case(self._get("getCaseInfo", case_id))
        gaps, relations, history = [], [], []
        try:
            relations = _safe_relations(self._get("getReationCase", case_id))
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            gaps.append({"endpoint": "related_cases", "error": type(exc).__name__})
        try:
            history = _safe_history(self._get("getResultFileList", case_id))
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            gaps.append({"endpoint": "procedural_history", "error": type(exc).__name__})
        return {"case": case, "relations": relations, "procedural_history": history, "coverage_gaps": gaps}

    def close(self):
        self.client.close()


def _detail_document(entry: dict, bundle: dict, project) -> tuple[dict, bytes]:
    case = bundle["case"]
    if str(case.get("caseNo")) != entry["application_number"]:
        raise ValueError("TIPO case detail does not match the gazette application number")
    announcement = str(case.get("announcementNo") or "")
    if announcement and announcement != entry["publication_number"]:
        raise ValueError("TIPO case detail does not match the gazette certificate number")
    applicants = [name for item in case["applicants"] for name in [item.get("chineseTitle"), item.get("englishTitle")] if name]
    entities = company_candidates(project, applicants or entry["assignees"])
    safe_raw = dumps({"gazette": entry, "case_api": bundle}).encode("utf-8")
    document = {
        "stable_id": entry["id"],
        "url": entry["url"],
        "title": case.get("title") or entry["title"],
        "text": dumps({
            "scope": "TIPO official grant bibliography, classification, priority, related-case and procedural-history fields; linked PDF is not transcribed.",
            "patent": case,
            "relations": bundle["relations"],
            "procedural_history": bundle["procedural_history"],
            "coverage_gaps": bundle["coverage_gaps"],
        }),
        "published_at": entry["published_at"],
        "kind": "patent",
        "coverage": "tipo_case_bibliography_and_history",
        "topics": project.topic_ids((case.get("title") or entry["title"])),
        "entities": entities,
        "metadata": {
            "publication_number": entry["publication_number"],
            "application_number": entry["application_number"],
            "kind_code": entry["kind_code"],
            "patent_event": "new_grant",
            "assignees": applicants or entry["assignees"],
            "classification": case.get("classification"),
            "application_date": roc_date(case["applicationDate"]) if case.get("applicationDate") else None,
            "priority_dates": [p.get("date") for p in case["priorities"] if p.get("date")],
            "grant_publication_verified": True,
            "currently_in_force": None,
            "mapping_status": "exact_name_candidate" if entities else "unresolved",
        },
    }
    return document, safe_raw


def _bibliographic_document(entry: dict) -> tuple[dict, bytes]:
    raw = json.dumps(entry, ensure_ascii=False).encode("utf-8")
    return ({
        "stable_id": entry["id"], "url": entry["url"], "title": entry["title"],
        "text": dumps({"scope": "TIPO official grant gazette bibliography only; case API enrichment is pending.",
            "application_number": entry["application_number"], "certificate_number": entry["publication_number"],
            "applicants": entry["assignees"], "inventors": entry["inventors"], "issue": entry["issue"]}),
        "published_at": entry["published_at"], "kind": "patent", "coverage": "bibliographic_only",
        "topics": entry["topics"], "entities": entry["entities"],
        "metadata": {"publication_number": entry["publication_number"], "application_number": entry["application_number"],
            "kind_code": entry["kind_code"], "patent_event": "new_grant", "assignees": entry["assignees"],
            "grant_publication_verified": True, "currently_in_force": None,
            "mapping_status": "exact_name_candidate" if entry["entities"] else "unresolved"},
    }, raw)


def tipo_grants(project, fetch, store, source, as_of, cap, emit, state):
    path = project.data / "patent-feeds" / "tipo-grants.json"
    feed = readjson(path) if path.exists() else {"entries": {}, "batches": {}, "last_discovery_as_of": None}
    briefs_url = GAZETTE_API + "/issues/briefs"
    raw, _ = fetch.get(briefs_url)
    feed["issue_briefs_raw_path"] = store.blob(raw)
    available = grant_issues(json.loads(raw))
    selected = [issue for issue in available if state["since"] <= issue["published_at"] <= as_of]
    listing_url = GAZETTE_API + "/issues/contents/sud00_1"
    for issue in selected:
        issue_id = f"{issue['vol']:03d}{issue['no']:03d}"
        if feed["batches"].get(issue_id, {}).get("status") == "complete":
            continue
        page, pages, entries, raw_paths, total = 1, 1, [], [], None
        while page <= pages:
            body, _ = fetch.get(listing_url, params={"vol": issue["vol"], "no": issue["no"],
                "pageNo": page, "paginationSize": 5000})
            raw_paths.append(store.blob(body))
            payload = json.loads(body)
            pages = int(payload.get("totalPages", 0))
            total = int(payload.get("totalCount", -1))
            if pages < 1 or pages > 100:
                raise ValueError("Unexpected TIPO pagination")
            entries.extend(grant_page(payload, issue, project))
            page += 1
        if total != len(entries):
            raise ValueError("TIPO issue total does not match retrieved rows")
        for entry in entries:
            previous = feed["entries"].get(entry["id"])
            if previous:
                detail = previous.get("detail_status", entry["detail_status"])
                entry["detail_status"] = detail
            feed["entries"][entry["id"]] = entry
        feed["batches"][issue_id] = {"status": "complete", "published_at": issue["published_at"],
            "vol": issue["vol"], "no": issue["no"], "count": len(entries), "raw_paths": raw_paths}
        jsonfile(path, feed)
    feed["last_discovery_as_of"] = as_of
    jsonfile(path, feed)

    # Topic and company dictionaries evolve over time. Reclassify retained
    # bibliography rows so an expanded research universe can promote older
    # rows into the bounded detail-enrichment queue without redownloading the
    # official gazette issue.
    for entry in feed["entries"].values():
        entry["topics"] = project.topic_ids(entry.get("title", ""))
        entry["entities"] = company_candidates(project, entry.get("assignees", []))
        if entry.get("detail_status") == "not_selected" and (entry["topics"] or entry["entities"]):
            entry["detail_status"] = "pending"
    jsonfile(path, feed)

    current = [entry for entry in feed["entries"].values() if state["since"] <= entry["published_at"] <= as_of]
    candidates = [entry for entry in feed["entries"].values()
        if entry["published_at"] <= as_of and entry["detail_status"] in {"pending", "failed"}]
    candidates.sort(key=lambda entry: (bool(entry["entities"]), len(entry["topics"]), entry["kind_code"] == "I",
        entry["published_at"], entry["publication_number"]), reverse=True)
    budget = min(cap, project.settings["collection"].get("tipo_details_per_run", 8))
    configured = bool(project.secrets.get("TIPO_API_USERNAME") and project.secrets.get("TIPO_API_PASSWORD"))
    client = CaseClient(project) if configured and budget else None
    try:
        for entry in candidates[:budget]:
            try:
                if client:
                    document, evidence_raw = _detail_document(entry, client.bundle(entry["application_number"]), project)
                    entry["detail_status"] = "complete"
                else:
                    document, evidence_raw = _bibliographic_document(entry)
                emit(document, evidence_raw)
            except Exception as exc:
                entry["detail_status"] = "failed"
                entry["last_error"] = type(exc).__name__
                state["failed"] += 1
            jsonfile(path, feed)
    finally:
        if client:
            client.close()
    remaining = sum(entry["detail_status"] in {"pending", "failed"} for entry in feed["entries"].values())
    state.update(discovered=len(current), new_grants_discovered=len(current), candidate_count=len(candidates),
        pending_details=remaining, status="partial" if remaining or state["failed"] else "complete",
        notes=[
            f"Official TIPO gazette enumeration for {len(selected)} issue(s), {state['since']} to {as_of}; {len(current)} grant bibliography rows retained.",
            f"{len(candidates)} topic/company candidates were eligible for bounded enrichment; {remaining} retained candidates remain.",
            "TIPO case credentials enrich known application numbers but do not enumerate new grants. The public gazette API performs enumeration.",
            "Grant publication is verified; current enforceability and stock-company ownership still require separate review.",
        ])
