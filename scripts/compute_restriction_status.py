# -*- coding: utf-8 -*-
"""
讀取 thefew_low_premium_full.csv + TWSE/TPEx OpenAPI 即時清單，
計算每檔候選 CB 的「限制狀態」七態分類，輸出給 public/index.html 使用。
"""
import csv
import json
import re
from pathlib import Path

BASE = Path(r"C:\Users\Evan\Desktop\Claude工作區\可轉債套利研究")
SCRATCH = Path(r"C:\Users\Evan\AppData\Local\Temp\claude\C--Users-Evan\34aa5e67-5c4a-4480-8f18-9c9bda01dc4c\scratchpad\cbmon")

def load_json(name):
    with open(SCRATCH / name, encoding="utf-8-sig") as f:
        return json.load(f)

twse_punish = load_json("twse_punish.json")
twse_notice = load_json("twse_notice.json")
tpex_warn = load_json("tpex_warn.json")
tpex_disp = load_json("tpex_disp.json")
tpex_margin_term = load_json("tpex_margin_term.json")

# --- 建立各清單的代碼集合 ---
# TPEx 注意股（正股）
warn_codes = {row["SecuritiesCompanyCode"] for row in tpex_warn if row.get("SecuritiesCompanyCode")}

# TPEx 處置（可能是正股代碼，也可能是 CB 代碼本身）
disp_codes = {row["SecuritiesCompanyCode"] for row in tpex_disp if row.get("SecuritiesCompanyCode")}

# TPEx 暫停融券賣出預告（正股）：分「進行中」與「即將」
# 用 Date 欄位（查詢當下日期）跟 Start/End 比較；Date 本身就是今天，直接看 Start<=Date<=End 或 Start>Date
active_margin_susp = set()
upcoming_margin_susp = set()
for row in tpex_margin_term:
    code = row.get("SecuritiesCompanyCode")
    if not code:
        continue
    today = row.get("Date", "")
    start = row.get("ShortSaleSuspensionStartDate", "")
    end = row.get("ShortSaleSuspensionEndDate", "")
    if start <= today <= end:
        active_margin_susp.add(code)
    elif start > today:
        upcoming_margin_susp.add(code)

# TWSE 上市：處置 / 注意
twse_punish_codes = {row["Code"] for row in twse_punish if row.get("Code")}
twse_notice_codes = {row["Code"] for row in twse_notice if row.get("Code")}

def underlying_code(cb_code: str) -> str:
    """CB 代碼前 4 碼＝正股代碼（如 61827 -> 6182，629010 -> 6290）"""
    m = re.match(r"^(\d{4})", cb_code)
    return m.group(1) if m else ""

STATE_PRIORITY = [
    # (state_key, state_label_zh)
    ("cb_disp", "CB處置"),
    ("stock_disp", "正股處置"),
    ("stock_margin_active", "正股暫停融券"),
    ("stock_margin_upcoming", "即將暫停融券"),
    ("stock_warn", "正股注意"),
    ("unresolved", "需人工問券商"),
    ("clear", "可觀察"),
]

def classify(cb_code: str, name: str):
    stock_code = underlying_code(cb_code)
    flags = []

    if not stock_code:
        return "unresolved", ["代碼格式無法解析"]

    # CB 本身是否處置（CB 代碼直接出現在處置清單）
    if cb_code in disp_codes:
        flags.append("cb_disp")
    # 正股處置（上市 punish 或 上櫃 disp 命中正股代碼）
    if stock_code in disp_codes or stock_code in twse_punish_codes:
        flags.append("stock_disp")
    # 正股暫停融券（進行中）
    if stock_code in active_margin_susp:
        flags.append("stock_margin_active")
    # 正股暫停融券（即將）
    if stock_code in upcoming_margin_susp:
        flags.append("stock_margin_upcoming")
    # 正股注意
    if stock_code in warn_codes or stock_code in twse_notice_codes:
        flags.append("stock_warn")

    if not flags:
        return "clear", []

    # 依優先序取最嚴重的當主狀態
    for key, _ in STATE_PRIORITY:
        if key in flags:
            return key, flags
    return "clear", []

def main():
    rows = []
    with open(BASE / "thefew_low_premium_full.csv", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    results = []
    for r in rows:
        code = r["代碼"].strip()
        name = r["名稱"].strip()
        gap_raw = r["離強贖門檻(%)"].strip()
        conv_raw = r["已轉換%"].strip().rstrip("%")
        maturity = r["到期/賣回日"].strip()
        try:
            gap = float(gap_raw)
        except ValueError:
            continue
        try:
            conv = float(conv_raw)
        except ValueError:
            conv = None

        state_key, flags = classify(code, name)
        results.append({
            "code": code,
            "name": name,
            "gap": gap,
            "conv": conv,
            "maturity": maturity,
            "underlying": underlying_code(code),
            "state": state_key,
            "flags": flags,
        })

    # --- 輸出統計 ---
    from collections import Counter
    state_labels = dict(STATE_PRIORITY)
    counter = Counter(r["state"] for r in results)
    print("=== 全部 439 檔限制狀態統計 ===")
    for key, label in STATE_PRIORITY:
        print(f"{label:12s} {counter.get(key, 0)}")

    print("\n=== 候選名單 (gap>=15%, conv<30%) 中有限制旗標的標的 ===")
    for r in results:
        if r["gap"] >= 15 and (r["conv"] is None or r["conv"] < 30) and r["state"] != "clear":
            print(f"{r['code']:8s} {r['name']:14s} gap={r['gap']:8.1f}% conv={r['conv']}% state={state_labels[r['state']]} flags={r['flags']}")

    # 輸出 JSON 給 HTML 用
    out_path = BASE / "restriction_status.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n已輸出：{out_path}")

if __name__ == "__main__":
    main()
