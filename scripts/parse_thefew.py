import re
import csv
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 可轉債套利研究資料夾
SRC = os.path.join(BASE, "thefew_low_premium_raw.txt")
OUT_CSV = os.path.join(BASE, "thefew_low_premium_full.csv")
OUT_SUMMARY = os.path.join(BASE, "candidates_summary.txt")

with open(SRC, "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
records = []
i = 0
code_name_re = re.compile(r"^(\d{4,6}) (.+)$")
n = len(lines)
seen = set()
while i < n:
    line = lines[i].strip("\r")
    m = code_name_re.match(line)
    if m:
        code = m.group(1)
        name = m.group(2)
        key = (code, name)
        if i + 1 < n:
            data_line = lines[i+1].strip("\r")
            parts = [p for p in data_line.split("\t") if p != ""]
            if len(parts) == 7:
                cb_price_raw, conv_value, premium, stock_price_raw, conv_price, converted_pct, maturity = parts
                if key not in seen:
                    seen.add(key)
                    records.append({
                        "code": code, "name": name, "premium": premium, "conv_price": conv_price,
                        "stock_price_raw": stock_price_raw, "cb_price_raw": cb_price_raw,
                        "conv_value": conv_value, "converted_pct": converted_pct, "maturity": maturity,
                    })
    i += 1

def parse_price(raw):
    m = re.match(r"^([\d.]+)", raw)
    return float(m.group(1)) if m else None

def parse_pct(raw):
    m = re.match(r"^([\d.]+)%", raw)
    return float(m.group(1)) if m else None

rows_out = []
for r in records:
    stock_price = parse_price(r["stock_price_raw"])
    try:
        conv_price = float(r["conv_price"])
    except ValueError:
        conv_price = None
    gap = None
    if stock_price is not None and conv_price is not None and conv_price != 0:
        gap = (stock_price - conv_price) / conv_price * 100
    converted = parse_pct(r["converted_pct"])
    rows_out.append({**r, "stock_price": stock_price, "conv_price_f": conv_price, "gap_pct": gap, "converted_f": converted})

rows_out.sort(key=lambda x: (x["gap_pct"] is None, -(x["gap_pct"] if x["gap_pct"] is not None else 0)))

with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["代碼", "名稱", "轉換溢價率", "轉換價", "股票收盤價", "離強贖門檻(%)", "CB收盤價原始", "轉換價值", "已轉換%", "到期/賣回日"])
    for r in rows_out:
        gap_str = f"{r['gap_pct']:.1f}" if r["gap_pct"] is not None else ""
        w.writerow([r["code"], r["name"], r["premium"], r["conv_price"], r["stock_price"] if r["stock_price"] is not None else "", gap_str, r["cb_price_raw"], r["conv_value"], r["converted_pct"], r["maturity"]])

# candidates: gap>=15% (getting close to/over 30% trigger) AND converted% still low (<30%, chips still mostly outstanding = early-stage, actionable)
candidates = [r for r in rows_out if r["gap_pct"] is not None and r["gap_pct"] >= 15 and (r["converted_f"] is None or r["converted_f"] < 30)]
candidates.sort(key=lambda x: -x["gap_pct"])

# already-resolved: gap>=30% but converted% high (>=30%) = large chips already gone, signal is late/moot
resolved = [r for r in rows_out if r["gap_pct"] is not None and r["gap_pct"] >= 30 and r["converted_f"] is not None and r["converted_f"] >= 30]
resolved.sort(key=lambda x: -x["gap_pct"])

with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
    f.write(f"total unique records: {len(records)}\n")
    f.write(f"gap computed: {sum(1 for r in rows_out if r['gap_pct'] is not None)}\n\n")
    f.write("=== 候選名單 (離強贖門檻>=15% 且 已轉換%<30%，籌碼還沒被收割) ===\n")
    for r in candidates[:30]:
        f.write(f"{r['code']} {r['name']:14s} 離強贖={r['gap_pct']:.1f}%  股價={r['stock_price']}  轉換價={r['conv_price']}  轉換溢價率={r['premium']}  已轉換={r['converted_pct']}  到期={r['maturity']}\n")
    f.write(f"\n候選總數: {len(candidates)}\n\n")
    f.write("=== 已收割/近尾聲 (離強贖>=30% 但 已轉換%>=30%，訊號偏晚僅供參考) ===\n")
    for r in resolved[:15]:
        f.write(f"{r['code']} {r['name']:14s} 離強贖={r['gap_pct']:.1f}%  已轉換={r['converted_pct']}  到期={r['maturity']}\n")
    f.write(f"\n已收割總數: {len(resolved)}\n")

print("done")
