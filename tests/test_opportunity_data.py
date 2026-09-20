from datetime import datetime, timedelta, timezone

from edgefinance.opportunity_data import (_crypto_metrics, parse_tw_market, parse_tw_revenue,
    parse_tw_valuation, patent_candidate_radar, score_sec_candidates, score_taiwan_candidates,
    select_crypto_tickers, _reported_quarter)


def test_taiwan_screen_joins_official_rows_and_explains_score():
    market = parse_tw_market([
        {"Date": "1150918", "Code": "2330", "Name": "台積電", "ClosingPrice": "1,200",
            "TradeValue": "1000000000", "TradeVolume": "1000"},
        {"Date": "1150918", "Code": "2317", "Name": "鴻海", "ClosingPrice": "200",
            "TradeValue": "500000000", "TradeVolume": "2000"}], "TWSE", "2026-09-20")
    revenue = parse_tw_revenue([
        {"出表日期": "1150917", "資料年月": "11508", "公司代號": "2330", "產業別": "半導體",
            "營業收入-當月營收": "100", "營業收入-去年同月增減(%)": "30", "累計營業收入-前期比較增減(%)": "25"},
        {"出表日期": "1150917", "資料年月": "11508", "公司代號": "2317", "產業別": "電子",
            "營業收入-當月營收": "100", "營業收入-去年同月增減(%)": "5", "累計營業收入-前期比較增減(%)": "8"}],
        "TWSE", "2026-09-20")
    valuation = parse_tw_valuation([
        {"Date": "1150918", "Code": "2330", "PEratio": "20", "DividendYield": "2", "PBratio": "6"},
        {"Date": "1150918", "Code": "2317", "PEratio": "18", "DividendYield": "4", "PBratio": "2"}],
        "TWSE", "2026-09-20")
    result = score_taiwan_candidates(market, revenue, valuation, {}, {"2330": "TSM", "2317": "2317.TW"})
    assert result["universe"] == 2 and result["ranked"] == 2
    assert {row["ticker"] for row in result["candidates"]} == {"TSM", "2317.TW"}
    assert all(sum(row["components"].values()) == row["score"] for row in result["candidates"])
    assert all(row["cautions"] for row in result["candidates"])


def test_sec_screen_separates_us_and_foreign_issuers():
    universe = {"fields": ["cik", "name", "ticker", "exchange"], "data": [
        [1, "US CO", "USCO", "Nasdaq"], [2, "FOREIGN CO", "INTL", "NYSE"], [3, "OTC CO", "OTC", "OTC"]]}
    current = {1: {"cik": 1, "val": 150_000_000, "loc": "US-CA"},
        2: {"cik": 2, "val": 200_000_000, "loc": "NL"}}
    prior = {1: {"cik": 1, "val": 100_000_000}, 2: {"cik": 2, "val": 180_000_000}}
    income = {1: {"val": 20_000_000}, 2: {"val": 10_000_000}}
    research = {1: {"val": 30_000_000}, 2: {"val": 15_000_000}}
    result = score_sec_candidates(universe, current, prior, income, research, "CY2026Q2")
    assert result["comparable_companies"] == 2 and result["international_candidates"] == 1
    assert {row["scope"] for row in result["candidates"]} == {"美國上市公司", "國際／美國上市外國發行人"}
    assert all(row["cautions"] and row["score"] <= 100 for row in result["candidates"])


def test_sec_frame_uses_latest_completed_quarter_after_reporting_lag():
    assert _reported_quarter("2026-09-20") == ("CY2026Q2", "CY2025Q2")
    assert _reported_quarter("2026-01-10") == ("CY2025Q3", "CY2024Q3")


def test_crypto_metrics_preserve_volatility_and_drawdown():
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    klines = []
    for i in range(121):
        opened = start + timedelta(days=i)
        close = 100 + i if i < 90 else 190 - (i - 90) * 2
        klines.append([int(opened.timestamp() * 1000), "0", "0", "0", str(close), "0",
            int((opened + timedelta(days=1) - timedelta(milliseconds=1)).timestamp() * 1000), "1000"])
    metrics = _crypto_metrics(klines, "2026-09-20")
    assert metrics["daily_points"] == 121
    assert metrics["annualized_volatility_pct"] > 0 and metrics["max_drawdown_pct"] < 0
    assert metrics["return_90d_pct"] is not None


def test_crypto_sample_keeps_bitcoin_ether_and_bnb_before_volume_fill():
    tickers = [{"symbol": symbol, "quoteVolume": str(volume)} for symbol, volume in
        [("SOLUSDT", 1000), ("XRPUSDT", 900), ("BTCUSDT", 800), ("ETHUSDT", 700), ("BNBUSDT", 10)]]
    allowed = {row["symbol"]: {} for row in tickers}
    selected = select_crypto_tickers(tickers, allowed, 4)
    assert [row["symbol"] for row in selected[:3]] == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    assert selected[3]["symbol"] == "SOLUSDT"


def test_patent_radar_requires_exact_company_name(project):
    updates = [{"publication_number": "US1B2", "title": "Optical compute package", "published_at": "2026-09-20",
        "url": "https://example.org/patent", "detail_status": "complete", "assignees": ["NVIDIA Corporation"]},
        {"publication_number": "EP2B1", "title": "Battery control", "published_at": "2026-09-20",
        "url": "https://example.org/patent2", "detail_status": "not_selected", "assignees": ["NVIDIA-ish"]}]
    radar = patent_candidate_radar(project, updates)
    mapped = next(row for row in radar if row["assignee"] == "NVIDIA Corporation")
    unresolved = next(row for row in radar if row["assignee"] == "NVIDIA-ish")
    assert mapped["companies"] == ["NVDA"] and not unresolved["companies"]
    assert unresolved["mapping_status"].startswith("unresolved")
