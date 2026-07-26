# -*- coding: utf-8 -*-
"""免登入、免瀏覽器抓取全市場CB資料，取代每天手動開XQ桌面程式匯出CSV。

資料來源（皆免登入，純requests）：
  1. TDCC臺灣集中保管結算所「可轉換公司債月分析表」-> 全市場CB代碼/名稱清單(377檔)+官方保管張數(月頻率)
  2. thefew.tw/quote/{code} -> 個股轉換條款+每日價格/溢價率/已轉換%(伺服器端渲染，免登入)
  3. thefew.tw/api/prices/{chart_id} -> 逐日OHLC+volume

輸出：xq_cb_master_auto.csv，欄位盡量對齊xq_cb_master.csv（parse_xq_csv.py的FIELDS），
方便之後跟手動匯出的版本並排比對，決定是否切換。目前無法從thefew取得的欄位
(coupon_pct/collateral明確文字/stop_conv_start/stop_conv_end/shares_per_lot)留空，
需之後另外從MOPS/TPEx發行辦法backfill一次，非本script範圍。

用法：
  python fetch_cb_public_sources.py --limit 5      # 先測前5檔
  python fetch_cb_public_sources.py                # 全市場跑一次

★已知重大限制(2026-07-26實測確認，勿忽略)：
  thefew.tw的「目前轉換價」(conv_price)對部分CB是舊資料，會漏掉除權息/重設條款觸發的
  轉換價向下調整——已用華友聯三(14363)+華友聯四(14364)驗證：thefew顯示這兩檔「目前轉換價」
  等於「發行時轉換價」(代表thefew認為從未調整過)，但華友聯(1436)本尊在2025/07/21有大額
  除權息(現金9.796元+股票股利3.014元)，理論上必然觸發formula-driven轉換價向下調整；
  對比Evan手動XQ匯出的同兩檔轉換價，果然比thefew低約41.7~41.8%(兩檔比例幾乎相同，
  符合"同一次除權息事件、同一公式"的預期)。
  => conv_price、以及依賴它算出的conv_value/premium_pct/converted_pct，在thefew這條全自動
     管線裡都不可視為可靠，除非額外對每檔逐一核對MOPS轉換價格調整公告。
  => 目前可信賴的欄位：cb_price、stock_price、next_put_date/next_put_price、volume(已除以1000
     校正單位)、TDCC官方月頻「保管張數」交叉驗證。這組欄位剛好完全涵蓋cbput(賣回排行)的需求，
     但不足以支撐cbmon(強贖/溢價)這種依賴conv_price的分析。
"""
import argparse
import csv
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).parent.parent
OUT_PATH = BASE / "xq_cb_master_auto.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

FIELDS = [
    "code", "name",
    "cb_price", "volume", "avg_volume_5d", "stock_price",
    "conv_value", "premium_pct",
    "conv_price_eff_date", "conv_price", "conv_price_orig", "stock_code", "shares_per_lot",
    "stop_conv_start", "stop_conv_end",
    "next_put_date", "next_put_price", "ytp_pct", "ytm_pct",
    "issue_date", "maturity_date", "issued_lots", "remaining_lots",
    "converted_pct", "coupon_pct", "collateral",
    "chart_stock_id", "source",
    "tdcc_remaining_lots", "tdcc_remaining_lots_prev_month", "tdcc_change_pct", "tdcc_data_month",
]

TDCC_URL = "https://www.tdcc.com.tw/portal/zh/QStatWAR/indm004"


def discover_universe(session):
    """打TDCC「可轉換公司債月分析表」，回傳全市場CB清單。
    表單有CSRF token但免登入：先GET拿token，再POST(scope=all)即可拿全部。"""
    r1 = session.get(TDCC_URL, headers=HEADERS, timeout=20)
    r1.raise_for_status()
    token = re.search(r'name="SYNCHRONIZER_TOKEN" value="([^"]+)"', r1.text).group(1)
    uri = re.search(r'name="SYNCHRONIZER_URI" value="([^"]+)"', r1.text).group(1)

    payload = {
        "SYNCHRONIZER_TOKEN": token,
        "SYNCHRONIZER_URI": uri,
        "method": "submit",
        "scope": "all",
        "stockNo": "",
        "stockName": "",
    }
    r2 = session.post(TDCC_URL, headers=HEADERS, data=payload, timeout=30)
    r2.raise_for_status()

    soup = BeautifulSoup(r2.text, "html.parser")
    data_month_match = re.search(r"資料年月：(\d+)", r2.text)
    data_month = data_month_match.group(1) if data_month_match else None

    universe = []
    for tr in soup.select("table.table tr"):
        tds = tr.find_all("td")
        if len(tds) != 7:
            continue
        code = tds[0].get_text(strip=True)
        name = tds[1].get_text(strip=True)
        this_month_lots = tds[2].get_text(strip=True).replace(",", "")
        prev_month_lots = tds[3].get_text(strip=True).replace(",", "")
        change = tds[4].get_text(strip=True).replace(",", "")
        change_pct = tds[5].get_text(strip=True)
        holders = tds[6].get_text(strip=True).replace(",", "")
        universe.append({
            "code": code,
            "name": name,
            "tdcc_custody_lots_this_month": this_month_lots,
            "tdcc_custody_lots_prev_month": prev_month_lots,
            "tdcc_change_lots": change,
            "tdcc_change_pct": change_pct,
            "tdcc_holder_count": holders,
            "tdcc_data_month": data_month,
        })
    return universe


