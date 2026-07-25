# -*- coding: utf-8 -*-
"""
可轉債(CB)套利兩個模型：
1. conversion_arbitrage()  — 負溢價/低溢價 CB 靜態轉換套利淨利試算
2. auction_expected_return() — CB初級市場競拍期望報酬(依歷史n=39統計)

公式來源：C:\\Users\\Evan\\.claude\\projects\\C--Users-Evan\\memory\\project-cb-arbitrage-research.md
(2026-07-18研究，含33571臺慶科一驗證案例、台境二/倉和一/霖宏二A級候選、
 39檔CB競拍全樣本統計)
"""

from dataclasses import dataclass, asdict


FACE_VALUE_PER_LOT = 100_000  # 1張CB面額


# ---------------------------------------------------------------------------
# 模型1：負溢價/低溢價 CB 靜態轉換套利
# ---------------------------------------------------------------------------

@dataclass
class ConversionArbitrageResult:
    conversion_shares: float       # 1張理論轉換股數
    hedgeable_shares: int          # 可放空避險的整股股數(1000股倍數)
    odd_lot_shares: float          # 無法避險的零股股數
    hedge_ratio: float             # 避險覆蓋率
    cb_cost: float                 # 買進CB總成本(元)
    conversion_value: float        # 轉換後理論股票價值(元)
    premium_rate: float            # 外一/CB溢價率(正=貴、負=便宜)
    gross_profit: float            # 毛利差(轉換價值-CB成本，未扣任何費用)
    tax: float                     # 證交稅(僅避險整股部分課徵0.3%)
    borrow_cost: float             # 借券/融券成本(依年利率*曝險天數)
    broker_fee: float              # 雙邊手續費估算(買CB+賣股)
    net_profit: float              # 淨利(毛利差-稅-借券-手續費)
    net_margin: float              # 淨利/CB成本
    odd_lot_exposure: float        # 零股部分無法避險的曝險金額(元，非成本，是風險)
    passes_safety_margin: bool     # 淨利率是否穿過安全邊際門檻


