"""AI 算力链轮动监控 — 三层信号计算引擎

信号层 ①：滚动比价 Z-score（6 组比价对）
信号层 ②：量价状态分类（4 个 A 股篮子）
信号层 ③：ETF 资金流验证
综合信号：三层交叉验证
"""

import numpy as np
import pandas as pd

from config import (
    PAIR_GROUPS, BASKETS,
    ZSCORE_WINDOW, ZSCORE_EXTREME, ZSCORE_MODERATE,
    VOL_PRICE_SHORT, VOL_PRICE_LONG,
)


# ══════════════════════════════════════════════════════════
#  信号层 ① — 滚动比价 Z-score
# ══════════════════════════════════════════════════════════

def calc_basket_return(prices: pd.DataFrame) -> pd.Series:
    """等权日收益率序列。"""
    daily_ret = prices.pct_change(fill_method=None)
    return daily_ret.mean(axis=1)  # 等权


def calc_pair_zscore(ret_a: pd.Series, ret_b: pd.Series,
                     window: int = ZSCORE_WINDOW) -> pd.DataFrame:
    """计算一组比价对的累计收益差 Z-score。

    Returns DataFrame with columns:
        cum_diff, rolling_mean, rolling_std, zscore
    """
    cum_a = (1 + ret_a).cumprod()
    cum_b = (1 + ret_b).cumprod()
    cum_diff = cum_a - cum_b

    roll_mean = cum_diff.rolling(window).mean()
    roll_std = cum_diff.rolling(window).std()
    zscore = (cum_diff - roll_mean) / roll_std.replace(0, np.nan)

    return pd.DataFrame({
        "cum_diff": cum_diff,
        "rolling_mean": roll_mean,
        "rolling_std": roll_std,
        "zscore": zscore,
    })


def label_zscore(z: float) -> str:
    """Z-score → 文字标签。"""
    if pd.isna(z):
        return "无数据"
    if z > ZSCORE_EXTREME:
        return "左侧极端拥挤"
    if z > ZSCORE_MODERATE:
        return "左侧偏强"
    if z < -ZSCORE_EXTREME:
        return "右侧极端拥挤"
    if z < -ZSCORE_MODERATE:
        return "右侧偏强"
    return "中性"


def calc_all_pair_zscores(basket_prices: dict) -> dict:
    """计算全部 6 组比价 Z-score。

    Returns: {pair_label: DataFrame}
    """
    # 先算各篮子等权收益
    basket_rets = {}
    for name, prices in basket_prices.items():
        basket_rets[name] = calc_basket_return(prices)

    results = {}
    for left, right, desc in PAIR_GROUPS:
        if left not in basket_rets or right not in basket_rets:
            continue
        label = f"{left} vs {right}"
        ret_l = basket_rets[left]
        ret_r = basket_rets[right]
        # 对齐日期
        idx = ret_l.dropna().index.intersection(ret_r.dropna().index)
        df = calc_pair_zscore(ret_l.loc[idx], ret_r.loc[idx])
        df.attrs["desc"] = desc
        results[label] = df

    return results


# ══════════════════════════════════════════════════════════
#  信号层 ② — 量价状态分类
# ══════════════════════════════════════════════════════════

VP_STATES = {
    (True, True):   ("量价齐升", "🟢", "趋势确认"),
    (True, False):  ("价升量不跟", "🟡", "动能衰竭"),
    (False, True):  ("量升价不升", "🔵", "底部蓄力"),
    (False, False): ("量价齐跌", "🔴", "趋势确认↓"),
}


def classify_vol_price(prices: pd.DataFrame, amounts: pd.DataFrame,
                       short: int = VOL_PRICE_SHORT,
                       long_: int = VOL_PRICE_LONG) -> dict:
    """对单个篮子做量价状态分类。

    Returns:
        {
            "price_up": bool,
            "vol_up": bool,
            "state": str,
            "emoji": str,
            "meaning": str,
            "price_chg_5d": float,
            "vol_ratio": float,
        }
    """
    # 篮子等权价格
    basket_price = prices.mean(axis=1).dropna()
    basket_amount = amounts.mean(axis=1).dropna()

    if len(basket_price) < long_:
        return {"state": "数据不足", "emoji": "⚪", "meaning": ""}

    price_chg = basket_price.iloc[-1] / basket_price.iloc[-short] - 1
    vol_short = basket_amount.iloc[-short:].mean()
    vol_long = basket_amount.iloc[-long_:].mean()
    vol_ratio = vol_short / vol_long if vol_long > 0 else 1.0

    price_up = price_chg > 0
    vol_up = vol_ratio > 1.0

    state, emoji, meaning = VP_STATES[(price_up, vol_up)]

    return {
        "price_up": price_up,
        "vol_up": vol_up,
        "state": state,
        "emoji": emoji,
        "meaning": meaning,
        "price_chg_5d": round(price_chg * 100, 2),
        "vol_ratio": round(vol_ratio, 3),
    }


