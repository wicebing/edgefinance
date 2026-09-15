from __future__ import annotations

import csv
import io
import json
import re
import ssl
import time
import uuid
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET
from pypdf import PdfReader

from .core import Project, Store, dumps, now, public_url, jsonfile, readjson


class Fetcher:
    def __init__(self, project: Project):
        cfg = project.settings["collection"]
        self.timeout = cfg["timeout_seconds"]
        self.retries = cfg["retries"]
        self.limit = cfg["max_response_mb"] * 1024 * 1024
        self.client = httpx.Client(timeout=self.timeout, follow_redirects=True, verify=ssl.create_default_context(),
            headers={"User-Agent": project.secrets.get("SEC_USER_AGENT") or cfg["user_agent"]})
        self.last = 0.0

    def get(self, url, *, params=None, headers=None):
        public_url(url)
        for attempt in range(self.retries + 1):
            time.sleep(max(0, .35 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                with self.client.stream("GET", url, params=params, headers=headers) as r:
                    if r.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                        wait = r.headers.get("Retry-After", "")
                        time.sleep(min(15, int(wait) if wait.isdigit() else 2 ** attempt))
                        continue
                    r.raise_for_status()
                    chunks, size = [], 0
                    for b in r.iter_bytes():
                        size += len(b)
                        if size > self.limit:
                            raise ValueError("Source response exceeds configured byte budget")
                        chunks.append(b)
                    return b"".join(chunks), r.headers.get("content-type", "")
            except httpx.TransportError:
                if attempt >= self.retries:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Retry budget exhausted")

    def close(self):
        self.client.close()


def html_text(raw: bytes, content_type=""):
    if raw.startswith(b"%PDF") or "application/pdf" in content_type:
        reader = PdfReader(io.BytesIO(raw))
        text = "\n\n".join(f"[Page {i + 1}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages))
        if len(text.strip()) < 100:
            raise ValueError("PDF requires OCR; no usable text")
        return "PDF document", text
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Untitled source"
    for tag in soup.select("script,style,nav,footer,header,noscript,form"):
        tag.decompose()
    body = soup.select_one("article") or soup.select_one("main") or soup.body or soup
    return title, body.get_text("\n", strip=True)


def parsed_date(text: str):
    if re.match(r"^\d{8}$", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return parsedate_to_datetime(text).date().isoformat()


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(raw: bytes):
    root = ET.fromstring(raw)
    entries = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        fields = {}
        for child in item:
            name = local_name(child.tag)
            fields[name] = child.get("href") if name == "link" and child.get("href") else "".join(child.itertext())
        when = fields.get("pubDate") or fields.get("published") or fields.get("updated")
        if not when or not fields.get("link"):
            continue
        try:
            entries.append({"title": fields.get("title", "Untitled"), "url": public_url(fields["link"].strip()),
                "published_at": parsed_date(when), "summary": fields.get("description", fields.get("summary", ""))})
        except (ValueError, TypeError):
            continue
    return entries


def parse_google_patent(raw: bytes, url: str):
    soup = BeautifulSoup(raw, "html.parser")
    def meta(name):
        node = soup.find("meta", attrs={"name": name})
        return node.get("content", "") if node else ""
    pub = meta("DC.date") or meta("citation_date")
    dates = soup.select('time[itemprop="publicationDate"]')
    if dates:
        pub = dates[-1].get_text(strip=True)
    title = meta("DC.title") or meta("citation_title")
    if not title:
        node = soup.select_one('[itemprop="title"]')
        title = node.get_text(" ", strip=True) if node else "Patent"
    parts = []
    for label, selector in [("Abstract", '[itemprop="abstract"]'), ("Description", '[itemprop="description"]'), ("Claims", '[itemprop="claims"]')]:
        nodes = soup.select(selector)
        if nodes:
            parts.append(label + "\n" + "\n".join(n.get_text("\n", strip=True) for n in nodes))
    assignees = list(dict.fromkeys(n.get_text(" ", strip=True) for n in soup.select('[itemprop="assigneeOriginal"], [itemprop="assigneeCurrent"]')))
    patent_id = url.split("/patent/")[-1].split("/")[0]
    family = soup.select_one('[itemprop="familyID"]')
    return {"title": title, "text": "\n\n".join(parts), "published_at": parsed_date(pub.replace("/", "-")),
        "metadata": {"publication_number": patent_id, "assignees": assignees,
            "family_id": family.get_text(strip=True) if family else None,
            "legal_status_verified": False, "mirror": "Google Patents", "mapping_status": "unresolved"}}


def parse_epo(raw: bytes, url: str, publication_date: str):
    root = ET.fromstring(raw)
    titles = [n for n in root.iter() if local_name(n.tag) == "invention-title"]
    title_node = next((n for n in titles if n.get("lang", "").lower() == "en"), titles[0] if titles else None)
    title = " ".join(title_node.itertext()).strip() if title_node is not None else url.split("/")[-2]
    if title_node is None:
        language = ""
        for n in root.iter():
            if local_name(n.tag) == "B541":
                language = n.text or ""
            elif local_name(n.tag) == "B542" and language == "en":
                title = " ".join(n.itertext()).strip()
    parts = []
    for n in root.iter():
        if local_name(n.tag).lower() in {"abstract", "description", "claims"} and n.get("lang", "en").lower() in {"en", "eng"}:
            parts.append(local_name(n.tag).title() + "\n" + " ".join(n.itertext()).strip())
    has_text = bool(parts)
    if not parts:
        parts = [" ".join(root.itertext()).strip()]
    names = [" ".join(n.itertext()).strip() for n in root.iter() if local_name(n.tag) == "applicant"]
    return {"title": title, "text": "\n\n".join(parts), "published_at": publication_date,
        "coverage": "patent_text" if has_text else "bibliographic_only",
        "metadata": {"publication_number": root.get("doc-number", url.split("/")[-2]), "assignees": names,
            "family_id": None, "legal_status_verified": False, "mapping_status": "unresolved"}}


def financial_snapshot(data: dict, as_of: str):
    selected = {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "NetIncomeLoss",
        "OperatingIncomeLoss", "ResearchAndDevelopmentExpense", "CashAndCashEquivalentsAtCarryingValue", "LongTermDebtCurrent",
        "LongTermDebtNoncurrent", "StockholdersEquity", "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"}
    rows = []
    for taxonomy, facts in data.get("facts", {}).items():
        for name, fact in facts.items():
            if name not in selected:
                continue
            for unit, points in fact.get("units", {}).items():
                valid = [p for p in points if p.get("filed", "9999") <= as_of and p.get("form") in {"10-K", "10-Q", "20-F", "40-F"}]
                # Keep the latest filing known by cutoff for each exact period/unit.
                periods = {}
                for p in sorted(valid, key=lambda x: x["filed"]):
                    periods[(p.get("start"), p.get("end"))] = p
                for p in sorted(periods.values(), key=lambda x: (x.get("end", ""), x.get("start", "")), reverse=True)[:8]:
                    rows.append({"concept": name, "taxonomy": taxonomy, "unit": unit,
                        **{k: p.get(k) for k in ["start", "end", "val", "filed", "form", "accn"]}})
    return rows


def collect(project: Project, as_of: str, source_ids: list[str] | None = None, *, limit: int | None = None):
    store, fetch = project.store(), Fetcher(project)
    existing = store.documents()
    previous = store.latest_run()
    window = project.settings["project"]["lookback_days"] if existing else project.settings["project"]["bootstrap_days"]
    since = (date.fromisoformat(as_of) - timedelta(days=window)).isoformat()
    # Resume collection from the last successful source checkpoint with overlap.
    run = {"id": datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], "as_of": as_of,
        "started_at": now(), "sources": [], "new_document_ids": [], "document_ids": [], "since": since}
    cap = limit if limit is not None else project.settings["collection"]["max_items_per_source"]
    if cap < 0:
        raise ValueError("Item cap must not be negative")
    try:
        for source in project.sources:
            if not source.get("enabled") or (source_ids and source["id"] not in source_ids):
                continue
            sid = source["id"]
            state = {"id": sid, "name": source["name"], "status": "complete", "fetched": 0, "new": 0,
                "failed": 0, "discovered": None, "bounded": True, "notes": [], "docs": source.get("docs", ""), "since": since}
            run["sources"].append(state)
            if previous:
                old = next((s for s in previous["sources"] if s["id"] == sid), None)
                if old and old["status"] == "complete":
                    state["since"] = min(since, (date.fromisoformat(previous["as_of"]) - timedelta(days=7)).isoformat())
            def emit(doc, raw):
                if doc["published_at"][:10] > as_of:
                    state["notes"].append("Excluded post-cutoff document")
                    return
                doc.update(source_id=sid, origin=doc.get("origin", source.get("origin", sid)))
                doc.setdefault("topics", project.topic_ids(doc["title"] + " " + doc["text"][:12000]))
                saved, new = store.add(doc, raw)
                state["fetched"] += 1
                state["new"] += int(new)
                run["document_ids"].append(saved["id"])
                if new:
                    run["new_document_ids"].append(saved["id"])
            def failed(e):
                state["failed"] += 1
                state["status"] = "partial"
                code = f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else type(e).__name__
                state["notes"].append(code)  # Never serialize credentials or raw exception messages.
            print(f"Collecting {sid} ...", flush=True)
            try:
                key = source.get("credential")
                if key and not project.secrets.get(key):
                    state.update(status="needs_credentials", notes=[f"Set {key} locally"], bounded=False)
                    continue
                if source["kind"] == "epo_grants":
                    from .grant_feeds import epo_grants
                    epo_grants(project, fetch, store, source, as_of, cap, emit, state)
                elif source["kind"] == "tipo_grants":
                    from .tipo import tipo_grants
                    tipo_grants(project, fetch, store, source, as_of, cap, emit, state)
                elif source["kind"] == "uspto_grants":
                    from .grant_feeds import uspto_grants
                    uspto_grants(project, fetch, store, source, as_of, state)
                elif source["kind"] == "uspto_local":
                    from .uspto import import_inbox
                    imports = import_inbox(project, as_of)
                    state.update(status="complete" if imports and all(i["status"] == "complete" for i in imports) else ("partial" if imports else "awaiting_download"),
                        fetched=sum(i["processed_this_run"] for i in imports), new=sum(i["new_this_run"] for i in imports),
                        discovered=len(imports), notes=["Manual ODP ZIP/XML inbox; no API key needed for local processing. Only supplied files are covered.",
                            f"{sum(i['cursor'] for i in imports)} records inspected across {len(imports)} files; per-file limits resume next run."])
                elif source["kind"] == "rss":
                    raw, _ = fetch.get(source["url"])
                    store.blob(raw)
                    entries = [e for e in parse_feed(raw) if state["since"] <= e["published_at"] <= as_of]
                    state["discovered"] = len(entries)
                    queue_path = project.data / "queues" / f"{sid}.json"
                    queue = readjson(queue_path) if queue_path.exists() else {}
                    known = {d["url"] for d in existing if d["source_id"] == sid and d["coverage"] == "full_text"}
                    for entry in entries:
                        if entry["url"] not in known:
                            queue[entry["url"]] = entry
                    entries = list(queue.values())
                    jsonfile(queue_path, queue)
                    state["queued"] = len(entries)
                    if len(entries) > cap:
                        state["status"] = "partial"
                        state["notes"].append("Configured item cap; remaining entries are not claimed collected")
                    for entry in sorted(entries, key=lambda e: e["published_at"], reverse=True)[:cap]:
                        try:
                            body, ct = fetch.get(entry["url"])
                            _, text = html_text(body, ct)
                            if len(text) < 100:
                                raise ValueError("Body too short")
                            emit({**entry, "text": text, "kind": "article", "topics": source.get("topics") or project.topic_ids(text)}, body)
                            queue.pop(entry["url"], None)
                            jsonfile(queue_path, queue)
                        except Exception as e:
                            failed(e)
                            summary = BeautifulSoup(entry["summary"], "html.parser").get_text(" ", strip=True)
                            if summary:
                                emit({**entry, "text": summary, "coverage": "feed_summary", "kind": "article"}, raw)
                elif source["kind"] == "sec":
                    companies = project.companies[:project.settings["collection"]["sec_company_limit"]]
                    state["discovered"] = len(project.companies)
                    state["notes"].append(f"Selected-concept snapshots for {len(companies)}/{len(project.companies)} watchlist companies; not complete filings")
                    if len(companies) < len(project.companies):
                        state["status"] = "partial"
                    for company in companies:
                        try:
                            cik = company["cik"].zfill(10)
                            submission_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                            sr, _ = fetch.get(submission_url)
                            store.blob(sr)
                            sub = json.loads(sr)
                            if company["ticker"] not in sub.get("tickers", []):
                                raise ValueError("CIK/ticker mapping requires review")
                            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                            raw, _ = fetch.get(url)
                            rows = financial_snapshot(json.loads(raw), as_of)
                            if not rows:
                                raise ValueError("No comparable financial concepts")
                            emit({"url": url, "title": f"{company['ticker']} · SEC 財務觀測（選定科目）",
                                "text": dumps({"company": sub["name"], "ticker": company["ticker"], "cik": cik, "observations": rows}),
                                "published_at": max(r["filed"] for r in rows), "kind": "financial",
                                "origin": f"issuer:{cik}", "coverage": "selected_financial_concepts",
                                "entities": [company["ticker"]], "topics": company["topics"],
                                "metadata": {"observations": rows, "verified_company_name": sub["name"], "mapping_status": "sec_verified", "retrieved_vintage": now()}}, raw)
                        except Exception as e:
                            failed(e)
                elif source["kind"] == "patent_pages":
                    state["discovered"] = len(source["urls"])
                    if len(source["urls"]) > cap:
                        state["status"] = "partial"
                    state["notes"].append("Explicit historical watch samples; not all new US publications. Legal status/family need primary verification.")
                    for url in source["urls"][:cap]:
                        try:
                            raw, _ = fetch.get(url)
                            doc = parse_google_patent(raw, url)
                            doc.update(url=url, kind="patent", coverage="patent_text")
                            # Exact normalized assignee names only; no fuzzy stock attribution.
                            norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
                            doc["entities"] = [c["ticker"] for c in project.companies if any(norm(a) == norm(n)
                                for a in doc["metadata"]["assignees"] for n in [c["name"], *c.get("aliases", [])])]
                            doc["metadata"]["mapping_status"] = "exact_name_candidate" if doc["entities"] else "unresolved"
                            emit(doc, raw)
                        except Exception as e:
                            failed(e)
                elif source["kind"] == "epo":
                    base = "https://data.epo.org/publication-server/rest/v1.2/"
                    raw, _ = fetch.get(base + "publication-dates")
                    store.blob(raw)
                    soup = BeautifulSoup(raw, "html.parser")
                    dates = [(a.get_text(strip=True).replace("/", "-"), urljoin(base, a["href"])) for a in soup.select("a[href]")]
                    dates = sorted([(d, u) for d, u in dates if state["since"] <= d <= as_of], reverse=True)
                    if not dates:
                        state["notes"].append("No publication date inside configured window")
                    for pub_date, listing in dates[:1]:
                        raw, _ = fetch.get(listing)
                        store.blob(raw)
                        links = BeautifulSoup(raw, "html.parser").select("a[href]")
                        state["discovered"] = len(links)
                        count = min(cap, project.settings["collection"]["epo_document_limit"])
                        state.update(status="partial", notes=["Latest publication batch, deterministic first-document sample; not representative topic coverage"])
                        for a in links[:count]:
                            try:
                                url = urljoin(base, a["href"])
                                index, _ = fetch.get(url)
                                formats = BeautifulSoup(index, "html.parser").select("a[href]")
                                xml = next((urljoin(url + "/", x["href"]) for x in formats if ".xml" in x["href"].lower() or x.get_text(strip=True).upper() == "XML"), url + "/document.xml")
                                body, _ = fetch.get(xml)
                                doc = parse_epo(body, xml, pub_date)
                                emit({**doc, "url": xml, "kind": "patent"}, body)
                            except Exception as e:
                                failed(e)
                elif source["kind"] == "bls":
                    for series in source["series"]:
                        try:
                            url = "https://api.bls.gov/publicAPI/v2/timeseries/data/" + series["id"]
                            raw, _ = fetch.get(url)
                            payload = json.loads(raw)
                            if payload.get("status") != "REQUEST_SUCCEEDED":
                                raise ValueError("BLS request not successful")
                            rows, missing = [], []
                            for group in payload.get("Results", {}).get("series", []):
                                for point in group.get("data", []):
                                    period = point["period"]
                                    if not re.fullmatch(r"M(?:0[1-9]|1[0-2])", period):
                                        continue
                                    when = f"{point['year']}-{period[1:]}-01"
                                    if when <= as_of:
                                        if point["value"] in {"-", ".", "", "(NA)"}:
                                            missing.append({"date": when, "footnotes": point.get("footnotes", [])})
                                            continue
                                        rows.append({"date": when, "series": series["id"], "value": float(point["value"]),
                                            "unit": series["unit"], "footnotes": point.get("footnotes", [])})
                            rows.sort(key=lambda r: r["date"])
                            if not rows:
                                raise ValueError("No usable BLS observations")
                            emit({"url": url, "title": series["name"], "published_at": now()[:10],
                                "kind": "macro", "topics": ["macro"], "coverage": "selected_series_current_vintage",
                                "text": dumps({"series": series, "date_basis": "Observation month is not publication date; current retrieved vintage", "observations": rows, "missing_observations": missing}),
                                "metadata": {"observations": rows, "point_in_time_certified": False,
                                    "missing_observations": missing, "date_basis": "retrieval_date", "retrieved_vintage": now()}}, raw)
                            if missing:
                                state["notes"].append(f"{series['id']}: {len(missing)} unavailable monthly values retained as gaps, never zero-filled")
                        except Exception as e:
                            failed(e)
                elif source["kind"] == "treasury":
                    year = as_of[:4]
                    url = "https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml"
                    raw, _ = fetch.get(url, params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": year})
                    root = ET.fromstring(raw)
                    rows = []
                    for entry in root.iter():
                        if local_name(entry.tag) == "properties":
                            record = {local_name(n.tag): n.text for n in entry}
                            when = (record.get("NEW_DATE") or "")[:10]
                            if when and when <= as_of:
                                for tenor in ["BC_3MONTH", "BC_2YEAR", "BC_10YEAR", "BC_30YEAR"]:
                                    if record.get(tenor):
                                        rows.append({"date": when, "series": tenor, "value": float(record[tenor]), "unit": "percent"})
                    if not rows:
                        raise ValueError("Treasury response contains no observations")
                    published = max(r["date"] for r in rows)
                    emit({"url": url + f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}", "title": "美國公債殖利率 · 官方日資料",
                        "text": dumps({"unit": "percent", "observations": rows[-240:]}), "published_at": published,
                        "kind": "macro", "topics": ["macro"], "coverage": "selected_series_recent_observations",
                        "metadata": {"observations": rows, "vintage": now(), "point_in_time_certified": False}}, raw)
                elif source["kind"] == "fred":
                    for series in source["series"]:
                        try:
                            url = "https://api.stlouisfed.org/fred/series/observations"
                            raw, _ = fetch.get(url, params={"series_id": series, "api_key": project.secrets[key], "file_type": "json",
                                "observation_start": (date.fromisoformat(as_of) - timedelta(days=730)).isoformat(),
                                "realtime_start": as_of, "realtime_end": as_of})
                            observations = json.loads(raw).get("observations", [])
                            rows = [{"date": p["date"], "value": float(p["value"]), "series": series} for p in observations if p["value"] != "." and p["date"] <= as_of]
                            if not rows:
                                raise ValueError("No FRED observations")
                            emit({"url": f"https://fred.stlouisfed.org/series/{series}", "title": f"FRED / ALFRED · {series}",
                                "text": dumps({"series": series, "vintage": as_of, "observations": rows}), "published_at": as_of,
                                "kind": "macro", "topics": ["macro"], "coverage": "selected_series",
                                "metadata": {"observations": rows, "vintage": as_of, "point_in_time_certified": True}}, raw)
                        except Exception as e:
                            failed(e)
                elif source["kind"] == "odp_catalog":
                    raw, _ = fetch.get("https://api.uspto.gov/api/v1/datasets/products/search", headers={"x-api-key": project.secrets[key]})
                    state.update(status="catalog_only", notes=["Product catalog archived. Import selected authorized patent XML with import-file; bulk downloader not enabled."])
                    state["catalog_raw_path"] = store.blob(raw)
                else:
                    state.update(status="unsupported", notes=["Collector not implemented"])
            except Exception as e:
                failed(e)
            finally:
                store.save_run(run)
                print(f"  {state['status']}: {state['fetched']} documents, {state['new']} new", flush=True)
        run["completed_at"] = now()
        run["status"] = "complete" if all(s["status"] == "complete" for s in run["sources"]) else "partial"
        store.save_run(run)
        return run
    finally:
        fetch.close()
        store.close()