def conversion_arbitrage(
    cb_price: float,           # CB報價(每100面額，如206代表每10萬面額206,000元)
    conversion_price: float,   # 轉換價(元/股)
    stock_price: float,        # 正股現價(用可執行的外盤掛價，非收盤價)
    lots: int = 1,             # 買進張數(每張面額10萬)
    borrow_annual_rate: float = 0.03,   # SBL/融券年利率，依標的熱門度變動，需自行查證
    exposure_days: int = 8,             # 曝險天數(CB結算+轉換生效+撥券，經驗值約7~9個交易日)
    broker_fee_rate: float = 0.001425,  # 單邊手續費率，買賣各算一次
    tax_rate: float = 0.003,            # 證交稅率(僅股票賣出/現券償還這一邊課徵，CB本身賣出目前免稅)
    safety_margin: float = 0.03,        # 安全邊際門檻(淨利率需超過此值才算真正可執行，經驗值-3%~-4%成本後門檻)
) -> ConversionArbitrageResult:
    conversion_shares = FACE_VALUE_PER_LOT * lots / conversion_price
    hedgeable_shares = int(conversion_shares // 1000) * 1000
    odd_lot_shares = conversion_shares - hedgeable_shares
    hedge_ratio = hedgeable_shares / conversion_shares if conversion_shares else 0.0

    cb_cost = cb_price * 1000 * lots
    conversion_value = conversion_shares * stock_price
    premium_rate = (cb_cost - conversion_value) / conversion_value
    gross_profit = conversion_value - cb_cost

    tax = hedgeable_shares * stock_price * tax_rate
    borrow_cost = hedgeable_shares * stock_price * borrow_annual_rate * exposure_days / 365
    broker_fee = (cb_cost + hedgeable_shares * stock_price) * broker_fee_rate

    net_profit = gross_profit - tax - borrow_cost - broker_fee
    net_margin = net_profit / cb_cost if cb_cost else 0.0
    odd_lot_exposure = odd_lot_shares * stock_price

    return ConversionArbitrageResult(
        conversion_shares=conversion_shares,
        hedgeable_shares=hedgeable_shares,
        odd_lot_shares=odd_lot_shares,
        hedge_ratio=hedge_ratio,
        cb_cost=cb_cost,
        conversion_value=conversion_value,
        premium_rate=premium_rate,
        gross_profit=gross_profit,
        tax=tax,
        borrow_cost=borrow_cost,
        broker_fee=broker_fee,
        net_profit=net_profit,
        net_margin=net_margin,
        odd_lot_exposure=odd_lot_exposure,
        passes_safety_margin=net_margin >= safety_margin,
    )


# ---------------------------------------------------------------------------
# 模型2：CB初級市場競拍期望報酬(依2026-07-18查證的n=39全樣本統計)
# ---------------------------------------------------------------------------

# 全樣本統計(2026/01/15~07/14，39檔真CB競拍，已撥券掛牌，排除IPO股票類)
AUCTION_STATS_ALL = {
    "n": 39,
    "day1_mean": 0.0336,
    "day1_median": 0.0333,
    "day1_positive_ratio": 30 / 39,
    "day1_range": (-0.104, 0.100),
    "day5_mean": 0.0736,
    "day5_median": 0.0505,
    "day5_positive_ratio": 29 / 39,
    "day5_range": (-0.127, 0.340),
}

# 近底價因子分組(得標加權均價貼近最低投標底價，差距<3%)
AUCTION_STATS_NEAR_FLOOR = {"n": 4, "day1_mean": -0.0449}
AUCTION_STATS_REST = {"n": 35, "day1_mean": 0.0426}

NEAR_FLOOR_THRESHOLD = 0.03
DAY1_CAP = 0.10  # 觀察到多檔首日報酬精確卡在+10.0%，疑似漲幅限制機制(未查證正式規則)


@dataclass
class AuctionExpectedReturn:
    bid_to_floor_gap: float        # (得標價-最低投標底價)/最低投標底價
    is_near_floor: bool            # 是否落入近底價因子分組(<3%)
    expected_day1_return: float    # 依分組給出的首日期望報酬
    expected_day5_return: float    # 全樣本首日/五日期望報酬(近底價分組僅有首日數據)
    day1_positive_ratio: float
    hit_day1_cap: bool             # 是否可能撞到+10%疑似漲停機制(僅供提示)
    sample_size: int               # 依據的樣本數(分組樣本數很小，僅供參考方向)
    caveats: list


def auction_expected_return(
    bid_price: float,      # 計畫/預估得標加權均價
    floor_price: float,    # 最低投標底價
) -> AuctionExpectedReturn:
    gap = (bid_price - floor_price) / floor_price
    is_near_floor = gap < NEAR_FLOOR_THRESHOLD

    if is_near_floor:
        expected_day1 = AUCTION_STATS_NEAR_FLOOR["day1_mean"]
        sample_size = AUCTION_STATS_NEAR_FLOOR["n"]
    else:
        expected_day1 = AUCTION_STATS_REST["day1_mean"]
        sample_size = AUCTION_STATS_REST["n"]

    caveats = [
        "n=39全樣本集中在2026/01~07多頭噴出期間，可能有regime成分，非任何時期都適用",
        "近底價分組(n=4)與其餘分組(n=35)樣本數差距大，近底價那組方向一致但不到能下定論的程度",
        "報酬是「得標條件下」的，競拍是價高者得，不保證真的能得標，且得標要先付50%保證金",
        "CB賣出目前免徵證交稅(2026-12-31前)，但一般賣出手續費+得標手續費0.5%+投標處理費約400元/標單仍要扣",
    ]
    if abs(gap - DAY1_CAP) < 0.005:
        caveats.append("得標價與底價差距接近過去觀察到的+10%卡點區間，實際報酬可能被限制機制低估")

    return AuctionExpectedReturn(
        bid_to_floor_gap=gap,
        is_near_floor=is_near_floor,
        expected_day1_return=expected_day1,
        expected_day5_return=AUCTION_STATS_ALL["day5_median"],
        day1_positive_ratio=AUCTION_STATS_ALL["day1_positive_ratio"],
        hit_day1_cap=False,
        sample_size=sample_size,
        caveats=caveats,
    )


# ---------------------------------------------------------------------------
# 驗證區塊：用memory已核實的案例反推，確認公式正確
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== 驗證案例：33571臺慶科一(2026-07-18記憶已核實數字) ===")
    r = conversion_arbitrage(
        cb_price=206,
        conversion_price=100_000 / 881,  # 反推轉換價，使轉換股數=881
        stock_price=218,
        lots=1,
        tax_rate=0.0,
        broker_fee_rate=0.0,
        borrow_annual_rate=0.0,
    )
    print(f"轉換股數: {r.conversion_shares:.1f} (預期881)")
    print(f"轉換價值: {r.conversion_value:,.0f} (預期192,070)")
    print(f"溢價率: {r.premium_rate:.1%} (預期7.3%)")
    print(f"毛利差: {r.gross_profit:,.0f} (預期-13,930)")

    print("\n=== CB競拍模型示範 ===")
    a1 = auction_expected_return(bid_price=103, floor_price=100)
    print(f"得標-底價差距: {a1.bid_to_floor_gap:.1%} -> 近底價: {a1.is_near_floor}")
    print(f"首日期望報酬: {a1.expected_day1_return:.1%} (樣本數{a1.sample_size})")

    a2 = auction_expected_return(bid_price=101, floor_price=100)
    print(f"\n得標-底價差距: {a2.bid_to_floor_gap:.1%} -> 近底價: {a2.is_near_floor}")
    print(f"首日期望報酬: {a2.expected_day1_return:.1%} (樣本數{a2.sample_size})")
