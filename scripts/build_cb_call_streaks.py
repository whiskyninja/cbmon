# 來源註記：這是 Codex 弄的。
# -*- coding: utf-8 -*-
r"""建立全市場 CB 強贖價格條件的逐日稽核資料。

資料來源：
- 正股收盤價：TWSE / TPEx 官方每日全市場盤後資料。
- 轉換價：目前 xq_cb_master.csv，加上 Drea\XQ 的歷史日快照。

只有最近 30 個市場營業日都能找到有效收盤價與當日轉換價時，
data_quality 才會標示 complete；否則不會宣稱已達 30/30。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests


BASE = Path(__file__).resolve().parent.parent
MASTER_CSV = BASE / "xq_cb_master.csv"
OUT_JSON = BASE / "cb_call_streak.json"
PUBLIC_JSON = BASE / "public" / "data" / "cb_call_streak.json"
CACHE_DIR = BASE / ".cache" / "cb_call_streaks"
DEFAULT_XQ_DIR = Path(r"C:\Users\Evan\我的雲端硬碟\Drea\XQ")
LOOKBACK_MARKET_DAYS = 70
AUDIT_DAYS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "---", "N/A", "除權", "除息"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def read_master() -> list[dict[str, str]]:
    with MASTER_CSV.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def dated_xq_files(xq_dir: Path, as_of: date | None = None) -> list[tuple[date, Path]]:
    found: list[tuple[date, Path]] = []
    for path in xq_dir.glob("*.csv"):
        if not re.fullmatch(r"\d{8}\.csv", path.name):
            continue
        snapshot_date = datetime.strptime(path.stem, "%Y%m%d").date()
        if as_of is None or snapshot_date <= as_of:
            found.append((snapshot_date, path))
    return sorted(found)


def parse_xq_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    """只讀 XQ 原始快照的 CB 代碼、目前轉換價與該價格生效日。"""
    result: dict[str, dict[str, Any]] = {}
    with path.open(encoding="cp950", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    for raw in rows[3:]:
        if len(raw) < 8:
            continue
        def unwrap(cell: str) -> str:
            text = cell.strip()
            return text[2:-1] if text.startswith('="') and text.endswith('"') else text

        name_cell = unwrap(raw[0])
        match = re.search(r"\(([A-Za-z0-9]+)\)\s*$", name_cell)
        if not match:
            continue
        price = to_float(unwrap(raw[7]))
        effective_text = unwrap(raw[6])
        effective = parse_iso_date(effective_text)
        if price and price > 0:
            result[match.group(1)] = {
                "price": price,
                "effective_date": effective.isoformat() if effective else None,
            }
    return result


def cached_json(session: requests.Session, cache_path: Path, url: str) -> dict[str, Any]:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.08)
    return data


def parse_twse(payload: dict[str, Any]) -> dict[str, float]:
    for table in payload.get("tables") or []:
        fields = [str(x).strip() for x in table.get("fields") or []]
        if "證券代號" not in fields or "收盤價" not in fields:
            continue
        code_i, close_i = fields.index("證券代號"), fields.index("收盤價")
        return {
            str(row[code_i]).strip(): close
            for row in table.get("data") or []
            if (close := to_float(row[close_i])) is not None
        }
    return {}


def parse_tpex(payload: dict[str, Any]) -> dict[str, float]:
    for table in payload.get("tables") or []:
        fields = [str(x).strip() for x in table.get("fields") or []]
        code_field = next((x for x in fields if x == "代號"), None)
        close_field = next((x for x in fields if x == "收盤"), None)
        if not code_field or not close_field:
            continue
        code_i, close_i = fields.index(code_field), fields.index(close_field)
        return {
            str(row[code_i]).strip(): close
            for row in table.get("data") or []
            if (close := to_float(row[close_i])) is not None
        }
    return {}


def fetch_market_history(as_of: date) -> list[dict[str, Any]]:
    session = requests.Session()
    days: list[dict[str, Any]] = []
    cursor = as_of
    attempts = 0
    while len(days) < LOOKBACK_MARKET_DAYS and attempts < 140:
        attempts += 1
        if cursor.weekday() < 5:
            ymd = cursor.strftime("%Y%m%d")
            iso = cursor.strftime("%Y/%m/%d")
            twse_url = (
                "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                f"?date={ymd}&type=ALLBUT0999&response=json"
            )
            tpex_url = (
                "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
                f"?date={iso}&type=EW&response=json"
            )
            twse = parse_twse(cached_json(session, CACHE_DIR / f"twse_{ymd}.json", twse_url))
            tpex = parse_tpex(cached_json(session, CACHE_DIR / f"tpex_{ymd}.json", tpex_url))
            if twse or tpex:
                days.append({"date": cursor.isoformat(), "twse": twse, "tpex": tpex})
        cursor -= timedelta(days=1)
    if len(days) < AUDIT_DAYS:
        raise RuntimeError(f"官方行情僅取得 {len(days)} 個市場營業日，少於 {AUDIT_DAYS} 日")
    return sorted(days, key=lambda row: row["date"])


def conversion_price_for_day(
    cb_code: str,
    day: date,
    current_price: float,
    current_effective: date | None,
    snapshots: list[tuple[date, dict[str, dict[str, Any]]]],
) -> tuple[float | None, str]:
    regimes: dict[date, tuple[float, str]] = {}
    for snapshot_date, prices in snapshots:
        item = prices.get(cb_code)
        if not item:
            continue
        effective = parse_iso_date(item.get("effective_date"))
        if effective:
            regimes[effective] = (float(item["price"]), f"XQ {snapshot_date.isoformat()}")
    if current_effective:
        regimes[current_effective] = (current_price, f"XQ 生效日 {current_effective.isoformat()}")
    applicable = [(effective, value) for effective, value in regimes.items() if effective <= day]
    if applicable:
        _, (price, source) = max(applicable, key=lambda pair: pair[0])
        return price, source
    if current_effective is None:
        return current_price, "XQ 目前轉換價（無生效日）"
    return None, "缺少調價前 XQ/MOPS 歷史"


def build_record(
    row: dict[str, str],
    market_days: list[dict[str, Any]],
    snapshots: list[tuple[date, dict[str, dict[str, Any]]]],
) -> dict[str, Any]:
    cb_code = row["code"]
    underlying = cb_code[:4]
    current_price = to_float(row.get("conv_price"))
    current_effective = parse_iso_date(row.get("conv_price_eff_date"))
    warnings: list[str] = []
    if current_price is None or current_price <= 0:
        return {
            "cb_code": cb_code, "underlying_code": underlying, "current_streak": 0,
            "days_remaining": 30, "price_condition_met": False,
            "last_failed_date": None, "data_quality": "incomplete",
            "warnings": ["缺少目前轉換價"], "history": [],
        }

    latest_market = market_days[-1]
    if underlying in latest_market["twse"]:
        market = "TWSE"
    elif underlying in latest_market["tpex"]:
        market = "TPEx"
    else:
        market = "unknown"
        warnings.append("無法在最新官方行情辨識正股市場")

    full_history: list[dict[str, Any]] = []
    for market_day in market_days:
        day = date.fromisoformat(market_day["date"])
        close = None if market == "unknown" else market_day[market.lower()].get(underlying)
        conv_price, conv_source = conversion_price_for_day(
            cb_code, day, current_price, current_effective, snapshots
        )
        threshold = round(conv_price * 1.3, 4) if conv_price is not None else None
        passed = bool(close is not None and threshold is not None and close >= threshold)
        issue = None
        if close is None:
            issue = "無有效收盤價／可能停牌"
        elif conv_price is None:
            issue = "缺少當日有效轉換價"
        full_history.append({
            "date": day.isoformat(),
            "close": close,
            "conversion_price": conv_price,
            "threshold_130": threshold,
            "passed": passed,
            "market": market,
            "price_source": f"{market} 官方盤後資料" if market != "unknown" else "缺少",
            "conversion_source": conv_source,
            "issue": issue,
        })

    history = full_history[-AUDIT_DAYS:]
    complete = all(item["close"] is not None and item["conversion_price"] is not None for item in history)
    streak = 0
    for item in reversed(full_history):
        if item["passed"]:
            streak += 1
        else:
            break
    last_failed = next((item["date"] for item in reversed(history) if not item["passed"]), None)
    rolling = 0
    qualified_indexes: list[int] = []
    for index, item in enumerate(full_history):
        if item["passed"]:
            rolling += 1
            if rolling >= AUDIT_DAYS:
                qualified_indexes.append(index)
        else:
            rolling = 0
    qualified_index = qualified_indexes[-1] if qualified_indexes else None
    qualified_on = full_history[qualified_index]["date"] if qualified_index is not None else None
    days_since_qualification = (
        len(full_history) - 1 - qualified_index if qualified_index is not None else None
    )
    redemption_window_active = bool(
        days_since_qualification is not None and days_since_qualification <= AUDIT_DAYS
    )
    if not complete:
        warnings.append("最近30個營業日存在缺價，結果不可視為法律資格確認")
    return {
        "cb_code": cb_code,
        "underlying_code": underlying,
        "market": market,
        "current_streak": streak,
        "days_remaining": max(0, AUDIT_DAYS - streak),
        "price_condition_met": bool(complete and streak >= AUDIT_DAYS),
        "qualified_on": qualified_on,
        "business_days_since_qualification": days_since_qualification,
        "redemption_window_active": redemption_window_active,
        "last_failed_date": last_failed,
        "data_quality": "complete" if complete else "incomplete",
        "warnings": warnings,
        "history": history,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xq-dir", type=Path, default=DEFAULT_XQ_DIR)
    parser.add_argument("--as-of", help="YYYY-MM-DD；預設使用最新的純日期 XQ CSV")
    args = parser.parse_args()

    explicit_as_of = parse_iso_date(args.as_of) if args.as_of else None
    xq_files = dated_xq_files(args.xq_dir, explicit_as_of)
    if not xq_files:
        raise RuntimeError(f"找不到 XQ 日期快照：{args.xq_dir}")
    as_of = explicit_as_of or xq_files[-1][0]
    xq_files = [(d, p) for d, p in xq_files if d <= as_of]
    snapshots = [(d, parse_xq_snapshot(path)) for d, path in xq_files]
    market_days = fetch_market_history(as_of)
    master_rows = read_master()
    records = [build_record(row, market_days, snapshots) for row in master_rows]
    by_code = {record["cb_code"]: record for record in records}
    summary = {
        "as_of": as_of.isoformat(),
        "market_days": len(market_days),
        "audit_days": AUDIT_DAYS,
        "total": len(records),
        "met_30": sum(1 for r in records if r["price_condition_met"]),
        "redemption_window_active": sum(1 for r in records if r.get("redemption_window_active")),
        "streak_20_29": sum(1 for r in records if r["data_quality"] == "complete" and 20 <= r["current_streak"] < 30),
        "incomplete": sum(1 for r in records if r["data_quality"] != "complete"),
        "sources": {
            "stock_prices": "TWSE/TPEx 官方每日盤後資料",
            "conversion_prices": "XQ 每日快照與目前轉換價",
        },
    }
    payload = {"summary": summary, "by_code": by_code}
    rendered = json.dumps(payload, ensure_ascii=False, indent=1)
    public_by_code = {}
    for code, record in by_code.items():
        slim = {key: value for key, value in record.items() if key != "history"}
        slim["history"] = [
            {key: item.get(key) for key in (
                "date", "close", "conversion_price", "threshold_130", "passed", "issue"
            )}
            for item in record.get("history", [])
        ]
        public_by_code[code] = slim
    public_payload = {"summary": summary, "by_code": public_by_code}
    compact_rendered = json.dumps(public_payload, ensure_ascii=False, separators=(",", ":"))
    OUT_JSON.write_text(rendered, encoding="utf-8")
    PUBLIC_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_JSON.write_text(compact_rendered, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"輸出：{OUT_JSON}")
    print(f"網站：{PUBLIC_JSON}")


if __name__ == "__main__":
    main()