def calc_all_vol_price(basket_prices: dict, basket_amounts: dict) -> dict:
    """对全部 A 股篮子做量价分类。"""
    results = {}
    for name in BASKETS:
        if name not in basket_prices or name not in basket_amounts:
            continue
        results[name] = classify_vol_price(
            basket_prices[name], basket_amounts[name]
        )
    return results


# ══════════════════════════════════════════════════════════
#  信号层 ③ — ETF 资金流
# ══════════════════════════════════════════════════════════

def calc_etf_flow(etf_shares: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """计算 ETF 份额日度变动和短期累计。

    Returns DataFrame: columns = ETF名称, rows = trade_date
    Values = 日度份额变动（亿份）
    """
    if etf_shares.empty:
        return pd.DataFrame()

    daily_chg = etf_shares.diff()
    return daily_chg


def etf_flow_summary(etf_shares: pd.DataFrame, window: int = 5) -> dict:
    """最近 N 日 ETF 资金流摘要。"""
    chg = calc_etf_flow(etf_shares)
    if chg.empty:
        return {}

    recent = chg.iloc[-window:]
    summary = {}
    for col in recent.columns:
        total = recent[col].sum()
        direction = "净流入" if total > 0 else "净流出"
        summary[col] = {
            "recent_chg": round(total, 2),
            "direction": direction,
            "daily_avg": round(total / window, 2),
        }
    return summary


# ══════════════════════════════════════════════════════════
#  综合信号引擎
# ══════════════════════════════════════════════════════════

def composite_signal(pair_zscores: dict, vol_price: dict,
                     etf_summary: dict) -> dict:
    """三层交叉验证，输出综合信号。

    Returns:
        {
            "level": "强信号" | "中等信号" | "观望" | "均衡",
            "emoji": str,
            "detail": str,
            "layers": {layer_name: summary},
        }
    """
    signals = []

    # Layer 1: 有没有极端 Z-score
    extreme_pairs = []
    for label, df in pair_zscores.items():
        last_z = df["zscore"].dropna().iloc[-1] if not df["zscore"].dropna().empty else 0
        lbl = label_zscore(last_z)
        if "极端" in lbl:
            extreme_pairs.append((label, last_z, lbl))
    if extreme_pairs:
        signals.append("zscore_extreme")

    # Layer 2: 有没有高低切信号（一个衰竭 + 一个齐升）
    exhaustion = [k for k, v in vol_price.items() if v.get("state") == "价升量不跟"]
    momentum = [k for k, v in vol_price.items() if v.get("state") == "量价齐升"]
    if exhaustion and momentum:
        signals.append("rotation_signal")

    # Layer 3: ETF 资金流方向分化
    inflow = [k for k, v in etf_summary.items() if v.get("direction") == "净流入"]
    outflow = [k for k, v in etf_summary.items() if v.get("direction") == "净流出"]
    if inflow and outflow:
        signals.append("etf_divergence")

    # 综合判断
    n = len(signals)
    if n >= 3:
        level, emoji = "强信号", "🔴"
    elif n == 2:
        level, emoji = "中等信号", "🟡"
    elif n == 1:
        level, emoji = "关注", "🟠"
    else:
        level, emoji = "均衡", "🟢"

    detail_parts = []
    if extreme_pairs:
        for lbl, z, desc in extreme_pairs:
            detail_parts.append(f"{lbl}: Z={z:.2f} ({desc})")
    if exhaustion and momentum:
        detail_parts.append(f"轮动信号: {','.join(exhaustion)}→{','.join(momentum)}")
    if inflow and outflow:
        detail_parts.append(f"ETF分化: 流入{','.join(inflow)} / 流出{','.join(outflow)}")

    return {
        "level": level,
        "emoji": emoji,
        "detail": " | ".join(detail_parts) if detail_parts else "各层信号中性，无明显轮动",
        "layers": {
            "zscore_extreme": extreme_pairs,
            "rotation_signal": {"exhaustion": exhaustion, "momentum": momentum},
            "etf_divergence": {"inflow": inflow, "outflow": outflow},
        },
    }

