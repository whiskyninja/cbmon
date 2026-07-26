# -*- coding: utf-8 -*-
"""掃描目前市面上所有可轉債，找出「本尊為穩定配息/穩定觸發轉換價調整」的公司名單。

資料來源：
1. xq_cb_master_auto_verified.csv 裡既有的 conv_price_adjustment_dates_found 欄位
   （來自 verify_conv_price_reliability.py 對 MOPS 歷史重大訊息「轉換價格調整」標題的查詢結果，
   已對全市場375檔CB查過，不需要重打API）。
2. TWSE OpenAPI /opendata/t187ap45_L（上市公司股利分派情形，最新一次決議）—— 用來確認
   該公司「目前」是否仍有配息動作，作為輔助交叉驗證，非必要條件。

方法：
- 依正股代碼(stock_code)分組(同一發行人可能有多檔CB，共用同一組調整紀錄)。
- 從 conv_price_adjustment_dates_found 解析出所有民國年(YYY)，去重複。
- 用該發行人「最早一檔CB的issue_date」到「今年」估計「可觀察窗口年數」。
- 「穩定配息候選」＝ 有調整紀錄的年數 / 可觀察窗口年數 達到門檻(預設>=0.6，且至少2個不同年度)。

已知限制(務必在報告時附註)：
- 這是「正向證據清單」，不是「排除清單」——沒被抓到「轉換價格調整」標題不代表該公司沒有穩定配息，
  只代表該公司可能沒有為此單獨發一則可搜尋的公告標題(見project memory「廣華二KY案例」)。
  所以這份名單「有出現的」高度可信是穩定配息，但「沒出現的」不能反推為不穩定配息。
- 只涵蓋「目前市面上還在流通的CB」的正股，不是全市場穩定配息股(全市場沒發CB的公司不在此列)。
"""
import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
IN_PATH = BASE / "xq_cb_master_auto_verified.csv"
OUT_PATH = BASE / "stable_dividend_cb_issuers.csv"


def roc_year(dt):
    return dt.year - 1911


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y/%m/%d").date()
    except ValueError:
        return None


def main():
    with open(IN_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    today_roc = roc_year(date.today())

    # 依正股代碼分組
    issuers = defaultdict(lambda: {
        "names": set(), "cb_codes": [], "issue_dates": [], "adj_years": set(),
    })

    for r in rows:
        sc = r.get("stock_code")
        if not sc:
            continue
        g = issuers[sc]
        g["names"].add(r.get("name", "").strip())
        g["cb_codes"].append(r.get("code"))
        issue = parse_date(r.get("issue_date"))
        if issue:
            g["issue_dates"].append(issue)
        dates_str = r.get("conv_price_adjustment_dates_found") or ""
        for d in dates_str.split(";"):
            d = d.strip()
            m = re.match(r"^(\d{2,3})/\d{2}/\d{2}$", d)
            if m:
                g["adj_years"].add(int(m.group(1)))

    out_rows = []
    for sc, g in issuers.items():
        if not g["issue_dates"]:
            continue
        earliest_issue = min(g["issue_dates"])
        from_yr = roc_year(earliest_issue)
        window_years = max(1, today_roc - from_yr + 1)
        n_adj_years = len(g["adj_years"])
        ratio = n_adj_years / window_years
        out_rows.append({
            "stock_code": sc,
            "names": "/".join(sorted(g["names"])),
            "cb_codes": ";".join(sorted(set(g["cb_codes"]))),
            "earliest_cb_issue_date": earliest_issue.strftime("%Y/%m/%d"),
            "observable_window_years": window_years,
            "n_years_with_conv_price_adjustment": n_adj_years,
            "adjustment_years_roc": ";".join(str(y) for y in sorted(g["adj_years"])),
            "adjustment_ratio": round(ratio, 2),
            "stable_dividend_candidate": (n_adj_years >= 2 and ratio >= 0.6),
        })

    out_rows.sort(key=lambda x: (-x["stable_dividend_candidate"], -x["adjustment_ratio"], -x["n_years_with_conv_price_adjustment"]))

    fields = ["stock_code", "names", "cb_codes", "earliest_cb_issue_date",
              "observable_window_years", "n_years_with_conv_price_adjustment",
              "adjustment_years_roc", "adjustment_ratio", "stable_dividend_candidate"]
    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)

    n_candidates = sum(1 for r in out_rows if r["stable_dividend_candidate"])
    n_any_adj = sum(1 for r in out_rows if r["n_years_with_conv_price_adjustment"] > 0)
    print(f"共 {len(out_rows)} 個發行人(正股)。")
    print(f"至少出現過1年轉換價調整記錄：{n_any_adj} 檔")
    print(f"符合「穩定配息候選」(>=2個不同年度 且 調整年數/觀察窗口>=0.6)：{n_candidates} 檔")
    print(f"輸出：{OUT_PATH}")


if __name__ == "__main__":
    main()