LABEL_MAP = {
    "可轉債名稱": "name_full",
    "轉換標的名稱": "underlying_name",
    "上市櫃別": "market",
    "擔保銀行/TCRI信用評等": "collateral_tcri_raw",
    "最新 CB 收盤價": "cb_price_raw",
    "轉換價值": "conv_value",
    "轉換溢價率": "premium_pct",
    "最新股票收盤價": "stock_price_raw",
    "目前轉換價": "conv_price",
    "發行時轉換價": "conv_price_orig",
    "發行價格": "issue_price",
    "發行總額(百萬)": "issued_total_million",
    "最新餘額(百萬)": "remaining_total_million",
    "轉換比例": "converted_pct",
    "發行日": "issue_date_raw",
    "到期日": "maturity_date_raw",
    "到期賣回價格": "maturity_put_price",
    "下次提前賣回日": "next_put_date_raw",
    "下次提前賣回價格": "next_put_price",
}


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _first_number(s):
    """'99.4 (+0.1%)' -> 99.4"""
    if not s:
        return None
    m = re.match(r"^-?[\d,]+\.?\d*", s.strip())
    return _num(m.group(0)) if m else None


def _reformat_date(s):
    """'2026-08-12' -> '2026/08/12'（比照xq_cb_master.csv的日期格式）"""
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s.strip())
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else s


def fetch_thefew_quote(session, code):
    url = f"https://thefew.tw/quote/{code}"
    r = session.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    raw = {}
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            label = tds[0].get_text(strip=True)
            value = tds[1].get_text(" ", strip=True)
            if label in LABEL_MAP:
                raw[LABEL_MAP[label]] = value

    chart_id_tag = soup.find(attrs={"data-cb-chart-stock-id-value": True})
    chart_stock_id = chart_id_tag["data-cb-chart-stock-id-value"] if chart_id_tag else None

    return {
        "cb_price": _first_number(raw.get("cb_price_raw")),
        "stock_price": _first_number(raw.get("stock_price_raw")),
        "conv_value": _num(raw.get("conv_value")),
        "premium_pct": _num(raw.get("premium_pct")),
        "conv_price": _num(raw.get("conv_price")),
        "conv_price_orig": _num(raw.get("conv_price_orig")),
        "converted_pct": _num(raw.get("converted_pct")),
        "issue_date": _reformat_date(raw.get("issue_date_raw")),
        "maturity_date": _reformat_date(raw.get("maturity_date_raw")),
        "maturity_put_price": _num(raw.get("maturity_put_price")),
        "next_put_date": _reformat_date(raw.get("next_put_date_raw")),
        "next_put_price": _num(raw.get("next_put_price")),
        "issued_total_million": _num(raw.get("issued_total_million")),
        "remaining_total_million": _num(raw.get("remaining_total_million")),
        "market": raw.get("market"),
        "collateral_tcri_raw": raw.get("collateral_tcri_raw"),
        "chart_stock_id": chart_stock_id,
    }


def fetch_thefew_volume(session, chart_stock_id, days=6):
    if not chart_stock_id:
        return None, None
    url = f"https://thefew.tw/api/prices/{chart_stock_id}?days={days}"
    r = session.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        return None, None
    data = r.json().get("data", [])
    if not data:
        return None, None
    # thefew回傳單位是「股」，XQ的volume欄位單位是「張」(1張=1000)，
    # 已用manual xq_cb_master.csv實測比對驗證(47000/47=1000, 4000/4=1000, 70000/70=1000)
    latest_volume = data[-1].get("volume")
    latest_volume_lots = latest_volume / 1000 if latest_volume is not None else None
    vols = [d.get("volume") for d in data if d.get("volume") is not None]
    avg_5d_lots = (sum(vols) / len(vols) / 1000) if vols else None
    return latest_volume_lots, avg_5d_lots


