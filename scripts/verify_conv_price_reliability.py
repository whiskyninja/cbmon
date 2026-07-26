# -*- coding: utf-8 -*-
"""驗證xq_cb_master_auto.csv裡每一檔CB的conv_price(來自thefew.tw)是否可信。

方法：查MOPS「歷史重大訊息」(t05st01, 免登入GET, 依公司代號+民國年度)，
比對公告標題有沒有出現「轉換價格調整」關鍵字。有出現＝該發行人在該年度真的
調整過轉換價，thefew若顯示「目前轉換價=發行時轉換價」就代表thefew資料是舊的
(不可信)；查完該CB發行年至今所有年度都沒有這個標題＝目前thefew的conv_price
可信(該檔真的從未調整過)。

已用兩個已知案例驗證方法本身正確：
  14363(華友聯三, 正股1436)：114年度查到「轉換價格調整」-> thefew的182.5證實是舊值
  15364(和大四,   正股1536)：114/115年度都查無「轉換價格調整」-> thefew的72.26證實正確

同一發行人底下的CB(如14362/14363/14364都是正股1436)共用同一份查詢結果，
用(stock_code, year)當cache key，避免同一發行人被重複查好幾次。

用法：
  python verify_conv_price_reliability.py --limit 20   # 先測前20檔
  python verify_conv_price_reliability.py              # 全市場跑一次(建議跑一次backfill即可，
                                                        # 不需要每天重跑；只有查到"從未調整"的檔案
                                                        # 之後若又出現真的調整事件才需要重查)
"""
import argparse
import csv
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).parent.parent
IN_PATH = BASE / "xq_cb_master_auto.csv"
OUT_PATH = BASE / "xq_cb_master_auto_verified.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ADJUSTMENT_KEYWORD = "轉換價格調整"


def roc_year(dt):
    return dt.year - 1911


def query_material_info_titles(session, stock_code, roc_yr):
    """查MOPS歷史重大訊息，回傳(標題文字, 日期字串)list。"""
    url = (
        "https://mopsov.twse.com.tw/mops/web/t05st01"
        f"?encodeURIComponent=1&step=1&firstin=1&off=1"
        f"&queryName=co_id&inpuType=co_id&TYPEK=all&co_id={stock_code}&year={roc_yr}"
    )
    r = session.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        code_cell = tds[0].get_text(strip=True)
        date_str = tds[2].get_text(strip=True)
        # 真正的資料列：第一欄是純數字公司代號、第三欄是YYY/MM/DD格式日期
        # (排除頁面上其他含5+個td的導覽/搜尋提示列)
        if not code_cell.isdigit():
            continue
        if not re.match(r"^\d{2,3}/\d{2}/\d{2}$", date_str):
            continue
        subject = tds[4].get_text(" ", strip=True)
        if subject:
            results.append((date_str, subject))
    return results


def check_issuer_ever_adjusted(session, stock_code, from_year_roc, to_year_roc, cache, delay):
    """檢查該正股代碼從from_year到to_year(含)有沒有任何一年出現「轉換價格調整」標題。
    回傳(是否調整過, 調整日期list)。cache用(stock_code, year)避免重複查詢。"""
    adjustment_dates = []
    for yr in range(from_year_roc, to_year_roc + 1):
        key = (stock_code, yr)
        if key not in cache:
            titles = query_material_info_titles(session, stock_code, yr)
            cache[key] = titles
            time.sleep(delay)
        for date_str, subject in cache[key]:
            if ADJUSTMENT_KEYWORD in subject:
                adjustment_dates.append(date_str)
    return (len(adjustment_dates) > 0, adjustment_dates)


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y/%m/%d").date()
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()

    with open(IN_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if args.limit:
        rows = rows[: args.limit]

    session = requests.Session()
    cache = {}
    today_roc = roc_year(date.today())

    out_fields = list(rows[0].keys()) + ["conv_price_verified_reliable", "conv_price_adjustment_dates_found"]
    out_rows = []

    for i, r in enumerate(rows, 1):
        stock_code = r.get("stock_code")
        issue = parse_date(r.get("issue_date"))
        if not stock_code or not issue:
            r["conv_price_verified_reliable"] = None
            r["conv_price_adjustment_dates_found"] = "issue_date或stock_code缺失無法查證"
            out_rows.append(r)
            continue

        from_yr = roc_year(issue)
        ever_adjusted, adj_dates = check_issuer_ever_adjusted(
            session, stock_code, from_yr, today_roc, cache, args.delay
        )
        r["conv_price_verified_reliable"] = not ever_adjusted
        r["conv_price_adjustment_dates_found"] = ";".join(adj_dates) if adj_dates else ""
        out_rows.append(r)

        if i % 20 == 0:
            print(f"進度 {i}/{len(rows)}... (已查詢{len(cache)}組公司-年度快取)")

    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(out_rows)

    n_reliable = sum(1 for r in out_rows if r.get("conv_price_verified_reliable") is True)
    n_unreliable = sum(1 for r in out_rows if r.get("conv_price_verified_reliable") is False)
    n_unknown = len(out_rows) - n_reliable - n_unreliable
    print(f"\n完成：可信{n_reliable}檔、不可信(曾調整過){n_unreliable}檔、無法判斷{n_unknown}檔")
    print(f"共發出 {len(cache)} 組(正股代碼,年度)查詢請求")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
