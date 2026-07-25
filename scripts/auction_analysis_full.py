import json
import statistics
from datetime import datetime

with open("cb_auction_candidates.json", "r", encoding="utf-8") as f:
    candidates = json.load(f)
with open("auction_batch_full_dump.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

results = []
for c in candidates:
    code = c["code"]
    cost = c["weighted_avg"]
    listing = c["issue_date"]
    caps = raw.get(code, [])
    best = None
    for cap in caps:
        if isinstance(cap, dict) and "data" in cap:
            if best is None or len(cap["data"]) > len(best["data"]):
                best = cap
    if not best or not best.get("data"):
        results.append({**c, "d0_date": None, "d0_close": None, "d0_ret": None, "d5_ret": None})
        continue
    series = sorted(best["data"], key=lambda x: x["time"])
    on_after = [d for d in series if d["time"] >= listing]
    if not on_after:
        results.append({**c, "d0_date": None, "d0_close": None, "d0_ret": None, "d5_ret": None})
        continue
    day0 = on_after[0]
    day5 = on_after[5] if len(on_after) > 5 else on_after[-1]
    d0_ret = (day0["close"] - cost) / cost * 100
    d5_ret = (day5["close"] - cost) / cost * 100
    results.append({**c, "d0_date": day0["time"], "d0_close": day0["close"], "d0_ret": d0_ret, "d5_ret": d5_ret})

valid = [r for r in results if r["d0_ret"] is not None]
print(f"{'代碼':<8}{'名稱':<10}{'成本':>8}{'撥券日':<12}{'首日%':>8}{'+5日%':>8}  近底價")
for r in valid:
    flag = "Y" if r["near_floor"] else ""
    print(f"{r['code']:<8}{r['name']:<10}{r['weighted_avg']:>8.2f}{r['issue_date']:<12}{r['d0_ret']:>+8.1f}{r['d5_ret']:>+8.1f}  {flag}")

d0s = [r["d0_ret"] for r in valid]
d5s = [r["d5_ret"] for r in valid]
print(f"\n樣本數: {len(valid)}")
print(f"首日：平均{sum(d0s)/len(d0s):+.2f}%  中位數{statistics.median(d0s):+.2f}%  正報酬{sum(1 for x in d0s if x>0)}/{len(d0s)}  最小{min(d0s):+.1f}%  最大{max(d0s):+.1f}%")
print(f"+5日：平均{sum(d5s)/len(d5s):+.2f}%  中位數{statistics.median(d5s):+.2f}%  正報酬{sum(1 for x in d5s if x>0)}/{len(d5s)}  最小{min(d5s):+.1f}%  最大{max(d5s):+.1f}%")

near_floor = [r for r in valid if r["near_floor"]]
not_floor = [r for r in valid if not r["near_floor"]]
if near_floor:
    nf_d0 = [r["d0_ret"] for r in near_floor]
    print(f"\n近底價組(n={len(near_floor)})首日平均: {sum(nf_d0)/len(nf_d0):+.2f}%")
if not_floor:
    nof_d0 = [r["d0_ret"] for r in not_floor]
    print(f"非近底價組(n={len(not_floor)})首日平均: {sum(nof_d0)/len(nof_d0):+.2f}%")
