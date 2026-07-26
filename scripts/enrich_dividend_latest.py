# -*- coding: utf-8 -*-
"""幫 stable_dividend_cb_issuers.csv 加上「最新一次決議股利」資訊(現金股利+股票股利)，
資料源: TWSE OpenAPI /opendata/t187ap45_L (上市公司股利分派情形，免登入，僅上市適用，
上櫃公司此欄位會是空的，需另外用TPEx對應資料源，暫未串接)。
"""
import csv
import json
from pathlib import Path
from urllib.request import urlopen, Request

BASE = Path(__file__).parent.parent
IN_PATH = BASE / "stable_dividend_cb_issuers.csv"
OUT_PATH = BASE / "stable_dividend_cb_issuers_enriched.csv"

URL = "https://openapi.twse.com.tw/v1/opendata/t187ap45_L"


def fetch_dividend_map():
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    m = {}
    for row in data:
        code = row.get("公司代號")
        if not code:
            continue
        cash = row.get("股東配發-盈餘分配之現金股利(元/股)") or "0"
        cash_cap = row.get("股東配發-法定盈餘公積發放之現金(元/股)") or "0"
        cash_cap2 = row.get("股東配發-資本公積發放之現金(元/股)") or "0"
        stock = row.get("股東配發-盈餘轉增資配股(元/股)") or "0"
        year = row.get("股利年度")
        period = row.get("股利所屬年(季)度")
        try:
            total_cash = float(cash) + float(cash_cap) + float(cash_cap2)
        except ValueError:
            total_cash = None
        # 只保留第一筆(該公司代號在資料集中最早出現的一筆通常是最新一次決議)
        if code not in m:
            m[code] = {
                "latest_dividend_year_roc": year,
                "latest_dividend_period": period,
                "latest_cash_dividend_per_share": total_cash,
                "latest_stock_dividend_per_share": stock,
            }
    return m


def main():
    div_map = fetch_dividend_map()
    print(f"TWSE股利分派資料共 {len(div_map)} 家上市公司(不含上櫃)")

    with open(IN_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    extra_fields = ["latest_dividend_year_roc", "latest_dividend_period",
                     "latest_cash_dividend_per_share", "latest_stock_dividend_per_share",
                     "has_twse_dividend_record"]
    for r in rows:
        info = div_map.get(r["stock_code"])
        if info:
            r["latest_dividend_year_roc"] = info["latest_dividend_year_roc"]
            r["latest_dividend_period"] = info["latest_dividend_period"]
            r["latest_cash_dividend_per_share"] = info["latest_cash_dividend_per_share"]
            r["latest_stock_dividend_per_share"] = info["latest_stock_dividend_per_share"]
            r["has_twse_dividend_record"] = True
        else:
            for k in extra_fields[:-1]:
                r[k] = ""
            r["has_twse_dividend_record"] = False

    fields = list(rows[0].keys())
    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