def derive_stock_code(cb_code):
    """CB代碼慣例＝4碼正股代碼+1~2碼系列序號(如14363->1436, 140201->1402)。"""
    cb_code = cb_code.strip()
    if len(cb_code) == 5:
        return cb_code[:4]
    if len(cb_code) == 6:
        return cb_code[:4]
    return cb_code[:4] if len(cb_code) > 4 else cb_code


def compute_ytp(cb_price, put_price, put_date_str, today=None):
    """比照put_yield_ranking.py既有算法：(1+簡單報酬率)^(365/天數) - 1"""
    if cb_price is None or put_price is None or not put_date_str:
        return None
    try:
        put_date = datetime.strptime(put_date_str, "%Y/%m/%d").date()
    except ValueError:
        return None
    today = today or date.today()
    days = (put_date - today).days
    if days <= 0:
        return None
    simple_return = (put_price - cb_price) / cb_price
    return ((1 + simple_return) ** (365 / days) - 1) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只跑前N檔（測試用）")
    ap.add_argument("--delay", type=float, default=0.5, help="每檔請求間隔秒數")
    args = ap.parse_args()

    session = requests.Session()

    print("Step 1: 從TDCC抓全市場CB清單...")
    universe = discover_universe(session)
    print(f"  拿到 {len(universe)} 檔（TDCC資料年月：{universe[0]['tdcc_data_month'] if universe else '?'}）")

    if args.limit:
        universe = universe[: args.limit]

    rows = []
    errors = []
    for i, u in enumerate(universe, 1):
        code = u["code"]
        try:
            q = fetch_thefew_quote(session, code)
            if q is None:
                errors.append((code, u["name"], "quote頁404或無法解析"))
                continue
            volume, avg_5d = fetch_thefew_volume(session, q.get("chart_stock_id"))

            ytp = compute_ytp(q["cb_price"], q["next_put_price"], q["next_put_date"])
            ytm = compute_ytp(q["cb_price"], q["maturity_put_price"], q["maturity_date"])

            issued_lots = round(q["issued_total_million"] * 10) if q["issued_total_million"] is not None else None
            remaining_lots = round(q["remaining_total_million"] * 10) if q["remaining_total_million"] is not None else None

            rows.append({
                "code": code,
                "name": u["name"],
                "cb_price": q["cb_price"],
                "volume": volume,
                "avg_volume_5d": round(avg_5d, 0) if avg_5d is not None else None,
                "stock_price": q["stock_price"],
                "conv_value": q["conv_value"],
                "premium_pct": q["premium_pct"],
                "conv_price_eff_date": None,
                "conv_price": q["conv_price"],
                "conv_price_orig": q["conv_price_orig"],
                "stock_code": derive_stock_code(code),
                "shares_per_lot": None,
                "stop_conv_start": None,
                "stop_conv_end": None,
                "next_put_date": q["next_put_date"],
                "next_put_price": q["next_put_price"],
                "ytp_pct": round(ytp, 2) if ytp is not None else None,
                "ytm_pct": round(ytm, 2) if ytm is not None else None,
                "issue_date": q["issue_date"],
                "maturity_date": q["maturity_date"],
                "issued_lots": issued_lots,       # 來自thefew「發行總額(百萬)」×10（1張=10萬面額）
                "remaining_lots": remaining_lots,  # 來自thefew「最新餘額(百萬)」×10，較即時
                "converted_pct": q["converted_pct"],
                "coupon_pct": None,
                "collateral": q["collateral_tcri_raw"],
                "chart_stock_id": q["chart_stock_id"],
                "source": "thefew.tw+tdcc.com.tw",
                "tdcc_remaining_lots": u["tdcc_custody_lots_this_month"],       # TDCC官方月頻率交叉驗證
                "tdcc_remaining_lots_prev_month": u["tdcc_custody_lots_prev_month"],
                "tdcc_change_pct": u["tdcc_change_pct"],
                "tdcc_data_month": u["tdcc_data_month"],
            })
        except Exception as e:
            errors.append((code, u["name"], str(e)))

        if i % 20 == 0:
            print(f"  進度 {i}/{len(universe)}...")
        time.sleep(args.delay)

    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n完成：{len(rows)} 檔成功，{len(errors)} 檔失敗")
    print(f"輸出：{OUT_PATH}")
    if errors:
        print("失敗清單（前20筆）：")
        for code, name, msg in errors[:20]:
            print(f"  {code} {name}: {msg}")


if __name__ == "__main__":
    main()
