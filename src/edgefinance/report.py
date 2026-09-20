from __future__ import annotations

import gzip
import json
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .analysis import CodexError, evidence_bundle, synthesize, synthesize_monthly_feature
from .core import PACKAGE, Project, digest, dumps, jsonfile, now, public_url, readjson, write
from .opportunity_data import patent_landscape


def build_report(project: Project, as_of: str, use_codex=True):
    store = project.store()
    try:
        evidence, summaries, coverage = evidence_bundle(project, store, as_of)
        docs = store.documents(as_of, latest_only=True)
        stored_reports = store.reports()
        previous = next((r for r in stored_reports if r["as_of"] < as_of), None)
        indicator_names = {indicator["id"]: indicator["name"] for source in project.sources
            for indicator in source.get("indicators", [])}
        def display_title(document):
            if document["source_id"] == "world-bank-major-economies":
                points = document.get("metadata", {}).get("observations", [])
                if points and points[0].get("series") in indicator_names:
                    return f"全球主要經濟體 · {indicator_names[points[0]['series']]}"
            return document["title"]
        display_titles = {document["id"]: display_title(document) for document in docs}
        runs = [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM runs ORDER BY rowid DESC")]
        runs = [r for r in runs if r.get("as_of", "9999") <= as_of]
        run = runs[0] if runs else None
        synthesis, execution, error = None, None, None
        if evidence and use_codex:
            try:
                output = synthesize(project, evidence, summaries, previous, as_of)
                synthesis, execution = output["result"], output["execution"]
            except Exception as e:
                error = str(e) if type(e).__name__ == "CodexError" else f"{type(e).__name__}: synthesis validation failed"
                if previous:
                    raise CodexError("New synthesis failed; previous report/site preserved. See local logs and resume.") from e
        if not synthesis:
            synthesis = {"summary": "資料庫已保存來源與取得紀錄。完整研究論點將在 Codex 分段理解及引用驗證完成後更新；目前不據此產生投資排名。",
                "theses": [], "risks": [{"horizon_days": h, "title": f"{h} 天風險 · 待完成證據分析", "assessment": "unknown",
                    "rationale": "目前不足以提出有證據的風險判斷。", "evidence_ids": [], "transmission": "待驗證資料補齊後分析。",
                    "triggers": [], "easing_conditions": [], "limitations": ["尚未完成跨來源分析"]} for h in [14, 30, 90, 180]],
                "next_week": ["補齊資料來源權限，完成待讀文件並覆核核心引用。"], "limitations": [error or "尚未執行或完成 Codex 綜合分析"]}
        evidence_map = {e["id"]: e for e in evidence}
        for thesis in synthesis["theses"]:
            thesis["id"] = "T-" + digest(thesis["topic_id"] + "|" + "|".join(sorted(thesis["company_ids"])))[:12]
            supported = [evidence_map[e] for e in thesis["evidence_ids"]]
            origins = {e["origin"] for e in supported}
            kinds = {e["kind"] for e in supported}
            thesis["gate"] = "multiple_source_types" if len(origins) >= 2 and len(kinds) >= 2 and "financial" in kinds else "exploration"
            thesis["status"] = "needs_review"
            thesis["valuation_status"] = "missing_price_and_valuation"
            thesis["evidence_count"] = len(supported)
            thesis["independent_origins"] = len(origins)
            old = next((t for t in (previous or {}).get("theses", []) if t["id"] == thesis["id"]), None)
            thesis["change"] = "new" if not old else ("updated" if old["statement"] != thesis["statement"] else "unchanged")
        # Stable topic/company keys must not silently collapse different theses.
        if len({t["id"] for t in synthesis["theses"]}) != len(synthesis["theses"]):
            for n, thesis in enumerate(synthesis["theses"]):
                thesis["id"] += f"-{n + 1}"
        for risk in synthesis["risks"]:
            risk["due_at"] = (date.fromisoformat(as_of) + timedelta(days=risk["horizon_days"])).isoformat()
            risk["probability"] = None
        errors = []
        if run and run.get("status") != "complete":
            errors.append("部分來源受金鑰、抽樣範圍、筆數上限或連線狀態限制，非完整市場覆蓋。")
        if coverage["pending_chunks"]:
            errors.append(f"尚有 {coverage['pending_chunks']} 個資料分段未完成理解；本期分析只使用已完成且引用通過核對的部分。")
        errors.extend(synthesis["limitations"])
        errors += ["核心語意與公司歸屬仍需人工覆核；引用文字比對不等於獨立證實。",
            "尚無完整行情、公司行動與估值資料，不提供買進排序、目標價或回測獲利宣稱。"]
        report_id = as_of + "-" + uuid.uuid4().hex[:8]
        timeline = [{"date": d["published_at"][:10], "title": display_titles[d["id"]], "kind": d["kind"], "url": d["url"],
            "source_id": d["source_id"], "first_seen_at": d["first_seen_at"]} for d in docs]
        observations = []
        for d in docs:
            if d["kind"] == "macro":
                for point in d.get("metadata", {}).get("observations", []):
                    if "series" in point:
                        normalized = {**point, "source_url": d["url"], "vintage": d["first_seen_at"]}
                        if point["series"] in indicator_names:
                            normalized["series_name"] = indicator_names[point["series"]]
                        observations.append(normalized)
        # Multiple vintages may coexist locally. Plot only the latest observed version of each point.
        unique_points = {}
        for p in sorted(observations, key=lambda p: p["vintage"]):
            unique_points[(p.get("economy", ""), p["series"], p["date"])] = p
        current_points = list(unique_points.values())
        global_economy_ids = {economy["id"] for economy in project.economies}
        latest_global = {}
        for point in sorted(current_points, key=lambda p: p["date"]):
            if point.get("economy") in global_economy_ids:
                latest_global[(point["economy"], point["series"])] = point
        taiwan_markets, taiwan_revenue = {}, {}
        for d in docs:
            dashboard = d.get("metadata", {}).get("dashboard")
            if not dashboard:
                continue
            if d["source_id"] == "taiwan-market":
                old = taiwan_markets.get(dashboard["market"])
                if not old or dashboard["date"] > old["date"]:
                    taiwan_markets[dashboard["market"]] = dashboard
            elif d["source_id"] == "taiwan-revenue" and d["kind"] == "macro":
                old = taiwan_revenue.get(dashboard["market"])
                if not old or dashboard["period"] > old["period"]:
                    taiwan_revenue[dashboard["market"]] = dashboard
        taiwan_disclosures = [{"title": d["title"], "published_at": d["published_at"], "url": d["url"],
            "entities": d["entities"], "market": d.get("metadata", {}).get("market"),
            "code": d.get("metadata", {}).get("code"), "event_date": d.get("metadata", {}).get("event_date")}
            for d in docs if d["source_id"] == "taiwan-disclosures"]
        latest_states = {}
        for prior_run in runs:
            for state in prior_run.get("sources", []):
                latest_states.setdefault(state["id"], {**state, "last_run_as_of": prior_run["as_of"]})
        source_states = list(latest_states.values())
        observed_sources = {s["id"] for s in source_states}
        source_states = source_states + [{"id": s["id"], "name": s["name"], "status": "not_run", "fetched": 0,
            "new": 0, "failed": 0, "discovered": None, "bounded": True, "notes": ["Not selected in latest collection run"], "docs": s.get("docs", "")}
            for s in project.sources if s.get("enabled") and s["id"] not in observed_sources]
        configured_sources = {source["id"]: source for source in project.sources}
        for source_state in source_states:
            if source_state["id"] in configured_sources:
                source_state["name"] = configured_sources[source_state["id"]]["name"]
        patents = patent_landscape(project, as_of)
        patent_updates = patents["entries"]
        patent_keys = {(item.get("publication_number"), item.get("published_at")) for item in patent_updates}
        patent_since = (date.fromisoformat(as_of) - timedelta(days=35)).isoformat()
        for d in docs:
            meta = d.get("metadata", {})
            key = (meta.get("publication_number"), d["published_at"])
            if d["origin"] == "uspto" and key not in patent_keys and meta.get("patent_event") in {"new_grant", "other_grant_publication"} and patent_since <= d["published_at"] <= as_of:
                patent_updates.append({"authority": "USPTO", "source_id": d["source_id"],
                    "publication_number": meta["publication_number"], "kind_code": meta["kind_code"], "event": meta["patent_event"],
                    "published_at": d["published_at"], "url": d["url"], "detail_status": "complete", "title": d["title"],
                    "assignees": meta.get("assignees", []), "topics": d.get("topics", []), "companies": d.get("entities", [])})
                patent_keys.add(key)
        def latest_dashboard(source_id):
            candidates = [d for d in docs if d["source_id"] == source_id and d.get("metadata", {}).get("dashboard")]
            if not candidates:
                return {}
            return max(candidates, key=lambda d: (d["published_at"], d["first_seen_at"]))["metadata"]["dashboard"]
        opportunities = {"taiwan": latest_dashboard("taiwan-opportunities"),
            "sec": latest_dashboard("sec-opportunities"),
            "crypto": latest_dashboard("binance-opportunities"),
            "patents": patents["organizations"]}
        prior_reports, prior_dates = [], set()
        for item in stored_reports:
            if item["as_of"] < as_of and item["as_of"] not in prior_dates:
                prior_reports.append(item)
                prior_dates.add(item["as_of"])
        weekly_comparisons = []
        for thesis in synthesis["theses"]:
            matches = []
            for prior_report in prior_reports[:12]:
                for old in prior_report.get("theses", []):
                    shared = sorted(set(thesis["company_ids"]) & set(old.get("company_ids", [])))
                    if old.get("topic_id") == thesis["topic_id"] or shared:
                        matches.append({"report_id": prior_report["id"], "as_of": prior_report["as_of"],
                            "title": old["title"], "statement": old["statement"], "gate": old.get("gate"),
                            "shared_companies": shared})
                        break
            weekly_comparisons.append({"thesis_id": thesis["id"], "title": thesis["title"],
                "status": "new" if not matches else ("continued" if thesis["statement"] == matches[0]["statement"] else "changed"),
                "history": matches})
        risk_history = [{"horizon_days": risk["horizon_days"], "current": risk["assessment"],
            "history": [{"report_id": item["id"], "as_of": item["as_of"], "assessment": old["assessment"], "title": old["title"]}
                for item in prior_reports[:12] for old in item.get("risks", []) if old["horizon_days"] == risk["horizon_days"]][:8]}
            for risk in synthesis["risks"]]
        monthly_feature = synthesize_monthly_feature(project, evidence, stored_reports, as_of) if use_codex else None
        report = {"schema_version": 2, "id": report_id, "as_of": as_of, "generated_at": now(), "snapshot_frozen_at": now(),
            "decision_available_at": now(), "status": "partial" if errors else "draft", "review_status": "pending",
            "summary": synthesis["summary"], "theses": synthesis["theses"], "risks": synthesis["risks"],
            "document_summaries": summaries,
            "patent_updates": patent_updates,
            "patent_landscape": {key: value for key, value in patents.items() if key != "entries"},
            "thesis_changes": [{"id": t["id"], "title": t["title"], "previous_report_id": previous["id"],
                "status": "not_selected_this_report", "reason": "本期綜合未選入此論點；尚未確認失效，保留前版供追蹤。"}
                for t in (previous or {}).get("theses", []) if t["id"] not in {x["id"] for x in synthesis["theses"]}],
            "next_week": synthesis["next_week"], "limitations": list(dict.fromkeys(errors)), "coverage": coverage,
            "sources": source_states, "source_manifest_id": (run or {}).get("id"),
            "evidence": [{**{k: v for k, v in e.items() if k not in {"quote", "title"}},
                "title": display_titles.get(e["document_version"], e["title"])} for e in evidence],
            "documents": [{**{k: d.get(k) for k in ["id", "document_id", "url", "kind", "published_at", "first_seen_at", "source_id", "coverage", "entities", "topics", "content_hash"]},
                "title": display_titles[d["id"]]} for d in docs],
            "timeline": timeline, "observations": current_points, "companies": project.companies, "topics": project.topics,
            "economies": project.economies, "global_latest": sorted(latest_global.values(), key=lambda p: (p["series"], p["economy"])),
            "opportunities": opportunities,
            "weekly_comparisons": weekly_comparisons, "risk_history": risk_history,
            "monthly_feature": monthly_feature,
            "taiwan": {"markets": sorted(taiwan_markets.values(), key=lambda row: row["market"]),
                "revenue": sorted(taiwan_revenue.values(), key=lambda row: row["market"]),
                "disclosures": sorted(taiwan_disclosures, key=lambda row: row["published_at"], reverse=True)[:50]},
            "previous_report_id": previous["id"] if previous else None, "execution": execution,
            "financials": [{"ticker": ticker, "rows": d.get("metadata", {}).get("observations", []),
                "url": d["url"], "source_id": d["source_id"], "filed_at": d["published_at"], "retrieved_at": d["first_seen_at"]}
                for d in docs if d["kind"] == "financial" for ticker in d["entities"]],
            "outcomes": [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM outcomes")],
            "checks": [{"id": f"{report_id}-risk-{r['horizon_days']}", "title": r["title"], "due_at": r["due_at"],
                "definition": "；".join(r["triggers"]) or "尚未具備可檢驗的觸發條件", "status": "pending", "type": "risk_condition_review"} for r in synthesis["risks"]]}
        validate_report(report)
        # Verify locally retained evidence bytes before recording a report.
        for doc in docs:
            if digest(gzip.decompress((project.data / doc["raw_path"]).read_bytes())) != doc["raw_sha256"]:
                raise ValueError("Raw evidence checksum mismatch")
        store.save_report(report)
        return report
    finally:
        store.close()


def validate_report(report):
    if report.get("schema_version") not in {1, 2}:
        raise ValueError("Unsupported report schema")
    date.fromisoformat(report["as_of"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", report["id"]):
        raise ValueError("Invalid report identifier")
    for company in report["companies"]:
        if not re.fullmatch(r"[A-Z0-9.-]{1,20}", company["ticker"]):
            raise ValueError("Invalid public ticker")
    for topic in report["topics"]:
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", topic["id"]):
            raise ValueError("Invalid public topic identifier")
    evidence_ids = {e["id"] for e in report["evidence"]}
    if len(evidence_ids) != len(report["evidence"]):
        raise ValueError("Duplicate evidence ID")
    expected_horizons = [90, 180] if report["schema_version"] == 1 else [14, 30, 90, 180]
    if sorted(r["horizon_days"] for r in report["risks"]) != expected_horizons:
        raise ValueError("Risk horizons incomplete")
    for e in report["evidence"]:
        public_url(e["url"])
        if e["published_at"][:10] > report["as_of"]:
            raise ValueError("Post-cutoff evidence")
        if "quote" in e or "text" in e or "raw_path" in e:
            raise ValueError("Raw text is not allowed in public evidence")
    for thesis in report["theses"]:
        if not thesis["evidence_ids"] or not set(thesis["evidence_ids"] + thesis["counterevidence_ids"]) <= evidence_ids:
            raise ValueError("Dangling thesis citation")
    for risk in report["risks"]:
        if not set(risk["evidence_ids"]) <= evidence_ids:
            raise ValueError("Dangling risk citation")
    for doc in report["documents"]:
        public_url(doc["url"])
        if doc["published_at"][:10] > report["as_of"]:
            raise ValueError("Post-cutoff document")
    serialized = dumps(report)
    if re.search(r"mongodb(?:\+srv)?://|(?:sk-proj-|sk-live-)[A-Za-z0-9]|[?&](?:api_key|token|password)=", serialized, re.I):
        raise ValueError("Potential secret in public export")
    return True


def sparkline(points):
    if len(points) < 2:
        return ""
    ys = [float(p["value"]) for p in points]
    lo, hi = min(ys), max(ys)
    span = hi - lo or 1
    xs = [date.fromisoformat(p["date"]).toordinal() for p in points]
    duration = max(xs) - min(xs) or 1
    return " ".join(f"{(x - min(xs)) * 600 / duration:.1f},{135 - (v - lo) / span * 110:.1f}" for x, v in zip(xs, ys))


def render_site(project: Project, output: Path | None = None, from_public=False):
    public = project.root / "public-data" / "v1"
    public.mkdir(parents=True, exist_ok=True)
    if from_public:
        latest = readjson(public / "latest.json")
        manifest_path = (public / latest["manifest"]).resolve()
        if not manifest_path.is_relative_to(public.resolve()):
            raise ValueError("Invalid manifest path")
        for manifest_file in public.glob("releases/*/manifest.json"):
            manifest = readjson(manifest_file)
            paths = {item["path"] for item in manifest["files"]}
            if str((manifest_file.parent / "report.json").relative_to(public)).replace("\\", "/") not in paths:
                raise ValueError("Report missing from integrity manifest")
            for item in manifest["files"]:
                path = (public / item["path"]).resolve()
                if not path.is_relative_to(public.resolve()) or digest(path.read_bytes()) != item["sha256"]:
                    raise ValueError("Public release integrity check failed")
        if not manifest_path.is_file():
            raise ValueError("Missing latest manifest")
        reports = [readjson(p) for p in public.glob("releases/*/report.json")]
        for p in public.glob("releases/*/report.json"):
            if not (p.parent / "manifest.json").is_file():
                raise ValueError("Historical report has no integrity manifest")
        reports.sort(key=lambda r: r["generated_at"], reverse=True)
        current = next(r for r in reports if r["id"] == latest["release_id"])
    else:
        store = project.store()
        retained_reports = store.reports()
        store.close()
        if not retained_reports:
            raise ValueError("Create a report first")
        for report in retained_reports:
            validate_report(report)
        reports, seen_retained_dates = [], set()
        for report in retained_reports:
            if report["as_of"] not in seen_retained_dates:
                reports.append(report)
                seen_retained_dates.add(report["as_of"])
        current = reports[0]
        for report in reports:
            release_dir = public / "releases" / report["id"]
            if (release_dir / "manifest.json").exists():
                if readjson(release_dir / "report.json") != report:
                    raise ValueError("Frozen public report differs from retained report")
                for item in readjson(release_dir / "manifest.json")["files"]:
                    archived = (public / item["path"]).resolve()
                    if not archived.is_relative_to(public.resolve()) or digest(archived.read_bytes()) != item["sha256"]:
                        raise ValueError("Frozen release integrity failed")
                continue
            jsonfile(release_dir / "report.json", report)
            # Small by-purpose files are convenient for both the frontend and external tools.
            for name, value in [("overview", {k: report[k] for k in ["id", "as_of", "status", "summary", "coverage", "theses", "risks"]}),
                ("evidence", report["evidence"]), ("companies", report["companies"]), ("technologies", report["topics"]),
                ("patents", report.get("patent_updates", [])), ("economies", report.get("economies", [])),
                ("patent-landscape", report.get("patent_landscape", {})),
                ("history", {"weekly_comparisons": report.get("weekly_comparisons", []), "risk_history": report.get("risk_history", [])}),
                ("monthly-feature", report.get("monthly_feature") or {}),
                ("global", report.get("global_latest", [])), ("taiwan", report.get("taiwan", {})),
                ("opportunities", report.get("opportunities", {})), ("crypto", report.get("opportunities", {}).get("crypto", {}))]:
                jsonfile(release_dir / f"{name}.json", value)
            files = [{"path": str(p.relative_to(public)).replace("\\", "/"), "sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                for p in sorted(release_dir.glob("*.json")) if p.name != "manifest.json"]
            jsonfile(release_dir / "manifest.json", {"schema_version": 1, "release_id": report["id"], "as_of": report["as_of"], "files": files})
        jsonfile(public / "latest.json", {"schema_version": 1, "release_id": current["id"], "manifest": f"releases/{current['id']}/manifest.json"})
    for report in reports:
        validate_report(report)
    # Multiple same-day builds are revisions, not additional weekly editions.
    # Keep immutable releases available as JSON while showing only the newest
    # revision for each cutoff date in navigation and the archive.
    visible_reports, seen_dates = [], set()
    for historical in reports:
        if historical["as_of"] not in seen_dates:
            visible_reports.append(historical)
            seen_dates.add(historical["as_of"])
    reports = visible_reports
    output = (output or project.root / project.settings["site"]["output"]).resolve()
    if not output.is_relative_to(project.root) or output in {project.root, project.data}:
        raise ValueError("Site output must be a dedicated project subdirectory")
    if output.relative_to(project.root).parts[0] in {"config", "src", "tests", "docs", ".git", "scripts", "public-data", ".venv", "data", "work", "News Scrapping"}:
        raise ValueError("Site output cannot replace project inputs or retained data")
    final_output = output
    output = project.data / "site-builds" / uuid.uuid4().hex
    output.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(PACKAGE / "templates"), autoescape=select_autoescape(["html", "xml"]))
    env.globals["sparkline"] = sparkline
    env.filters["shortdate"] = lambda s: str(s)[:10]
    env.globals["labels"] = {"unknown": "資料不足", "low": "偏低", "moderate": "中等", "elevated": "偏高", "complete": "完成所選範圍",
        "partial": "部分完成", "needs_credentials": "待設定金鑰", "not_run": "尚未執行", "catalog_only": "僅資料目錄",
        "awaiting_download": "待放入下載檔案", "draft": "研究草稿"}
    template = env.get_template("page.html")
    series = {}
    for point in current.get("observations", []):
        label = point.get("series_name", point["series"])
        if point.get("economy"):
            label = f"{point.get('economy_name', point['economy'])} · {label}"
        series.setdefault(label, []).append(point)
    for points in series.values():
        points.sort(key=lambda p: p["date"])
    risk_series = {name: points for name, points in series.items()
        if not points[-1].get("economy") or points[-1].get("economy") == "TWN"}
    global_indicators = {}
    for point in current.get("global_latest", []):
        global_indicators.setdefault(point.get("series_name", point["series"]), []).append(point)
    podcasts_path = project.root / "public-media" / "podcasts.json"
    podcasts = readjson(podcasts_path) if podcasts_path.exists() else {
        "schema_version": 1, "show": {"name": "edgeFinance4Podcast", "language": "zh-Hant"}, "episodes": []}
    if podcasts_path.exists():
        from .media import validate_podcast_collection
        validate_podcast_collection(podcasts, project.root)
    common = {"report": current, "reports": reports, "series": risk_series, "podcasts": podcasts,
        "global_indicators": global_indicators, "project_name": "EdgeFinance"}
    pages = [("index.html", "home", None), ("opportunities.html", "opportunities", None),
        ("crypto.html", "crypto", None), ("global.html", "global", None), ("taiwan.html", "taiwan", None),
        ("research.html", "research", None), ("risks.html", "risks", None),
        ("patents.html", "patents", None), ("features.html", "features", None),
        ("podcast.html", "podcast", None), ("sources.html", "sources", None),
        ("archive.html", "archive", None), ("methodology.html", "methodology", None)]
    for company in current["companies"]:
        pages.append((f"company-{company['ticker']}.html", "company", company))
    for topic in current["topics"]:
        pages.append((f"technology-{topic['id']}.html", "technology", topic))
    for report in reports:
        filename = f"report-{report['id']}.html"
        write(output / filename, template.render(**{**common, "report": report}, page="weekly", entity=None))
    for filename, page, entity in pages:
        write(output / filename, template.render(**common, page=page, entity=entity))
    for p in (PACKAGE / "assets").iterdir():
        write(output / "assets" / p.name, p.read_bytes())
    for p in public.rglob("*.json"):
        write(output / "data" / "v1" / p.relative_to(public), p.read_bytes())
    public_media = project.root / "public-media"
    if public_media.exists():
        for p in public_media.rglob("*"):
            if p.is_file():
                write(output / "media" / p.relative_to(public_media), p.read_bytes())
    write(output / ".nojekyll", "")
    write(output / "404.html", template.render(**common, page="notfound", entity=None))
    if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > 800_000_000:
        raise ValueError("Site exceeds the 800 MB project budget")
    for p in output.rglob("*"):
        if p.is_file() and p.suffix in {".html", ".json", ".js", ".css"}:
            text = p.read_text(encoding="utf-8")
            if re.search(r"mongodb(?:\+srv)?://|[?&](?:api_key|password)=", text, re.I):
                raise ValueError("Secret-like content in generated site")
    backup = project.data / "site-backups" / uuid.uuid4().hex
    backup.parent.mkdir(parents=True, exist_ok=True)
    if final_output.exists():
        final_output.rename(backup)
    try:
        output.rename(final_output)
    except Exception:
        if backup.exists() and not final_output.exists():
            backup.rename(final_output)
        raise
    return final_output
