# 來源註記：這是 Codex 弄的。
# -*- coding: utf-8 -*-
"""用今日manual xq_cb_master.csv(XQ匯出，conv_price可信)重新計算cbmon強贖候選名單。

取代原本2026-07-17基於thefew.tw掃描結果的靜態候選名單——那批資料的conv_price
後來被證實系統性不可靠(見[[project-cb-arbitrage-research]])，manual XQ匯出的
conv_price沒有這個問題，且每天已經在為cbput更新，順便拿來重建cbmon是正確方向。

離強贖門檻% = (股票收盤價 − 轉換價) ÷ 轉換價 × 100
依證券商業同業公會自律規則第16條，需連續30個營業日 ≥ 30% 公司才可強制贖回。

三層分類(沿用原始public/index.html的邏輯)：
  候選名單：15% <= gap <= 100% 且 已轉換% < 30%（籌碼還沒被收割，值得盯）
  已收割/訊號偏晚：gap >= 30% 且 已轉換% >= 30%（大戶已轉股出脫，訊號偏晚）
  極端值：gap > 100% 且 已轉換% < 30%（多半是深度價內債，需個別查證非新訊號）

限制狀態(注意股/處置股/暫停融券)沿用restriction_status.json(2026-07-18查詢，
已過期，非本次重新查證範圍)，找不到對應代碼的一律標"clear"。

用法：python build_cbmon_candidates.py
"""
import csv
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
MASTER_CSV = BASE / "xq_cb_master.csv"
RESTRICTION_JSON = BASE / "restriction_status.json"
OUT_JSON = BASE / "cbmon_candidates_new.json"
STREAK_JSON = BASE / "cb_call_streak.json"


def load_restriction_map():
    if not RESTRICTION_JSON.exists():
        return {}
    with open(RESTRICTION_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    return {r["code"]: r["state"] for r in rows}


def to_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main():
    with open(MASTER_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    restriction_map = load_restriction_map()
    streak_map = {}
    streak_summary = {}
    if STREAK_JSON.exists():
        with open(STREAK_JSON, encoding="utf-8") as f:
            streak_payload = json.load(f)
        streak_map = streak_payload.get("by_code", {})
        streak_summary = streak_payload.get("summary", {})

    parsed = []
    skipped_no_price = 0
    for r in rows:
        stock_price = to_float(r.get("stock_price"))
        conv_price = to_float(r.get("conv_price"))
        converted_pct = to_float(r.get("converted_pct"))
        if stock_price is None or conv_price is None or conv_price == 0:
            skipped_no_price += 1
            continue
        gap = (stock_price - conv_price) / conv_price * 100
        maturity = r.get("next_put_date") or r.get("maturity_date") or ""
        state = restriction_map.get(r["code"], "clear")
        streak = streak_map.get(r["code"], {})
        parsed.append({
            "code": r["code"],
            "name": r["name"],
            "gap": round(gap, 1),
            "conv": converted_pct if converted_pct is not None else 0.0,
            "maturity": maturity,
            "state": state,
            "streak": int(streak.get("current_streak", 0)),
            "streak_quality": streak.get("data_quality", "incomplete"),
            "last_failed_date": streak.get("last_failed_date"),
            "redemption_window_active": bool(streak.get("redemption_window_active", False)),
            "qualified_on": streak.get("qualified_on"),
        })

    candidates = [r for r in parsed if 15 <= r["gap"] <= 100 and r["conv"] < 30]
    harvested = [r for r in parsed if r["gap"] >= 30 and r["conv"] >= 30]
    outliers = [r for r in parsed if r["gap"] > 100 and r["conv"] < 30]

    def rank_key(x):
        quality_rank = 0 if x["streak_quality"] == "complete" else 1
        qualified_rank = 0 if x["redemption_window_active"] else 1
        return (qualified_rank, quality_rank, -x["streak"], -x["gap"], x["conv"])

    candidates.sort(key=rank_key)
    harvested.sort(key=rank_key)
    outliers.sort(key=rank_key)

    out = {"candidates": candidates, "harvested": harvested, "outliers": outliers,
           "total": len(rows), "skipped_no_price": skipped_no_price,
           "streak_summary": streak_summary}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"全市場 {len(rows)} 檔，{skipped_no_price} 檔缺股價/轉換價無法算gap")
    print(f"候選名單 {len(candidates)} 檔 / 已收割 {len(harvested)} 檔 / 極端值 {len(outliers)} 檔")
    print(f"輸出：{OUT_JSON}")


if __name__ == "__main__":
    main()
