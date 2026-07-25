# -*- coding: utf-8 -*-
"""可轉債篩選工具，比照XQ全球贏家「進階篩選」的維度，套用在xq_cb_master.csv上。
用法範例：
  python cb_filter.py --conv-value-min 100 --conv-value-max 130 --premium-min 10 --converted-max 10
  python cb_filter.py --recent-issue-days 30
  python cb_filter.py --days-to-maturity 30
  python cb_filter.py --ytp-max 0
  python cb_filter.py --ytm-min 3
  python cb_filter.py --collateral 有擔保
  python cb_filter.py --exclude-recent-stop-days 7

未涵蓋（XQ有但這份CSV匯出沒有欄位，需在XQ內先篩再匯出）：
  - 集保戶數
  - 轉換開始日：已可轉換／未開始（本表的起日/迄日是「停止轉換」重設窗口，不是能否轉換的欄位）
"""
import argparse
import csv
from datetime import date, datetime
from pathlib import Path

BASE = Path(r"C:\Users\Evan\Desktop\Claude工作區\可轉債套利研究")
DEFAULT_CSV = BASE / "xq_cb_master.csv"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y/%m/%d").date()
    except ValueError:
        return None


def load_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("cb_price", "volume", "stock_price", "conv_value", "premium_pct",
                   "conv_price", "shares_per_lot", "next_put_price", "ytp_pct", "ytm_pct",
                   "issued_lots", "remaining_lots", "converted_pct", "coupon_pct"):
            v = r.get(k)
            r[k] = float(v) if v not in (None, "") else None
        r["_issue_date"] = parse_date(r.get("issue_date"))
        r["_maturity_date"] = parse_date(r.get("maturity_date"))
        r["_stop_conv_end"] = parse_date(r.get("stop_conv_end"))
    return rows


def apply_filters(rows, args, today=None):
    today = today or date.today()
    out = []
    for r in rows:
        if args.conv_value_min is not None and (r["conv_value"] is None or r["conv_value"] < args.conv_value_min):
            continue
        if args.conv_value_max is not None and (r["conv_value"] is None or r["conv_value"] > args.conv_value_max):
            continue
        if args.premium_min is not None and (r["premium_pct"] is None or r["premium_pct"] < args.premium_min):
            continue
        if args.premium_max is not None and (r["premium_pct"] is None or r["premium_pct"] > args.premium_max):
            continue
        if args.converted_min is not None and (r["converted_pct"] is None or r["converted_pct"] < args.converted_min):
            continue
        if args.converted_max is not None and (r["converted_pct"] is None or r["converted_pct"] > args.converted_max):
            continue
        if args.recent_issue_days is not None:
            if r["_issue_date"] is None or (today - r["_issue_date"]).days > args.recent_issue_days:
                continue
        if args.days_to_maturity is not None:
            if r["_maturity_date"] is None or (r["_maturity_date"] - today).days > args.days_to_maturity:
                continue
        if args.ytp_min is not None and (r["ytp_pct"] is None or r["ytp_pct"] < args.ytp_min):
            continue
        if args.ytp_max is not None and (r["ytp_pct"] is None or r["ytp_pct"] > args.ytp_max):
            continue
        if args.ytm_min is not None and (r["ytm_pct"] is None or r["ytm_pct"] < args.ytm_min):
            continue
        if args.ytm_max is not None and (r["ytm_pct"] is None or r["ytm_pct"] > args.ytm_max):
            continue
        if args.collateral and r["collateral"] != args.collateral:
            continue
        if args.exclude_recent_stop_days is not None:
            end = r["_stop_conv_end"]
            if end is not None and 0 <= (today - end).days <= args.exclude_recent_stop_days:
                continue
        out.append(r)
    return out


def build_parser():
    p = argparse.ArgumentParser(description="可轉債篩選工具（比照XQ進階篩選11維度）")
    p.add_argument("--csv", default=str(DEFAULT_CSV), help="輸入CSV路徑（xq_cb_master.csv）")
    p.add_argument("--conv-value-min", type=float, default=None, help="轉換價值下限")
    p.add_argument("--conv-value-max", type=float, default=None, help="轉換價值上限")
    p.add_argument("--premium-min", type=float, default=None, help="轉換溢價率下限(%%)")
    p.add_argument("--premium-max", type=float, default=None, help="轉換溢價率上限(%%)")
    p.add_argument("--converted-min", type=float, default=None, help="轉換比例下限(%%)")
    p.add_argument("--converted-max", type=float, default=None, help="轉換比例上限(%%)")
    p.add_argument("--recent-issue-days", type=int, default=None, help="近期發行：發行日距今N天以內")
    p.add_argument("--days-to-maturity", type=int, default=None, help="距到期日：到期日距今N天以內")
    p.add_argument("--ytp-min", type=float, default=None, help="提前賣回收益率下限(%%)")
    p.add_argument("--ytp-max", type=float, default=None, help="提前賣回收益率上限(%%)")
    p.add_argument("--ytm-min", type=float, default=None, help="到期收益率下限(%%)")
    p.add_argument("--ytm-max", type=float, default=None, help="到期收益率上限(%%)")
    p.add_argument("--collateral", default=None, choices=["有擔保", "無擔保"], help="擔保情形")
    p.add_argument("--exclude-recent-stop-days", type=int, default=None,
                    help="排除N天內剛結束「停止轉換」窗口的CB（迄日在今天往前N天內）")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    rows = load_rows(args.csv)
    result = apply_filters(rows, args)
    result.sort(key=lambda r: (r["premium_pct"] if r["premium_pct"] is not None else 999))

    print(f"共 {len(rows)} 檔，符合條件 {len(result)} 檔\n")
    print(f"{'代碼':8s} {'名稱':12s} {'溢價%':>7s} {'轉換價值':>8s} {'轉換比例%':>9s} {'YTP%':>7s} {'YTM%':>7s} {'發行日':10s} {'到期日':10s} {'擔保'}")
    print("-" * 100)
    for r in result:
        print(f"{r['code']:8s} {r['name']:12s} "
              f"{r['premium_pct'] if r['premium_pct'] is not None else float('nan'):7.2f} "
              f"{r['conv_value'] if r['conv_value'] is not None else float('nan'):8.2f} "
              f"{r['converted_pct'] if r['converted_pct'] is not None else float('nan'):9.2f} "
              f"{r['ytp_pct'] if r['ytp_pct'] is not None else float('nan'):7.2f} "
              f"{r['ytm_pct'] if r['ytm_pct'] is not None else float('nan'):7.2f} "
              f"{r['issue_date'] or '':10s} {r['maturity_date'] or '':10s} {r['collateral']}")
