"""Official TWSE and TPEx market, revenue and material-information collectors."""
from __future__ import annotations

import json
import re
import statistics
from datetime import date

from .core import dumps, now
from .tipo import roc_date


MARKETS = {
    "TWSE": "上市",
    "TPEx": "上櫃",
}


def _clean(row: dict) -> dict:
    return {str(key).strip(): value for key, value in row.items()}


def _number(value):
    text = str(value or "").strip().replace(",", "").replace("+", "")
    if text in {"", "--", "---", "-", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _month(value: str) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) not in {5, 6}:
        raise ValueError("Unrecognized ROC month")
    width = len(text) - 2
    year, month = int(text[:width]) + 1911, int(text[width:])
    return date(year, month, 1).isoformat()


def _company_map(project):
    return {str(code): company["ticker"] for company in project.companies for code in company.get("local_codes", [])}


def parse_market_rows(payload, market: str, company_codes: dict, as_of: str) -> dict:
    if not isinstance(payload, list):
        raise ValueError("Unexpected Taiwan market schema")
    parsed = []
    for original in payload:
        row = _clean(original)
        code = str(row.get("Code") or row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        raw_date = row.get("Date")
        try:
            when = roc_date(raw_date)
        except ValueError:
            continue
        if when > as_of:
            continue
        close = _number(row.get("ClosingPrice") if market == "TWSE" else row.get("Close"))
        change = _number(row.get("Change"))
        value = _number(row.get("TradeValue") if market == "TWSE" else row.get("TransactionAmount"))
        volume = _number(row.get("TradeVolume") if market == "TWSE" else row.get("TradingShares"))
        if close is None:
            continue
        parsed.append({"code": code, "ticker": company_codes.get(code),
            "name": str(row.get("Name") or row.get("CompanyName") or "").strip(),
            "date": when, "close": close, "change": change, "trade_value": value, "volume": volume})
    if not parsed:
        raise ValueError("Taiwan market response contains no usable equities")
    latest = max(row["date"] for row in parsed)
    parsed = [row for row in parsed if row["date"] == latest]
    advances = sum((row["change"] or 0) > 0 for row in parsed)
    declines = sum((row["change"] or 0) < 0 for row in parsed)
    dashboard = {"market": market, "market_name": MARKETS[market], "date": latest, "companies": len(parsed),
        "trade_value": sum(row["trade_value"] or 0 for row in parsed),
        "trade_volume": sum(row["volume"] or 0 for row in parsed),
        "advances": advances, "declines": declines, "unchanged": len(parsed) - advances - declines,
        "watchlist": sorted([row for row in parsed if row["ticker"]], key=lambda row: row["ticker"]),
        "turnover_leaders": sorted(parsed, key=lambda row: row["trade_value"] or 0, reverse=True)[:15]}
    return dashboard


def taiwan_market(project, fetch, store, source, as_of, cap, emit, state):
    company_codes = _company_map(project)
    state["discovered"] = len(source["endpoints"])
    for endpoint in source["endpoints"][:cap]:
        raw, _ = fetch.get(endpoint["url"])
        dashboard = parse_market_rows(json.loads(raw), endpoint["market"], company_codes, as_of)
        market, when = endpoint["market"], dashboard["date"]
        observations = [
            {"economy": "TWN", "economy_name": "台灣", "date": when, "series": f"{market}_TRADE_VALUE",
                "series_name": f"{market} market turnover", "value": dashboard["trade_value"], "unit": "TWD"},
            {"economy": "TWN", "economy_name": "台灣", "date": when, "series": f"{market}_ADVANCE_DECLINE",
                "series_name": f"{market} advances minus declines", "value": dashboard["advances"] - dashboard["declines"], "unit": "companies"},
        ]
        emit({"url": endpoint["url"], "stable_id": f"{market}-market-{when}",
            "title": f"台灣{MARKETS[market]}市場日行情 · {when}", "published_at": when,
            "kind": "macro", "topics": ["macro"], "coverage": "all_equity_daily_snapshot",
            "entities": [row["ticker"] for row in dashboard["watchlist"]],
            "text": dumps({"dashboard": dashboard, "observations": observations}),
            "metadata": {"dashboard": dashboard, "observations": observations,
                "retrieved_vintage": now(), "point_in_time_certified": False}}, raw)
    state["notes"].append("官方當日上市／上櫃全市場快照；休市日可能仍回傳最近交易日，數值未回填為零。")


def parse_revenue_rows(payload, market: str, company_codes: dict, as_of: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected MOPS revenue schema")
    parsed = []
    for original in payload:
        row = _clean(original)
        code = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        try:
            period = _month(row.get("資料年月"))
            filed = roc_date(row.get("出表日期") or row.get("Date"))
        except ValueError:
            continue
        if filed > as_of:
            continue
        parsed.append({"market": market, "code": code, "ticker": company_codes.get(code),
            "name": str(row.get("公司名稱") or row.get("CompanyName") or "").strip(),
            "industry": str(row.get("產業別") or "").strip(), "period": period, "filed": filed,
            "revenue": _number(row.get("營業收入-當月營收")),
            "previous_revenue": _number(row.get("營業收入-上月營收")),
            "prior_year_revenue": _number(row.get("營業收入-去年當月營收")),
            "mom_pct": _number(row.get("營業收入-上月比較增減(%)")),
            "yoy_pct": _number(row.get("營業收入-去年同月增減(%)")),
            "ytd_revenue": _number(row.get("累計營業收入-當月累計營收")),
            "prior_ytd_revenue": _number(row.get("累計營業收入-去年累計營收")),
            "ytd_yoy_pct": _number(row.get("累計營業收入-前期比較增減(%)")),
            "note": str(row.get("備註") or "").strip()})
    return parsed


def _revenue_financial(row: dict, url: str) -> dict:
    period = row["period"]
    observations = []
    for concept, value, unit in [
        ("MonthlyRevenue", row["revenue"], "TWD thousands"),
        ("MonthlyRevenueMoMGrowth", row["mom_pct"], "percent"),
        ("MonthlyRevenueYoYGrowth", row["yoy_pct"], "percent"),
        ("YearToDateRevenue", row["ytd_revenue"], "TWD thousands"),
        ("YearToDateRevenueYoYGrowth", row["ytd_yoy_pct"], "percent")]:
        if value is not None:
            observations.append({"concept": concept, "start": period, "end": period,
                "val": value, "unit": unit, "filed": row["filed"], "form": "MOPS monthly revenue"})
    return {"url": url, "stable_id": f"{row['market']}-revenue-{row['period'][:7]}-{row['code']}",
        "title": f"{row['ticker']} · {row['period'][:7]} 月營收", "published_at": row["filed"],
        "kind": "financial", "topics": [], "coverage": "official_monthly_revenue_fields",
        "entities": [row["ticker"]], "text": dumps({"company": row, "observations": observations}),
        "metadata": {"observations": observations, "market": row["market"], "code": row["code"],
            "period": row["period"], "company_name": row["name"], "retrieved_vintage": now(),
            "mapping_status": "official_local_code"}}


def taiwan_revenue(project, fetch, store, source, as_of, cap, emit, state):
    company_codes = _company_map(project)
    datasets = []
    for endpoint in source["endpoints"]:
        raw, _ = fetch.get(endpoint["url"])
        store.blob(raw)
        rows = parse_revenue_rows(json.loads(raw), endpoint["market"], company_codes, as_of)
        if rows:
            latest = max(row["period"] for row in rows)
            rows = [row for row in rows if row["period"] == latest]
        datasets.append((endpoint, raw, rows))
    state["discovered"] = sum(len(rows) for _, _, rows in datasets)
    candidates = []
    for endpoint, raw, rows in datasets:
        values = [row["yoy_pct"] for row in rows if row["yoy_pct"] is not None]
        if not values:
            continue
        market, period = endpoint["market"], rows[0]["period"]
        dashboard = {"market": market, "market_name": MARKETS[market], "period": period,
            "filed": max(row["filed"] for row in rows), "companies": len(rows),
            "median_yoy_pct": statistics.median(values), "positive_yoy": sum(value > 0 for value in values),
            "negative_yoy": sum(value < 0 for value in values),
            "leaders": sorted(rows, key=lambda row: row["yoy_pct"] if row["yoy_pct"] is not None else float("-inf"), reverse=True)[:15],
            "laggards": sorted(rows, key=lambda row: row["yoy_pct"] if row["yoy_pct"] is not None else float("inf"))[:15]}
        observations = [{"economy": "TWN", "economy_name": "台灣", "date": period,
            "series": f"{market}_REVENUE_MEDIAN_YOY", "series_name": f"{market} monthly revenue median YoY",
            "value": dashboard["median_yoy_pct"], "unit": "percent"}]
        candidates.append((0, {"url": endpoint["url"], "stable_id": f"{market}-revenue-breadth-{period[:7]}",
            "title": f"台灣{MARKETS[market]}公司月營收廣度 · {period[:7]}", "published_at": dashboard["filed"],
            "kind": "macro", "topics": ["macro"], "coverage": "all_companies_monthly_revenue_breadth",
            "text": dumps({"dashboard": dashboard, "observations": observations}),
            "metadata": {"dashboard": dashboard, "observations": observations, "retrieved_vintage": now(),
                "point_in_time_certified": False}}, raw))
        for row in rows:
            if row["ticker"]:
                candidates.append((1, _revenue_financial(row, endpoint["url"]), raw))
    existing = {(doc.get("metadata", {}).get("market"), doc.get("metadata", {}).get("code"), doc.get("metadata", {}).get("period"))
        for doc in store.documents() if doc["source_id"] == source["id"]}
    candidates.sort(key=lambda item: (item[0],
        0 if (item[1].get("metadata", {}).get("market"), item[1].get("metadata", {}).get("code"), item[1].get("metadata", {}).get("period")) not in existing else 1,
        item[1]["stable_id"]))
    for _, doc, raw in candidates[:cap]:
        emit(doc, raw)
    if len(candidates) > cap:
        state.update(status="partial")
        state["notes"].append(f"本次處理 {cap}/{len(candidates)} 份廣度／觀察名單公司文件；未處理公司依月別與代號在後續執行接續。")
    state["notes"].append("月營收金額依 MOPS 欄位以新台幣仟元保存；成長率、產業分類與公司備註保持官方值。")


def parse_disclosure_rows(payload, market: str, company_codes: dict, as_of: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected material-information schema")
    rows = []
    for original in payload:
        row = _clean(original)
        code = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
        try:
            published = roc_date(row.get("發言日期"))
        except ValueError:
            continue
        if published > as_of:
            continue
        rows.append({"market": market, "code": code, "ticker": company_codes.get(code),
            "name": str(row.get("公司名稱") or row.get("CompanyName") or "").strip(),
            "published_at": published, "time": str(row.get("發言時間") or "").strip(),
            "subject": str(row.get("主旨") or "").strip(), "rule": str(row.get("符合條款") or "").strip(),
            "event_date": str(row.get("事實發生日") or "").strip(), "explanation": str(row.get("說明") or "").strip()})
    return rows


def taiwan_disclosures(project, fetch, store, source, as_of, cap, emit, state):
    company_codes = _company_map(project)
    candidates = []
    for endpoint in source["endpoints"]:
        raw, _ = fetch.get(endpoint["url"])
        store.blob(raw)
        for row in parse_disclosure_rows(json.loads(raw), endpoint["market"], company_codes, as_of):
            candidates.append((row, endpoint["url"], raw))
    candidates.sort(key=lambda item: (item[0]["published_at"], item[0]["time"], item[0]["market"], item[0]["code"]), reverse=True)
    state["discovered"] = len(candidates)
    for row, url, raw in candidates[:cap]:
        subject = row["subject"] or "公司重大訊息"
        emit({"url": url, "stable_id": f"{row['market']}-{row['published_at']}-{row['time']}-{row['code']}-{subject}",
            "title": f"{row['ticker'] or row['code']} · {subject}", "published_at": row["published_at"],
            "kind": "disclosure", "coverage": "official_material_information", "entities": [row["ticker"]] if row["ticker"] else [],
            "text": dumps(row), "metadata": {"market": row["market"], "code": row["code"],
                "event_date": row["event_date"], "rule": row["rule"], "retrieved_vintage": now()}}, raw)
    if len(candidates) > cap:
        state.update(status="partial")
        state["notes"].append(f"官方最新頁共有 {len(candidates)} 則，本次依時間處理前 {cap} 則；完整原始回應已封存。")
    state["notes"].append("公開資訊觀測站重大訊息是事件線索；內容需結合財報、公告附件與後續結果覆核。")
