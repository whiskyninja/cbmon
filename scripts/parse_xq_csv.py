# -*- coding: utf-8 -*-
"""把XQ全球贏家「可轉債總表」匯出的CSV(cp950編碼, Excel強制文字格式)轉成乾淨UTF-8 CSV。
用法: python parse_xq_csv.py <輸入路徑> [輸出路徑]
"""
import csv
import re
import sys
from pathlib import Path

IN_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\Evan\Downloads\aa.csv")
OUT_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "xq_cb_master.csv"

FIELDS = [
    "code", "name",
    "cb_price", "volume", "stock_price",
    "conv_value", "premium_pct",
    "conv_price_eff_date", "conv_price", "shares_per_lot",
    "stop_conv_start", "stop_conv_end",
    "next_put_date", "next_put_price", "ytp_pct", "ytm_pct",
    "issue_date", "maturity_date", "issued_lots", "remaining_lots",
    "converted_pct", "coupon_pct", "collateral",
]

def unwrap(cell):
    """去掉 ="值" 的Excel強制文字包裝，回傳去除後的字串（空字串保留為None）"""
    cell = cell.strip()
    m = re.match(r'^="(.*)"$', cell)
    if m:
        cell = m.group(1)
    cell = cell.strip()
    return cell if cell != "" else None

def to_float(s):
    if s is None:
        return None
    s = s.replace(",", "").replace("%", "").strip()
    if s in ("", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def to_int(s):
    f = to_float(s)
    return int(f) if f is not None else None

def parse_name_code(s):
    """'台泥一永(11011)' -> ('11011', '台泥一永')"""
    m = re.match(r'^(.*)\((\w+)\)$', s)
    if m:
        return m.group(2), m.group(1)
    return None, s

with open(IN_PATH, encoding="cp950") as f:
    reader = csv.reader(f)
    rows = list(reader)

# rows[0] = title, rows[1] = group header, rows[2] = column header, rows[3:] = data
data_rows = rows[3:]

out_rows = []
skipped = 0
for r in data_rows:
    if not r or not r[0].strip():
        continue
    cells = [unwrap(c) for c in r]
    # pad to expected length
    while len(cells) < 22:
        cells.append(None)

    code, name = parse_name_code(cells[0]) if cells[0] else (None, None)
    if not code:
        skipped += 1
        continue

    out_rows.append({
        "code": code,
        "name": name,
        "cb_price": to_float(cells[1]),
        "volume": to_int(cells[2]),
        "stock_price": to_float(cells[3]),
        "conv_value": to_float(cells[4]),
        "premium_pct": to_float(cells[5]),
        "conv_price_eff_date": cells[6],
        "conv_price": to_float(cells[7]),
        "shares_per_lot": to_int(cells[8]),
        "stop_conv_start": cells[9],
        "stop_conv_end": cells[10],
        "next_put_date": cells[11],
        "next_put_price": to_float(cells[12]),
        "ytp_pct": to_float(cells[13]),
        "ytm_pct": to_float(cells[14]),
        "issue_date": cells[15],
        "maturity_date": cells[16],
        "issued_lots": to_int(cells[17]),
        "remaining_lots": to_int(cells[18]),
        "converted_pct": to_float(cells[19]),
        "coupon_pct": to_float(cells[20]),
        "collateral": cells[21],
    })

with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(out_rows)

print(f"解析完成: {len(out_rows)} 檔CB，跳過 {skipped} 筆無法解析的列")
print(f"輸出: {OUT_PATH}")
