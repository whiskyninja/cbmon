# -*- coding: utf-8 -*-
"""「攻守一體」交叉比對：cbput賣回排行(低於賣回價、有正賣回報酬率) x 穩定配息候選名單。

書中5-4節「攻守一體 穩賺不賠的特殊情況」：CB價格低於賣回價(有保底賣回報酬率=守)
+ 本尊穩定配息、具「股息穿越轉換價」效果(=攻)，兩者兼具的標的風險報酬最佳。

用法：python attack_defense_cross_ref.py
"""
import csv
from datetime import date, datetime
from pathlib import Path

BASE = Path(r"C:\Users\Evan\Desktop\Claude工作區\可轉債套利研究")
PUT_CSV = BASE / "xq_cb_master.csv"
DIV_CSV = BASE / "stable_dividend_cb_issuers_enriched.csv"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y/%m/%d").date()
    except ValueError:
        return None


def load_put_candidates():
    with open(PUT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    today = date.today()
    out = []
    for r in rows:
        cb_price = r.get("cb_price")
        put_price = r.get("next_put_price")
        put_date = parse_date(r.get("next_put_date"))
        ytp = r.get("ytp_pct")
        if not cb_price or not put_price or not put_date:
            continue
        cb_price = float(cb_price)
        put_price = float(put_price)
        if put_date <= today:
            continue
        if cb_price >= put_price:
            continue  # 只要「低於賣回價」的
        r["_stock_code"] = r["code"][:4]
        r["_cb_price"] = cb_price
        r["_put_price"] = put_price
        r["_ytp_pct"] = float(ytp) if ytp not in (None, "") else None
        r["_days_to_put"] = (put_date - today).days
        out.append(r)
    return out


def load_dividend_map():
    with open(DIV_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    m = {}
    for r in rows:
        m[r["stock_code"]] = r
    return m


def main():
    put_candidates = load_put_candidates()
    div_map = load_dividend_map()

    print(f"賣回排行候選(CB價<賣回價、賣回日未到期)：{len(put_candidates)} 檔\n")

    matches = []
    for r in put_candidates:
        info = div_map.get(r["_stock_code"])
        if info and info["stable_dividend_candidate"] == "True":
            matches.append((r, info))

    matches.sort(key=lambda x: -(x[0]["_ytp_pct"] or -999))

    print(f"=== 攻守一體候選(低於賣回價 + 穩定配息名單命中)：共 {len(matches)} 檔 ===\n")
    print(f"{'CB代號':7s} {'名稱':10s} {'CB價':>7s} {'賣回價':>7s} {'賣回年化%':>8s} "
          f"{'距賣回日':>6s} {'調整年度(民國)':16s} {'114現金股利':>10s}")
    print("-" * 100)
    for r, info in matches:
        cash_div = info.get("latest_cash_dividend_per_share") or ""
        print(f"{r['code']:7s} {r['name']:10s} {r['_cb_price']:7.2f} {r['_put_price']:7.2f} "
              f"{(r['_ytp_pct'] if r['_ytp_pct'] is not None else float('nan')):8.2f} "
              f"{r['_days_to_put']:6d} {info['adjustment_years_roc']:16s} {cash_div:>10s}")

    # 額外：也列出「低於賣回價但穩定配息名單沒命中」的，供人工複核是否漏抓
    print(f"\n(供參考)低於賣回價但不在穩定配息名單裡的候選數：{len(put_candidates) - len(matches)} 檔")


if __name__ == "__main__":
    main()
