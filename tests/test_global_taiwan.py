import json

from edgefinance.global_data import parse_ecb_csv, parse_world_bank
from edgefinance.taiwan_data import parse_disclosure_rows, parse_market_rows, parse_revenue_rows


def test_project_loads_major_economies(project):
    ids = {row["id"] for row in project.economies}
    assert {"USA", "CHN", "JPN", "DEU", "IND", "EUU"} <= ids
    assert all("?" not in row["name"] + row["region"] for row in project.economies)
    configured = [source["name"] for source in project.sources]
    configured += [indicator["name"] for source in project.sources for indicator in source.get("indicators", [])]
    assert all("?" not in label for label in configured)


def test_world_bank_keeps_economy_dimension_and_missing_values(project):
    payload = [
        {"lastupdated": "2026-07-13", "total": 3},
        [
            {"countryiso3code": "USA", "country": {"value": "United States"}, "date": "2025", "value": 2.1, "obs_status": ""},
            {"countryiso3code": "CHN", "country": {"value": "China"}, "date": "2025", "value": 4.8, "obs_status": ""},
            {"countryiso3code": "USA", "country": {"value": "United States"}, "date": "2024", "value": None, "obs_status": ""},
        ],
    ]
    points, meta = parse_world_bank(payload, {"USA", "CHN"},
        {"id": "GDP", "name": "GDP growth", "unit": "percent"}, "2026-09-20")
    assert {(p["economy"], p["value"]) for p in points} == {("USA", 2.1), ("CHN", 4.8)}
    assert meta["lastupdated"] == "2026-07-13"


def test_ecb_csv_parser_respects_cutoff_and_currency_filter():
    raw = ("CURRENCY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT\n"
        "USD,2026-09-18,1.18,A,USD per EUR\n"
        "JPY,2026-09-18,174.2,A,JPY per EUR\n"
        "USD,2026-09-21,1.19,A,USD per EUR\n").encode()
    points = parse_ecb_csv(raw, {"USD"}, "2026-09-20")
    assert len(points) == 1 and points[0]["series"] == "ECB_EXR_USD_PER_EUR"


def test_twse_market_parser_maps_only_official_company_codes():
    payload = [
        {"Date": "1150918", "Code": "2330", "Name": "台積電", "ClosingPrice": "1,200.00",
            "Change": "+10.00", "TradeValue": "30,000", "TradeVolume": "25"},
        {"Date": "1150918", "Code": "0050", "Name": "ETF", "ClosingPrice": "200",
            "Change": "-1", "TradeValue": "10,000", "TradeVolume": "50"},
    ]
    dashboard = parse_market_rows(payload, "TWSE", {"2330": "TSM"}, "2026-09-20")
    assert dashboard["date"] == "2026-09-18"
    assert dashboard["watchlist"][0]["ticker"] == "TSM"
    assert dashboard["companies"] == 2 and dashboard["advances"] == 1 and dashboard["declines"] == 1


def test_mops_revenue_parser_preserves_period_unit_inputs():
    payload = [{"出表日期": "1150917", "資料年月": "11508", "公司代號": "2330", "公司名稱": "台積電",
        "產業別": "半導體業", "營業收入-當月營收": "335,772,152", "營業收入-上月比較增減(%)": "3.9",
        "營業收入-去年同月增減(%)": "33.8", "累計營業收入-當月累計營收": "2,431,983,711",
        "累計營業收入-前期比較增減(%)": "37.1", "備註": ""}]
    rows = parse_revenue_rows(payload, "TWSE", {"2330": "TSM"}, "2026-09-20")
    assert rows[0]["period"] == "2026-08-01" and rows[0]["filed"] == "2026-09-17"
    assert rows[0]["revenue"] == 335772152 and rows[0]["ticker"] == "TSM"


def test_mops_disclosure_parser_strips_inconsistent_headers():
    payload = [{"發言日期": "1150919", "發言時間": "180000", "公司代號": "2330", "公司名稱": "台積電",
        "主旨 ": "董事會決議", "符合條款": "第 14 款", "事實發生日": "1150919", "說明": "測試資料"}]
    rows = parse_disclosure_rows(payload, "TWSE", {"2330": "TSM"}, "2026-09-20")
    assert rows[0]["subject"] == "董事會決議" and rows[0]["published_at"] == "2026-09-19"
    assert rows[0]["ticker"] == "TSM"
