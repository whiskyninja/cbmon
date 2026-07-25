# -*- coding: utf-8 -*-
"""全表 444 檔可轉債轉換溢價率掃描，找出負溢價/低溢價的真正轉換套利候選。
與離強贖門檻(gap)排序邏輯互補：gap 回答"事件何時發生"，溢價率回答"進場是付錢還是賺錢"。
"""
import csv
from pathlib import Path

BASE = Path(r"C:\Users\Evan\Desktop\Claude工作區\可轉債套利研究")

def parse_pct(s):
    s = s.strip()
    if s in ("無", "", "無成交"):
        return None
    return float(s.rstrip("%"))

def parse_float(s):
    s = s.strip()
    if s in ("無", "", "已全部轉換", "無成交"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

rows = []
with open(BASE / "thefew_low_premium_full.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for r in reader:
        premium = parse_pct(r["轉換溢價率"])
        if premium is None:
            continue  # 無成交/無資料，無法判斷溢價，排除
        conv_pct = parse_pct(r["已轉換%"])
        rows.append({
            "code": r["代碼"].strip(),
            "name": r["名稱"].strip(),
            "premium": premium,
            "cb_price": r["CB收盤價原始"].strip(),
            "conv_value": parse_float(r["轉換價值"]),
            "conv_pct": conv_pct,
            "gap": parse_float(r["離強贖門檻(%)"]),
            "maturity": r["到期/賣回日"].strip(),
        })

rows.sort(key=lambda x: x["premium"])

print(f"共 {len(rows)} 檔有溢價率資料（排除「無成交」的 CB）\n")

print("=== 負溢價（CB價格 < 轉換價值，理論上接近無風險轉換套利）===")
neg = [r for r in rows if r["premium"] < 0]
for r in neg:
    print(f"{r['code']:8s} {r['name']:12s} 溢價={r['premium']:6.1f}%  CB價={r['cb_price']:14s} 轉換價值={r['conv_value']}  已轉換={r['conv_pct']}%  gap={r['gap']}%  到期={r['maturity']}")
print(f"共 {len(neg)} 檔\n")

print("=== 低溢價 0%~5%（含已轉換低者，尚有轉換套利空間但需扣執行成本）===")
low = [r for r in rows if 0 <= r["premium"] <= 5]
for r in low:
    print(f"{r['code']:8s} {r['name']:12s} 溢價={r['premium']:6.1f}%  CB價={r['cb_price']:14s} 轉換價值={r['conv_value']}  已轉換={r['conv_pct']}%  gap={r['gap']}%  到期={r['maturity']}")
print(f"共 {len(low)} 檔\n")

print("=== 排除已轉換%過高(>=50%，籌碼多半已被拿走)的負溢價/低溢價候選 ===")
clean = [r for r in neg + low if (r["conv_pct"] is None or r["conv_pct"] < 50)]
clean.sort(key=lambda x: x["premium"])
for r in clean:
    print(f"{r['code']:8s} {r['name']:12s} 溢價={r['premium']:6.1f}%  已轉換={r['conv_pct']}%  gap={r['gap']}%  到期={r['maturity']}")
print(f"共 {len(clean)} 檔（這是修正後框架下最優先要查的名單）")
