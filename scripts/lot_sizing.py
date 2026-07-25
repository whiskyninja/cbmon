# -*- coding: utf-8 -*-
"""買N張同一檔CB，湊出轉股股數最接近1000整數倍(零股餘數最小)的N，
讓避險（融券/SBL放空）能覆蓋到最大比例的股數。"""

candidates = {
    "台境二(84762)": 19.7,
    "倉和一(65381)": 104.38,
    "霖宏二(54642)": 33.4,
}

MAX_N = 30  # 上限：N=30張 = 300萬面額，個人合理測試範圍

for name, cp in candidates.items():
    print(f"\n=== {name}  轉換價={cp} ===")
    results = []
    for n in range(1, MAX_N + 1):
        total_shares = int(n * 100000 / cp)  # 無條件捨去，實務以券商計算為準
        odd = total_shares % 1000
        # 也考慮「差幾股就湊到下一個整數倍」的情況（比整股略少一點點也算好）
        dist_to_round = min(odd, 1000 - odd)
        results.append((n, total_shares, odd, dist_to_round))
    # 依 dist_to_round 排序，找最佳的幾個N
    best = sorted(results, key=lambda x: x[3])[:5]
    print(f"{'N(張)':>6s} {'面額(萬)':>8s} {'總股數':>8s} {'零股餘數':>8s} {'避險覆蓋率':>10s}")
    for n, shares, odd, dist in best:
        coverage = (shares - odd) / shares * 100
        face_wan = n * 10  # 每張10萬 = 10萬元 = 10萬/10000=10萬... 用「萬元」表示 n*100000/10000=n*10
        print(f"{n:6d} {face_wan:8d} {shares:8d} {odd:8d} {coverage:9.2f}%")
