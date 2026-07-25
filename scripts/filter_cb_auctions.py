import json
from datetime import datetime

with open("twse_auction_2026_full.json", "r", encoding="utf-8-sig") as f:
    rows = json.load(f)

today = datetime.strptime("2026-07-18", "%Y-%m-%d")

kept = []
for row in rows:
    r = row["value"] if isinstance(row, dict) and "value" in row else row
    # fields index: 0 seq,1 open date,2 name,3 code,4 market,5 kind,6 method,7 bidstart,8 bidend,
    # 9 qty,10 minprice,11 minlot,12 maxlot,13 margin%,14 procfee,15 issuedate,16 broker,
    # 17 totalamt,18 feerate,19 totalvalid,20 validqty,21 minwin,22 maxwin,23 weightedavg,24 actualprice,25 cancel
    kind = r[5]
    if kind not in ("有擔保轉換公司債", "無擔保轉換公司債"):
        continue
    cancel = r[25].strip() if len(r) > 25 else ""
    if cancel == "Y":
        continue
    weighted_avg = r[23].replace(",", "")
    try:
        weighted_avg = float(weighted_avg)
    except Exception:
        continue
    if weighted_avg <= 0:
        continue
    issue_date_raw = r[15]
    try:
        issue_date = datetime.strptime(issue_date_raw, "%Y/%m/%d")
    except Exception:
        continue
    if issue_date >= today:
        continue  # not listed yet
    name = r[2]
    code = r[3]
    minprice = float(r[10])
    kept.append({
        "code": code, "name": name, "weighted_avg": weighted_avg,
        "issue_date": issue_date.strftime("%Y-%m-%d"), "min_price": minprice,
        "near_floor": (weighted_avg - minprice) / minprice < 0.03
    })

kept.sort(key=lambda x: x["issue_date"])
print(f"符合條件(真CB、已撥券、非取消)共 {len(kept)} 檔:")
for k in kept:
    flag = " [近底價]" if k["near_floor"] else ""
    print(f"{k['code']:<8}{k['name']:<10}加權均價{k['weighted_avg']:>8.2f}  底價{k['min_price']:>7.2f}  撥券{k['issue_date']}{flag}")

with open("cb_auction_candidates.json", "w", encoding="utf-8") as f:
    json.dump(kept, f, ensure_ascii=False, indent=2)
