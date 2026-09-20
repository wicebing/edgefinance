"""Deterministic, public-data market screens.

These screens rank records for further research.  They deliberately avoid the
language and mechanics of portfolio recommendations: no target price, position
size, or order is produced.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date, datetime, timedelta, timezone

from .core import digest, dumps, now
from .tipo import roc_date


def _number(value):
    text = str(value or "").strip().replace(",", "").replace("+", "")
    if text in {"", "-", "--", "---", "N/A", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """Return deterministic 0..1 empirical ranks, including ties."""
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0][0]: 0.5}
    result = {}
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = ((i + j - 1) / 2) / (len(ordered) - 1)
        for key, _ in ordered[i:j]:
            result[key] = rank
        i = j
    return result


def _roc_month(value) -> str | None:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) not in {5, 6}:
        return None
    year_digits = len(text) - 2
    try:
        return f"{int(text[:year_digits]) + 1911:04d}-{int(text[year_digits:]):02d}"
    except ValueError:
        return None


def parse_tw_market(payload, market: str, as_of: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected Taiwan market schema")
    rows = []
    for item in payload:
        row = {str(k).strip(): v for k, v in item.items()}
        code = str(row.get("Code") or row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        try:
            when = roc_date(row.get("Date"))
        except ValueError:
            continue
        close = _number(row.get("ClosingPrice") if market == "TWSE" else row.get("Close"))
        if when > as_of or close is None:
            continue
        rows.append({"code": code, "market": market, "date": when,
            "name": str(row.get("Name") or row.get("CompanyName") or "").strip(),
            "close": close,
            "trade_value": _number(row.get("TradeValue") if market == "TWSE" else row.get("TransactionAmount")),
            "volume": _number(row.get("TradeVolume") if market == "TWSE" else row.get("TradingShares"))})
    if not rows:
        raise ValueError("Taiwan market screen contains no equities")
    latest = max(row["date"] for row in rows)
    return [row for row in rows if row["date"] == latest]


def parse_tw_revenue(payload, market: str, as_of: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected Taiwan revenue schema")
    rows = []
    for item in payload:
        row = {str(k).strip(): v for k, v in item.items()}
        code = str(row.get("公司代號") or row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        period = _roc_month(row.get("資料年月"))
        try:
            filed = roc_date(row.get("出表日期") or row.get("Date"))
        except ValueError:
            continue
        if not period or filed > as_of:
            continue
        rows.append({"code": code, "market": market, "period": period, "filed": filed,
            "industry": str(row.get("產業別") or "").strip(),
            "revenue": _number(row.get("營業收入-當月營收")),
            "revenue_yoy_pct": _number(row.get("營業收入-去年同月增減(%)")),
            "revenue_ytd_yoy_pct": _number(row.get("累計營業收入-前期比較增減(%)"))})
    if not rows:
        return []
    latest = max(row["period"] for row in rows)
    return [row for row in rows if row["period"] == latest]


def parse_tw_valuation(payload, market: str, as_of: str) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("Unexpected Taiwan valuation schema")
    rows = []
    for item in payload:
        row = {str(k).strip(): v for k, v in item.items()}
        code = str(row.get("Code") or row.get("SecuritiesCompanyCode") or "").strip()
        if not re.fullmatch(r"\d{4}", code):
            continue
        try:
            when = roc_date(row.get("Date"))
        except ValueError:
            continue
        if when > as_of:
            continue
        rows.append({"code": code, "market": market, "date": when,
            "pe": _number(row.get("PEratio") if market == "TWSE" else row.get("PriceEarningRatio")),
            "dividend_yield_pct": _number(row.get("DividendYield") if market == "TWSE" else row.get("YieldRatio")),
            "pb": _number(row.get("PBratio") if market == "TWSE" else row.get("PriceBookRatio"))})
    if not rows:
        return []
    latest = max(row["date"] for row in rows)
    return [row for row in rows if row["date"] == latest]


def parse_tw_institutional(payload, market: str, as_of: str) -> dict[str, float]:
    """Parse TPEx total institutional difference; absent fields stay absent."""
    if not isinstance(payload, list):
        return {}
    result = {}
    for item in payload:
        row = {str(k).strip(): v for k, v in item.items()}
        code = str(row.get("SecuritiesCompanyCode") or row.get("Code") or "").strip()
        try:
            when = roc_date(row.get("Date"))
        except ValueError:
            continue
        value = _number(row.get("TotalDifference"))
        if re.fullmatch(r"\d{4}", code) and when <= as_of and value is not None:
            result[code] = value
    return result


def score_taiwan_candidates(market_rows: list[dict], revenue_rows: list[dict],
        valuation_rows: list[dict], institutional: dict[str, float], company_map: dict[str, str]) -> dict:
    markets = {row["code"]: row for row in market_rows}
    revenues = {row["code"]: row for row in revenue_rows}
    valuations = {row["code"]: row for row in valuation_rows}
    eligible = {code for code in markets if code in revenues}
    growth = {code: max(-100, min(300, revenues[code]["revenue_yoy_pct"])) for code in eligible
        if revenues[code]["revenue_yoy_pct"] is not None}
    liquidity = {code: math.log10(max(markets[code]["trade_value"] or 0, 1)) for code in eligible}
    growth_rank, liquidity_rank = _percentiles(growth), _percentiles(liquidity)
    candidates = []
    for code in eligible:
        market, revenue, valuation = markets[code], revenues[code], valuations.get(code, {})
        components = {
            "revenue_growth": round(40 * growth_rank.get(code, 0), 2),
            "liquidity": round(20 * liquidity_rank.get(code, 0), 2),
            "positive_pe_band": 0.0,
            "cash_yield": 0.0,
            "data_completeness": 0.0,
        }
        pe = valuation.get("pe")
        if pe and pe > 0:
            # A moderate positive P/E receives the most points; this is a
            # comparability signal, not an assertion that low P/E is cheap.
            components["positive_pe_band"] = round(max(0, 20 - abs(pe - 18) * 0.8), 2)
        dy = valuation.get("dividend_yield_pct")
        if dy is not None and dy >= 0:
            components["cash_yield"] = round(min(10, dy * 2), 2)
        present = sum(x is not None for x in [revenue.get("revenue_yoy_pct"), revenue.get("revenue_ytd_yoy_pct"),
            pe, valuation.get("pb"), dy, market.get("trade_value")])
        components["data_completeness"] = round(10 * present / 6, 2)
        score = round(sum(components.values()), 2)
        ticker = company_map.get(code) or f"{code}.{'TW' if market['market'] == 'TWSE' else 'TWO'}"
        reasons = []
        if revenue.get("revenue_yoy_pct") is not None:
            reasons.append(f"單月營收年增 {revenue['revenue_yoy_pct']:.1f}%")
        if revenue.get("revenue_ytd_yoy_pct") is not None:
            reasons.append(f"累計營收年增 {revenue['revenue_ytd_yoy_pct']:.1f}%")
        if pe and pe > 0:
            reasons.append(f"本益比 {pe:.1f}")
        if dy is not None:
            reasons.append(f"殖利率 {dy:.2f}%")
        if code in institutional:
            reasons.append(f"櫃買三大法人單日淨額 {institutional[code]:,.0f} 股")
        cautions = ["月營收不等於獲利或現金流；需再查毛利率、資本支出與應收帳款。",
            "估值未做產業、景氣循環與一次性損益調整。"]
        if revenue.get("revenue_yoy_pct") is not None and abs(revenue["revenue_yoy_pct"]) > 100:
            cautions.append("年增率超過 100%，可能受低基期、併購或認列時點影響。")
        candidates.append({"rank": 0, "score": score, "market": market["market"], "code": code,
            "ticker": ticker, "name": market["name"], "industry": revenue.get("industry"),
            "market_date": market["date"], "revenue_period": revenue["period"], "close": market["close"],
            "trade_value": market.get("trade_value"), "revenue_yoy_pct": revenue.get("revenue_yoy_pct"),
            "revenue_ytd_yoy_pct": revenue.get("revenue_ytd_yoy_pct"), "pe": pe, "pb": valuation.get("pb"),
            "dividend_yield_pct": dy, "institutional_net": institutional.get(code),
            "components": components, "reasons": reasons, "cautions": cautions,
            "coverage": f"{present}/6 核心欄位"})
    candidates.sort(key=lambda row: (-row["score"], row["market"], row["code"]))
    for n, row in enumerate(candidates, 1):
        row["rank"] = n
    return {"universe": len(markets), "revenue_matched": len(eligible), "ranked": len(candidates),
        "candidates": candidates[:50]}


def taiwan_opportunities(project, fetch, store, source, as_of, cap, emit, state):
    company_map = {str(code): company["ticker"] for company in project.companies for code in company.get("local_codes", [])}
    dashboards, raw_bundle = [], {}
    for config in source["markets"]:
        market = config["market"]
        raw_market, _ = fetch.get(config["market_url"])
        raw_revenue, _ = fetch.get(config["revenue_url"])
        raw_valuation, _ = fetch.get(config["valuation_url"])
        for raw in [raw_market, raw_revenue, raw_valuation]:
            store.blob(raw)
        raw_inst, institutional = b"[]", {}
        if config.get("institutional_url"):
            raw_inst, _ = fetch.get(config["institutional_url"])
            store.blob(raw_inst)
            institutional = parse_tw_institutional(json.loads(raw_inst), market, as_of)
        market_rows = parse_tw_market(json.loads(raw_market), market, as_of)
        revenue_rows = parse_tw_revenue(json.loads(raw_revenue), market, as_of)
        valuation_rows = parse_tw_valuation(json.loads(raw_valuation), market, as_of)
        dashboard = score_taiwan_candidates(market_rows, revenue_rows, valuation_rows, institutional, company_map)
        dashboard.update(market=market, market_date=max(row["date"] for row in market_rows),
            revenue_period=max(row["period"] for row in revenue_rows) if revenue_rows else None,
            valuation_date=max(row["date"] for row in valuation_rows) if valuation_rows else None,
            source_urls={k.removesuffix("_url"): v for k, v in config.items() if k.endswith("_url")})
        dashboards.append(dashboard)
        raw_bundle[market] = {"market": json.loads(raw_market), "revenue": json.loads(raw_revenue),
            "valuation": json.loads(raw_valuation), "institutional": json.loads(raw_inst)}
    all_candidates = sorted([row for d in dashboards for row in d["candidates"]], key=lambda row: (-row["score"], row["ticker"]))
    for n, row in enumerate(all_candidates, 1):
        row["cross_market_rank"] = n
    dashboard = {"as_of": as_of, "method": "revenue growth 40 + liquidity 20 + positive P/E band 20 + cash yield 10 + completeness 10",
        "markets": [{k: v for k, v in d.items() if k != "candidates"} for d in dashboards],
        "candidates": all_candidates[:50], "candidate_count": sum(d["ranked"] for d in dashboards),
        "limitations": ["分數是資料驅動的研究排序，不是買進建議或預期報酬。",
            "上市與上櫃法人欄位覆蓋不同，法人淨額只展示、不納入跨市場分數。",
            "目前未納入完整財報品質、產業估值常態、公司行動與交易成本。"]}
    raw = dumps(raw_bundle).encode("utf-8")
    emit({"url": source["docs"], "stable_id": f"taiwan-opportunity-screen-{as_of}",
        "title": f"台灣上市櫃研究候選雷達 · {as_of}", "published_at": as_of,
        "kind": "market_screen", "topics": [], "coverage": "all_equities_joined_to_latest_revenue_and_valuation",
        "entities": [row["ticker"] for row in all_candidates if row["ticker"] in {c["ticker"] for c in project.companies}],
        "text": dumps(dashboard), "metadata": {"dashboard": dashboard, "retrieved_vintage": now(),
            "point_in_time_certified": False, "score_is_research_priority": True}}, raw)
    state["discovered"] = dashboard["candidate_count"]
    state["notes"].append("掃描上市櫃全市場並聯結最新月營收與估值欄位；只公開前 50 名研究候選，完整官方回應保留在本機。")


def _reported_quarter(as_of: str) -> tuple[str, str]:
    lagged = date.fromisoformat(as_of) - timedelta(days=45)
    # Select the latest quarter that had already ended by the reporting lag,
    # rather than the quarter containing that date (which is still partial).
    quarter = (lagged.month - 1) // 3
    year = lagged.year
    if quarter == 0:
        quarter, year = 4, year - 1
    return f"CY{year}Q{quarter}", f"CY{year - 1}Q{quarter}"


def _frame_by_cik(payload: dict) -> dict[int, dict]:
    return {int(row["cik"]): row for row in payload.get("data", []) if row.get("cik") and row.get("val") is not None}


def score_sec_candidates(universe: dict, current_revenue: dict[int, dict], prior_revenue: dict[int, dict],
        income: dict[int, dict], research: dict[int, dict], frame: str) -> dict:
    fields = universe.get("fields", [])
    ticker_rows = [dict(zip(fields, row)) for row in universe.get("data", [])]
    exchange_priority = {"Nasdaq": 0, "NYSE": 1, "NYSE American": 2, "Cboe": 3}
    mapping = {}
    for row in sorted(ticker_rows, key=lambda x: (exchange_priority.get(x.get("exchange"), 99), x.get("ticker", ""))):
        if row.get("exchange") in exchange_priority:
            mapping.setdefault(int(row["cik"]), row)
    raw_rows = {}
    for cik, current in current_revenue.items():
        prior, listing = prior_revenue.get(cik), mapping.get(cik)
        if not prior or not listing or current["val"] <= 10_000_000 or prior["val"] <= 0:
            continue
        growth = (current["val"] / prior["val"] - 1) * 100
        if growth < -90 or growth > 1000:
            continue
        net = income.get(cik, {}).get("val")
        rnd = research.get(cik, {}).get("val")
        raw_rows[str(cik)] = {"cik": cik, "ticker": listing["ticker"], "name": listing["name"],
            "exchange": listing["exchange"], "location": current.get("loc", ""), "revenue": current["val"],
            "prior_revenue": prior["val"], "revenue_growth_pct": growth,
            "net_margin_pct": (net / current["val"] * 100) if net is not None else None,
            "rd_intensity_pct": (rnd / current["val"] * 100) if rnd is not None and rnd >= 0 else None,
            "accession": current.get("accn"), "period_start": current.get("start"), "period_end": current.get("end")}
    growth_rank = _percentiles({k: max(-50, min(200, v["revenue_growth_pct"])) for k, v in raw_rows.items()})
    margin_rank = _percentiles({k: max(-50, min(50, v["net_margin_pct"])) for k, v in raw_rows.items() if v["net_margin_pct"] is not None})
    rd_rank = _percentiles({k: min(40, v["rd_intensity_pct"]) for k, v in raw_rows.items() if v["rd_intensity_pct"] is not None})
    candidates = []
    for key, row in raw_rows.items():
        components = {"revenue_growth": round(45 * growth_rank[key], 2),
            "net_margin": round(25 * margin_rank.get(key, 0), 2),
            "research_intensity": round(20 * rd_rank.get(key, 0), 2),
            "data_completeness": round(10 * sum(row[x] is not None for x in ["revenue_growth_pct", "net_margin_pct", "rd_intensity_pct"]) / 3, 2)}
        score = round(sum(components.values()), 2)
        international = bool(row["location"] and not row["location"].startswith("US-"))
        cautions = ["SEC Frames 只涵蓋可對齊此標準科目與曆季的申報公司，會漏掉採其他概念或財年邊界不同者。",
            "此排序未含股價、估值、負債、稀釋與自由現金流。"]
        if row["revenue_growth_pct"] > 100:
            cautions.append("營收年增超過 100%，需查低基期、併購與會計重分類。")
        candidates.append({**row, "score": score, "rank": 0,
            "scope": "國際／美國上市外國發行人" if international else "美國上市公司",
            "components": components,
            "reasons": [f"同季營收年增 {row['revenue_growth_pct']:.1f}%",
                f"淨利率 {row['net_margin_pct']:.1f}%" if row["net_margin_pct"] is not None else "淨利科目未對齊",
                f"研發／營收 {row['rd_intensity_pct']:.1f}%" if row["rd_intensity_pct"] is not None else "研發科目未對齊"],
            "cautions": cautions, "coverage": f"{sum(row[x] is not None for x in ['revenue_growth_pct','net_margin_pct','rd_intensity_pct'])}/3 核心欄位"})
    candidates.sort(key=lambda row: (-row["score"], row["ticker"]))
    for n, row in enumerate(candidates, 1):
        row["rank"] = n
    return {"frame": frame, "listed_securities": len(ticker_rows), "mapped_main_exchange_ciks": len(mapping),
        "comparable_companies": len(candidates), "international_candidates": sum(row["scope"].startswith("國際") for row in candidates),
        "candidates": candidates[:75],
        "method": "cross-sectional percentile: revenue growth 45 + net margin 25 + R&D intensity 20 + completeness 10",
        "limitations": ["研究優先級不是投資建議或預期報酬。", "金融業、外國私營發行人及採不同 XBRL 概念者可能不在可比母體。",
            "需另接行情與估值資料，才可評估市場已反映程度。"]}


def sec_opportunities(project, fetch, store, source, as_of, cap, emit, state):
    current_frame, prior_frame = _reported_quarter(as_of)
    universe_url = "https://www.sec.gov/files/company_tickers_exchange.json"
    raw_universe, _ = fetch.get(universe_url)
    store.blob(raw_universe)
    concepts = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
    payloads, raws = {}, {}
    for concept in concepts:
        for frame in [current_frame, prior_frame]:
            url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{frame}.json"
            try:
                raw, _ = fetch.get(url)
                store.blob(raw); raws[f"{concept}-{frame}"] = raw.decode("utf-8")
                payloads[(concept, frame)] = json.loads(raw)
            except Exception:
                payloads[(concept, frame)] = {"data": []}
    for concept in ["NetIncomeLoss", "ResearchAndDevelopmentExpense"]:
        url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/USD/{current_frame}.json"
        raw, _ = fetch.get(url)
        store.blob(raw); raws[f"{concept}-{current_frame}"] = raw.decode("utf-8")
        payloads[(concept, current_frame)] = json.loads(raw)
    def merged(frame):
        result = {}
        # Prefer the newer revenue concept; use Revenues only where it is absent.
        for concept in reversed(concepts):
            result.update(_frame_by_cik(payloads[(concept, frame)]))
        return result
    dashboard = score_sec_candidates(json.loads(raw_universe), merged(current_frame), merged(prior_frame),
        _frame_by_cik(payloads[("NetIncomeLoss", current_frame)]),
        _frame_by_cik(payloads[("ResearchAndDevelopmentExpense", current_frame)]), current_frame)
    raw_bundle = dumps({"universe": json.loads(raw_universe), "frames": {k: json.loads(v) for k, v in raws.items()}}).encode("utf-8")
    emit({"url": source["docs"], "stable_id": f"sec-opportunity-screen-{current_frame}-{as_of}",
        "title": f"SEC 全市場財務研究候選雷達 · {current_frame}", "published_at": as_of,
        "kind": "market_screen", "coverage": "sec_listed_universe_joined_to_selected_xbrl_frames",
        "topics": [], "entities": [row["ticker"] for row in dashboard["candidates"] if row["ticker"] in {c["ticker"] for c in project.companies}],
        "text": dumps(dashboard), "metadata": {"dashboard": dashboard, "retrieved_vintage": now(),
            "point_in_time_certified": False, "score_is_research_priority": True}}, raw_bundle)
    state["discovered"] = dashboard["comparable_companies"]
    state["notes"].append(f"SEC {current_frame}／{prior_frame} 同季可比公司 {dashboard['comparable_companies']} 家；公開前 75 名研究候選。")


def _utc_date(milliseconds) -> str:
    return datetime.fromtimestamp(int(milliseconds) / 1000, tz=timezone.utc).date().isoformat()


def _crypto_metrics(klines: list, as_of: str) -> dict | None:
    rows = [(int(row[0]), float(row[4]), float(row[7])) for row in klines if _utc_date(row[6]) <= as_of]
    if len(rows) < 31:
        return None
    closes = [row[1] for row in rows]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0 and closes[i] > 0]
    peak, max_drawdown = closes[0], 0.0
    for value in closes:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    def ret(days):
        return (closes[-1] / closes[-days - 1] - 1) * 100 if len(closes) > days else None
    return {"date": _utc_date(rows[-1][0]), "close": closes[-1], "return_7d_pct": ret(7),
        "return_30d_pct": ret(30), "return_90d_pct": ret(90),
        "annualized_volatility_pct": statistics.stdev(returns) * math.sqrt(365) * 100 if len(returns) > 1 else None,
        "max_drawdown_pct": max_drawdown * 100, "daily_points": len(rows)}


def score_crypto_candidates(records: list[dict]) -> list[dict]:
    keyed = {row["symbol"]: row for row in records if row.get("metrics")}
    liquidity = _percentiles({k: math.log10(max(v["quote_volume_24h"], 1)) for k, v in keyed.items()})
    momentum = _percentiles({k: v["metrics"]["return_30d_pct"] for k, v in keyed.items()})
    resilience = _percentiles({k: v["metrics"]["max_drawdown_pct"] for k, v in keyed.items()})
    output = []
    for key, row in keyed.items():
        metrics = row["metrics"]
        volatility_penalty = min(15, max(0, (metrics["annualized_volatility_pct"] - 35) / 5))
        components = {"liquidity": round(35 * liquidity[key], 2), "30d_momentum": round(25 * momentum[key], 2),
            "drawdown_resilience": round(20 * resilience[key], 2),
            "trend_consistency": 10.0 if metrics["return_7d_pct"] > 0 and metrics["return_30d_pct"] > 0 else 0.0,
            "data_completeness": 10.0, "volatility_penalty": round(-volatility_penalty, 2)}
        output.append({**row, "score": round(sum(components.values()), 2), "rank": 0, "components": components,
            "reasons": [f"24h 成交額 {row['quote_volume_24h']:,.0f} USDT", f"30 日報酬 {metrics['return_30d_pct']:.1f}%",
                f"90 日區間最大回撤 {metrics['max_drawdown_pct']:.1f}%"],
            "cautions": ["加密資產排名只反映 Binance 現貨流動性與價格路徑，不代表技術價值或安全性。",
                "高動能可能快速反轉；交易所、市場操縱、監管、託管與穩定幣風險未進入分數。"]})
    output.sort(key=lambda row: (-row["score"], row["symbol"]))
    for n, row in enumerate(output, 1):
        row["rank"] = n
    return output


def select_crypto_tickers(tickers: list[dict], allowed: dict[str, dict], top_n: int) -> list[dict]:
    liquid = [row for row in tickers if row.get("symbol") in allowed and _number(row.get("quoteVolume")) is not None]
    liquid.sort(key=lambda row: _number(row["quoteVolume"]), reverse=True)
    by_symbol = {row["symbol"]: row for row in liquid}
    selected = []
    for symbol in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]:
        if symbol in by_symbol:
            selected.append(by_symbol[symbol])
    for row in liquid:
        if row["symbol"] not in {item["symbol"] for item in selected}:
            selected.append(row)
        if len(selected) >= top_n:
            break
    return selected[:top_n]


def binance_opportunities(project, fetch, store, source, as_of, cap, emit, state):
    base = "https://data-api.binance.vision"
    raw_info, _ = fetch.get(base + "/api/v3/exchangeInfo")
    raw_tickers, _ = fetch.get(base + "/api/v3/ticker/24hr")
    store.blob(raw_info); store.blob(raw_tickers)
    info, tickers = json.loads(raw_info), json.loads(raw_tickers)
    stablecoins = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "USD1", "USDS", "PYUSD", "EUR", "EURI"}
    allowed = {row["symbol"]: row for row in info.get("symbols", []) if row.get("quoteAsset") == "USDT"
        and row.get("status") == "TRADING" and row.get("isSpotTradingAllowed")
        and row.get("baseAsset") not in stablecoins
        and not re.search(r"(?:UP|DOWN|BULL|BEAR)$", row.get("baseAsset", ""))}
    liquid = [row for row in tickers if row.get("symbol") in allowed and _number(row.get("quoteVolume")) is not None]
    selected = select_crypto_tickers(tickers, allowed, max(1, source.get("top_symbols", 12)))
    records, kline_raw = [], {}
    for ticker in selected:
        symbol = ticker["symbol"]
        url = base + "/api/v3/klines"
        raw, _ = fetch.get(url, params={"symbol": symbol, "interval": "1d", "limit": source.get("kline_days", 120)})
        store.blob(raw); kline_raw[symbol] = json.loads(raw)
        metrics = _crypto_metrics(kline_raw[symbol], as_of)
        if metrics:
            records.append({"symbol": symbol, "base_asset": allowed[symbol]["baseAsset"], "quote_asset": "USDT",
                "last_price": _number(ticker.get("lastPrice")), "change_24h_pct": _number(ticker.get("priceChangePercent")),
                "quote_volume_24h": _number(ticker.get("quoteVolume")) or 0, "metrics": metrics})
    candidates = score_crypto_candidates(records)
    dashboard = {"as_of": as_of, "venue": "Binance public spot market data", "eligible_usdt_pairs": len(liquid),
        "analyzed_pairs": len(candidates), "candidates": candidates,
        "bitcoin": next((row for row in candidates if row["symbol"] == "BTCUSDT"), None),
        "method": "liquidity 35 + 30d momentum 25 + drawdown resilience 20 + trend consistency 10 + completeness 10 - volatility penalty",
        "limitations": ["只使用公開市場資料，不使用帳戶、交易或下單 API。", "只分析高流動性 USDT 現貨樣本，並非全部代幣的基本面盡職調查。",
            "分數不可直接與股票研究分數比較。"]}
    raw_bundle = dumps({"exchange_info": info, "tickers_24h": tickers, "klines": kline_raw}).encode("utf-8")
    emit({"url": source["docs"], "stable_id": f"binance-public-market-screen-{as_of}",
        "title": f"Bitcoin 與 Binance 公開現貨雷達 · {as_of}", "published_at": as_of,
        "kind": "crypto_screen", "coverage": "top_liquid_usdt_spot_sample_with_daily_klines",
        "topics": [], "entities": [], "text": dumps(dashboard), "metadata": {"dashboard": dashboard,
            "retrieved_vintage": now(), "score_is_research_priority": True}}, raw_bundle)
    state["discovered"] = len(liquid)
    if len(selected) < len(liquid):
        state["status"] = "partial"
    state["notes"].append(f"從 {len(liquid)} 個可交易 USDT 現貨對中，依 24h 成交額分析前 {len(candidates)} 個；沒有使用 Binance API 金鑰。")


def patent_candidate_radar(project, patent_updates: list[dict]) -> list[dict]:
    def norm(value):
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(value).lower())
    company_names = {}
    for company in project.companies:
        for name in [company["name"], *company.get("aliases", [])]:
            company_names[norm(name)] = company["ticker"]
    grouped = {}
    for patent in patent_updates:
        for assignee in patent.get("assignees", []) or ["未解析權利人"]:
            key = norm(assignee) or "unresolved"
            item = grouped.setdefault(key, {"assignee": assignee or "未解析權利人", "patents": [], "companies": set(), "topics": set()})
            item["patents"].append({k: patent.get(k) for k in ["publication_number", "title", "published_at", "url", "detail_status"]})
            if key in company_names:
                item["companies"].add(company_names[key])
            for topic in project.topic_ids(patent.get("title", "")):
                item["topics"].add(topic)
    output = []
    for item in grouped.values():
        complete = sum(p.get("detail_status") == "complete" for p in item["patents"])
        score = min(100, len(item["patents"]) * 12 + complete * 5 + len(item["topics"]) * 8 + (15 if item["companies"] else 0))
        output.append({"assignee": item["assignee"], "score": score, "patent_count": len(item["patents"]),
            "complete_details": complete, "companies": sorted(item["companies"]), "topics": sorted(item["topics"]),
            "mapping_status": "exact configured name" if item["companies"] else "unresolved / manual review",
            "patents": item["patents"][:10],
            "caution": "專利件數不等於品質、自由實施、有效權利或可商業化收入；權利人對上市公司映射需人工覆核。"})
    return sorted(output, key=lambda row: (-row["score"], row["assignee"]))[:50]
