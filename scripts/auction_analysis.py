import json
from datetime import datetime, timedelta

with open("auction_batch_dump.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

# code: (name, weighted_avg_cost, listing_date)
meta = {
    "80963": ("擎亞三", 114.60, "2026-07-14"),
    "61876": ("萬潤六", 140.21, "2026-07-02"),
    "41904": ("佐登四KY", 100.00, "2026-06-30"),
    "32943": ("英濟三", 117.71, "2026-06-18"),
    "34913": ("昇達科三", 144.93, "2026-06-09"),
    "54642": ("霖宏二", 158.40, "2026-05-25"),
    "68032": ("崑鼎二", 102.48, "2026-05-21"),
    "41239": ("晟德九", 100.56, "2026-05-14"),
    "36806": ("家登六", 136.90, "2026-05-21"),
    "47148": ("永捷八", 113.43, "2026-05-04"),
}

results = []
for code, (name, cost, listing) in meta.items():
    caps = raw.get(code, [])
    # pick the response with the most data points (usually the largest 'days' query)
    best = None
    for c in caps:
        if isinstance(c, dict) and "data" in c:
            if best is None or len(c["data"]) > len(best["data"]):
                best = c
    if not best:
        results.append((code, name, cost, listing, None, None, None, None))
        continue
    series = sorted(best["data"], key=lambda x: x["time"])
    listing_dt = datetime.strptime(listing, "%Y-%m-%d")

    # first trading day on/after listing date
    on_after = [d for d in series if d["time"] >= listing]
    day0 = on_after[0] if on_after else None
    day5 = on_after[5] if len(on_after) > 5 else (on_after[-1] if on_after else None)

    d0_close = day0["close"] if day0 else None
    d5_close = day5["close"] if day5 else None
    d0_ret = (d0_close - cost) / cost * 100 if d0_close else None
    d5_ret = (d5_close - cost) / cost * 100 if d5_close else None

    results.append((code, name, cost, listing, day0["time"] if day0 else None, d0_close, d0_ret, d5_ret))

print(f"{'代碼':<8}{'名稱':<10}{'得標成本':>10}{'掛牌日':<12}{'首日日期':<12}{'首日收盤':>10}{'首日報酬%':>10}{'+5日報酬%':>10}")
rets0 = []
rets5 = []
for code, name, cost, listing, d0date, d0close, d0ret, d5ret in results:
    d0ret_s = f"{d0ret:+.1f}" if d0ret is not None else "N/A"
    d5ret_s = f"{d5ret:+.1f}" if d5ret is not None else "N/A"
    d0close_s = f"{d0close}" if d0close is not None else "N/A"
    print(f"{code:<8}{name:<10}{cost:>10.2f}{listing:<12}{str(d0date):<12}{d0close_s:>10}{d0ret_s:>10}{d5ret_s:>10}")
    if d0ret is not None:
        rets0.append(d0ret)
    if d5ret is not None:
        rets5.append(d5ret)

if rets0:
    print(f"\n首日平均報酬: {sum(rets0)/len(rets0):+.2f}%  (樣本數{len(rets0)})  正報酬檔數:{sum(1 for r in rets0 if r>0)}/{len(rets0)}")
if rets5:
    print(f"+5日平均報酬: {sum(rets5)/len(rets5):+.2f}%  (樣本數{len(rets5)})  正報酬檔數:{sum(1 for r in rets5 if r>0)}/{len(rets5)}")
