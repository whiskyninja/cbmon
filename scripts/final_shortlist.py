# -*- coding: utf-8 -*-
"""把溢價率掃描的31檔候選，疊上限制狀態(B層)、KY股旗標、gap分類，
產出路徑2的分級鎖定建議。"""
import csv
import json
import re
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
            continue
        conv_pct = parse_pct(r["已轉換%"])
        rows.append({
            "code": r["代碼"].strip(),
            "name": r["名稱"].strip(),
            "premium": premium,
            "conv_pct": conv_pct,
            "gap": parse_float(r["離強贖門檻(%)"]),
            "maturity": r["到期/賣回日"].strip(),
        })

# 篩出31檔候選池（負溢價+0~5%低溢價，排除已轉換>=50%）
pool = [r for r in rows if (r["premium"] < 0 or 0 <= r["premium"] <= 5) and (r["conv_pct"] is None or r["conv_pct"] < 50)]

with open(BASE / "restriction_status.json", encoding="utf-8") as f:
    status_list = json.load(f)
status_by_code = {r["code"]: r for r in status_list}

STATE_LABEL = {
    "clear": "可觀察",
    "stock_warn": "正股注意",
    "stock_margin_upcoming": "即將暫停融券",
    "stock_margin_active": "正股暫停融券",
    "stock_disp": "正股處置",
    "cb_disp": "CB處置",
    "unresolved": "需人工問券商",
}

def is_ky(name):
    return "KY" in name

def optionality_tag(gap):
    if gap is None:
        return "?"
    if gap >= 100:
        return "已耗盡(deep ITM)"
    if gap <= 30:
        return "尚保有"
    return "中等"

# 讀轉換價，算轉股股數與零股避險覆蓋率（零股不得融資融券/借券，故無法避險）
conv_price_by_code = {}
with open(BASE / "thefew_low_premium_full.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for r in reader:
        cp = parse_float(r["轉換價"])
        if cp and cp > 0:
            conv_price_by_code[r["代碼"].strip()] = cp

def lot_analysis(code):
    cp = conv_price_by_code.get(code)
    if not cp:
        return None
    shares = int(100000 / cp)  # 無條件捨去，實際撥券股數以券商計算為準
    odd = shares % 1000
    round_lots = shares - odd
    coverage = round_lots / shares if shares else 0
    return {"shares": shares, "odd": odd, "round_lots": round_lots, "coverage": coverage}

def freshness_flag(conv_pct):
    """已轉換%=0 是新券/流動性存疑的訊號：可能還在發行後3個月閉鎖期內(根本不能轉換)，
    且新券成交量小、買賣價差常態偏寬(2026-07-25 Evan實測霖宏二踢爆：conv_pct=0%且被排A級最乾淨，
    實際卻不能轉換+當日價差5%，兩者都跟這裡的0%訊號同源)。"""
    if conv_pct == 0:
        return "新券警示(已轉換0%，疑閉鎖期未過)"
    if conv_pct is None:
        return "轉換率未知"
    return None

for r in pool:
    st = status_by_code.get(r["code"], {})
    r["state"] = st.get("state", "unknown")
    r["state_label"] = STATE_LABEL.get(r["state"], r["state"])
    r["ky"] = is_ky(r["name"])
    r["optionality"] = optionality_tag(r["gap"])
    r["fresh"] = freshness_flag(r["conv_pct"])

pool.sort(key=lambda x: x["premium"])

print(f"{'代碼':8s} {'名稱':14s} {'溢價%':>7s} {'gap%':>8s} {'optionality':14s} {'限制狀態':10s} KY 到期")
print("-" * 100)
for r in pool:
    ky_mark = "KY" if r["ky"] else "  "
    print(f"{r['code']:8s} {r['name']:14s} {r['premium']:7.1f} {str(r['gap']):>8s} {r['optionality']:14s} {r['state_label']:10s} {ky_mark} {r['maturity']}")

print("\n" + "!" * 100)
print("! 全域警告：以下分級全部只用「最後成交價」算溢價率，未扣真實買賣價差。")
print("! Evan 2026-07-25實測：多數CB買賣價差常態約5%，本清單負溢價/低溢價候選(-6.8%~+5%)理論折價")
print("! 普遍小於實際價差——任何等級要真的下單前，一律要先開實際看盤系統核對當下買一/賣一價，")
print("! 不能用這份清單的溢價率數字直接估成本。")
print("!" * 100)

# 分級：D級=新券/流動性存疑(已轉換0%或未知，優先於其他分級判斷)；C級=有嚴重限制旗標；
# A級=負溢價+無限制旗標+非KY+非新券；B級=其餘(低溢價/KY/輕微旗標)
print("\n=== 分級建議 ===")
A, B, C, D = [], [], [], []
for r in pool:
    severe = r["state"] in ("cb_disp", "stock_disp", "stock_margin_active")
    mild = r["state"] in ("stock_warn", "stock_margin_upcoming")
    if severe:
        C.append(r)
    elif r["fresh"]:
        D.append(r)
    elif r["premium"] <= 0 and not mild and not r["ky"]:
        A.append(r)
    else:
        B.append(r)

print(f"\nA級（負溢價 + 無限制旗標 + 非KY + 非新券，最乾淨，仍須人工核實即時價差）: {len(A)} 檔")
for r in A:
    print(f"  {r['code']} {r['name']}  溢價{r['premium']}%  gap{r['gap']}%  {r['optionality']}")

print(f"\nB級（低溢價或有輕微旗標/KY，需多一層查證）: {len(B)} 檔")
for r in B:
    reason = []
    if r["premium"] > 0: reason.append("非負溢價")
    if r["ky"]: reason.append("KY股")
    if r["state"] in ("stock_warn","stock_margin_upcoming"): reason.append(r["state_label"])
    print(f"  {r['code']} {r['name']}  溢價{r['premium']}%  gap{r['gap']}%  {r['optionality']}  原因:{','.join(reason)}")

print(f"\nC級（有嚴重限制旗標，暫不建議）: {len(C)} 檔")
for r in C:
    print(f"  {r['code']} {r['name']}  溢價{r['premium']}%  {r['state_label']}")

print(f"\nD級（新券/流動性存疑，未查發行日期與閉鎖期前不得視為可執行候選，含2026-07-25踢爆的霖宏二案例）: {len(D)} 檔")
for r in D:
    print(f"  {r['code']} {r['name']}  溢價{r['premium']}%  {r['fresh']}")
