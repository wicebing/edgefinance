"""Official, keyless cross-economy macro and foreign-exchange collectors."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from urllib.parse import urlencode

from .core import dumps, now


def _iso_date(value: str) -> str:
    return date.fromisoformat(str(value)[:10]).isoformat()


def parse_world_bank(payload, economy_ids: set[str], series: dict, as_of: str) -> tuple[list[dict], dict]:
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict) or not isinstance(payload[1], list):
        raise ValueError("Unexpected World Bank response schema")
    meta, rows = payload
    observations = []
    for row in rows:
        code = str(row.get("countryiso3code") or "")
        year = str(row.get("date") or "")
        value = row.get("value")
        if code not in economy_ids or not year.isdigit() or value is None:
            continue
        when = f"{int(year):04d}-01-01"
        if when > as_of:
            continue
        observations.append({"economy": code, "economy_name": row.get("country", {}).get("value", code),
            "date": when, "series": series["id"], "series_name": series["name"],
            "value": float(value), "unit": series["unit"], "status": row.get("obs_status") or ""})
    observations.sort(key=lambda point: (point["economy"], point["date"]))
    return observations, meta


def world_bank(project, fetch, store, source, as_of, cap, emit, state):
    economy_ids = {economy["id"] for economy in project.economies if economy.get("world_bank", True)}
    indicators = source["indicators"]
    state["discovered"] = len(indicators)
    if len(indicators) > cap:
        state.update(status="partial")
        state["notes"].append("Configured item cap; remaining indicator definitions were not requested")
    countries = ";".join(sorted(economy_ids))
    for series in indicators[:cap]:
        url = f"https://api.worldbank.org/v2/country/{countries}/indicator/{series['id']}"
        params = {"format": "json", "mrv": int(source.get("recent_values", 5)), "per_page": 20000}
        raw, _ = fetch.get(url, params=params)
        observations, meta = parse_world_bank(json.loads(raw), economy_ids, series, as_of)
        if not observations:
            raise ValueError(f"World Bank returned no observations for {series['id']}")
        released = _iso_date(meta.get("lastupdated") or now())
        public = url + "?" + urlencode(params)
        emit({"url": public, "stable_id": series["id"], "title": f"全球主要經濟體 · {series['name']}",
            "published_at": released, "kind": "macro", "topics": ["macro"],
            "coverage": "selected_economies_recent_observations",
            "text": dumps({"indicator": series, "source_last_updated": released,
                "current_vintage": True, "observations": observations}),
            "metadata": {"observations": observations, "retrieved_vintage": now(),
                "source_last_updated": released, "point_in_time_certified": False}}, raw)
    state["notes"].append(
        f"{len(economy_ids)} 個主要經濟體、每指標最近 {source.get('recent_values', 5)} 個非空值；World Bank 現行版本會修訂，非歷史當時版本。")


def parse_ecb_csv(raw: bytes, currencies: set[str], as_of: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        currency = str(row.get("CURRENCY") or "").strip()
        when = str(row.get("TIME_PERIOD") or "")[:10]
        value = str(row.get("OBS_VALUE") or "").strip()
        if currency not in currencies or not value or when > as_of:
            continue
        date.fromisoformat(when)
        rows.append({"economy": currency, "economy_name": f"{currency} / EUR",
            "date": when, "series": f"ECB_EXR_{currency}_PER_EUR",
            "series_name": f"{currency} per EUR", "value": float(value),
            "unit": row.get("UNIT") or f"{currency} per EUR", "status": row.get("OBS_STATUS") or ""})
    return sorted(rows, key=lambda point: (point["series"], point["date"]))


def ecb_fx(project, fetch, store, source, as_of, cap, emit, state):
    currencies = set(source["currencies"])
    start = (date.fromisoformat(as_of) - timedelta(days=int(source.get("lookback_days", 120)))).isoformat()
    key = "+".join(sorted(currencies))
    url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{key}.EUR.SP00.A"
    params = {"startPeriod": start, "endPeriod": as_of, "format": "csvdata"}
    raw, _ = fetch.get(url, params=params)
    observations = parse_ecb_csv(raw, currencies, as_of)
    if not observations:
        raise ValueError("ECB returned no usable exchange-rate observations")
    latest = max(point["date"] for point in observations)
    by_currency = {}
    for point in observations:
        by_currency.setdefault(point["economy"], []).append(point)
    model_summary = []
    for currency, points in sorted(by_currency.items()):
        points.sort(key=lambda point: point["date"])
        first, last = points[0], points[-1]
        model_summary.append({"currency": currency, "start_date": first["date"], "start_value": first["value"],
            "end_date": last["date"], "end_value": last["value"],
            "period_change_pct": (last["value"] / first["value"] - 1) * 100 if first["value"] else None,
            "unit": last["unit"]})
    emit({"url": url + "?" + urlencode(params), "stable_id": "ecb-reference-rates",
        "title": "ECB 歐元參考匯率 · 主要貨幣", "published_at": latest,
        "kind": "macro", "topics": ["macro"], "coverage": "selected_daily_reference_rates",
        # Preserve the complete series in metadata for charts; send a compact,
        # deterministic window summary to semantic analysis instead of thousands
        # of repetitive daily rows.
        "text": dumps({"base": "EUR", "current_vintage": True, "window_summary": model_summary}),
        "metadata": {"observations": observations, "retrieved_vintage": now(),
            "point_in_time_certified": False}}, raw)
    state["discovered"] = len(currencies)
    state["notes"].append(f"{len(currencies)} 種貨幣對歐元、最近 {source.get('lookback_days', 120)} 天；為 ECB 參考匯率，不是可成交報價。")
