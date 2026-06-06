#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缠论结构识别引擎 v2 — 多级别框架（中线票）
============================================================
级别定义（中线操作，持仓2-4周）:
  大级别 = 周线   -> 产业趋势方向（这波上行还在不在）
  中级别 = 日线   -> 中枢识别 + 三类买卖点（实战主战场）
  小级别 = 日线近段 -> 背驰精确确认（分钟线无权限，用日线近15根替代）

三类买卖点全部定义在【中级别(日线)】:
  一买: 下跌趋势末段，价创新低但MACD背驰（趋势衰竭反转，左侧抄底）
  二买: 一买后反弹回踩不破前低（右侧确认，最稳）
  三买: 中枢上移突破后，回踩不跌回中枢上沿zg（趋势中继，本票池最常见）
  卖点对称。

K线根数固定（不靠截断模拟级别）:
  周线看最近 ~26根(半年)  日线看最近 ~60根  小级别看最近 ~15根
============================================================
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# 各级别固定看多少根K线（缠论结构只需够识别"三段重叠成中枢"）
WEEK_BARS = 26    # 周线半年
DAY_BARS  = 60    # 日线约3个月
SMALL_BARS = 15   # 小级别（日线近段，无分钟线时退化用）
SMALL_30M_BARS = 48  # 30分钟小级别：约6个交易日（8根/日×6）


def merge_kline(highs, lows):
    """K线包含关系处理（标准合并：向上取高高，向下取低低）。"""
    H, L, idx = [], [], []
    direction = 1
    for i in range(len(highs)):
        h, l = highs[i], lows[i]
        if not H:
            H.append(h); L.append(l); idx.append(i); continue
        ph, pl = H[-1], L[-1]
        if (h <= ph and l >= pl) or (h >= ph and l <= pl):  # 有包含
            if direction == 1:
                H[-1] = max(h, ph); L[-1] = max(l, pl)
            else:
                H[-1] = min(h, ph); L[-1] = min(l, pl)
            idx[-1] = i
        else:
            direction = 1 if h > ph else -1
            H.append(h); L.append(l); idx.append(i)
    return np.array(H), np.array(L), idx


def find_fractals(H, L):
    """识别顶/底分型。返回 [(pos, 'top'/'bot', price)]。"""
    fr = []
    for i in range(1, len(H) - 1):
        if H[i] > H[i-1] and H[i] > H[i+1]:
            fr.append((i, "top", H[i]))
        elif L[i] < L[i-1] and L[i] < L[i+1]:
            fr.append((i, "bot", L[i]))
    return fr


def build_bi(fractals, min_gap=4):
    """构建笔: 相邻异型分型，间隔>=min_gap根合并K线。"""
    if not fractals:
        return []
    bi = [fractals[0]]
    for f in fractals[1:]:
        last = bi[-1]
        if f[1] == last[1]:  # 同型，保留更极端的
            if (f[1] == "top" and f[2] > last[2]) or (f[1] == "bot" and f[2] < last[2]):
                bi[-1] = f
        else:
            if f[0] - last[0] >= min_gap:
                bi.append(f)
    return bi


def find_centers(bi):
    """中枢: 连续3笔(4端点)的重叠区间 [zd下沿, zg上沿]。
    返回 [(start_pos, end_pos, zd, zg)]，按时间顺序。"""
    centers = []
    if len(bi) < 4:
        return centers
    i = 0
    while i + 3 < len(bi):
        seg = bi[i:i+4]
        highs = [max(seg[j][2], seg[j+1][2]) for j in range(3)]
        lows  = [min(seg[j][2], seg[j+1][2]) for j in range(3)]
        zg = min(highs); zd = max(lows)
        if zg > zd:
            centers.append((seg[0][0], seg[-1][0], round(zd, 3), round(zg, 3)))
            i += 3
        else:
            i += 1
    return centers


def macd(close, fast=12, slow=26, sig=9):
    c = pd.Series(close, dtype="float64")
    dif = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=sig, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif.values, dea.values, hist.values


def trend_direction(bi, centers, close=None):
    """趋势方向: 优先看中枢依次抬高/降低；否则看笔的整体斜率。
    关键修正: 纳入"最后一个分型之后的未完成笔"——单边急涨/急跌时
    形不成新分型，但当前价已远离最后分型，必须据此修正方向。"""
    base = "震荡"
    if len(centers) >= 2:
        if centers[-1][2] > centers[-2][3]:
            base = "上涨趋势"
        elif centers[-1][3] < centers[-2][2]:
            base = "下跌趋势"
        else:
            base = "中枢震荡"
    elif len(bi) >= 2:
        base = "上行" if bi[-1][2] > bi[0][2] else "下行"

    # 未完成笔修正: 当前价 vs 最后分型，偏离 >8% 时以现价方向为准
    if close is not None and len(bi) >= 1 and len(close) > 0:
        last_px = float(close[-1])
        last_fr = bi[-1][2]
        if last_fr > 0:
            dev = (last_px - last_fr) / last_fr
            if dev > 0.08 and base in ("下行", "下跌趋势", "震荡", "中枢震荡"):
                base = "上行(未完成笔)"
            elif dev < -0.08 and base in ("上行", "上涨趋势", "震荡", "中枢震荡"):
                base = "下行(未完成笔)"
    return base


def detect_divergence(close, bi):
    """背驰: 对比最后两段同方向笔的 MACD 柱面积。
    返回 {'type':'top'/'bot'/None, 'ratio':后/前力度}。ratio<0.9 视为背驰。"""
    if len(bi) < 4:
        return {"type": None, "ratio": None}
    _, _, hist = macd(close)
    segs = []
    for k in range(len(bi) - 1, 0, -1):
        a, b = bi[k-1], bi[k]
        segs.append((a[0], b[0], b[2] > a[2], b[2]))
    same = [s for s in segs if s[2] == segs[0][2]]
    if len(same) < 2:
        return {"type": None, "ratio": None}
    (s1a, s1b, up1, p1) = same[0]
    (s2a, s2b, up2, p2) = same[1]
    def area(a, b):
        seg = hist[min(a,b):max(a,b)+1]
        return seg[seg > 0].sum() if up1 else abs(seg[seg < 0].sum())
    f1, f2 = area(s1a, s1b), area(s2a, s2b)
    if f2 == 0:
        return {"type": None, "ratio": None}
    ratio = f1 / f2
    if up1 and p1 > p2 and ratio < 0.9:
        return {"type": "top", "ratio": round(ratio, 2)}
    if (not up1) and p1 < p2 and ratio < 0.9:
        return {"type": "bot", "ratio": round(ratio, 2)}
    return {"type": None, "ratio": round(ratio, 2)}


def classify_buy_sell(close, bi, centers, div):
    """三类买卖点判定（中级别/日线）。返回 signal 字符串或 None。
    依据缠论标准定义，重点识别本票池最常见的【三买】。"""
    if not bi:
        return None
    last_price = close[-1]

    # ---- 三买/三卖: 中枢突破后回踩不破中枢边沿 ----
    if centers:
        zd, zg = centers[-1][2], centers[-1][3]
        # 最后一笔方向
        last_up = bi[-1][2] > bi[-2][2] if len(bi) >= 2 else True
        recent_high = max(p[2] for p in bi[-3:]) if len(bi) >= 3 else last_price
        recent_low  = min(p[2] for p in bi[-3:]) if len(bi) >= 3 else last_price
        # 三买: 价格曾突破中枢上沿(recent_high>zg)，当前回踩仍站在zg上方
        if recent_high > zg and last_price >= zg:
            return "三类买点(中枢上突回踩不破)"
        # 三卖: 价格曾跌破中枢下沿，当前反抽仍在zd下方
        if recent_low < zd and last_price <= zd:
            return "三类卖点(中枢下破反抽不立)"

    # ---- 一买/二买: 依赖背驰 ----
    if div["type"] == "bot":
        return "一类买点(底背驰)"
    if div["type"] == "top":
        return "一类卖点(顶背驰)"

    # ---- 二买: 底背驰后反弹回踩不破前低（需结构序列，简化判定）----
    # 最近三笔: 跌-涨-跌，且第二个跌的低点 > 第一个跌的低点
    if len(bi) >= 4:
        p = [x[2] for x in bi[-4:]]
        t = [x[1] for x in bi[-4:]]
        if t[-1] == "bot" and t[-3] == "bot" and p[-1] > p[-3] and last_price > p[-1]:
            return "二类买点(回踩不破前低)"
        if t[-1] == "top" and t[-3] == "top" and p[-1] < p[-3] and last_price < p[-1]:
            return "二类卖点(反弹不过前高)"

    return None


def analyze(df, min_gap=4, label=""):
    """单级别分析。df需含 high/low/close 列（已按时间升序）。"""
    highs = df["high"].astype(float).values
    lows  = df["low"].astype(float).values
    close = df["close"].astype(float).values
    if len(close) < 8:
        return {"ok": False, "reason": "数据不足", "label": label}

    H, L, idx = merge_kline(highs, lows)
    fr = find_fractals(H, L)
    bi = build_bi(fr, min_gap=min_gap)
    centers = find_centers(bi)
    div = detect_divergence(close, bi)
    trend = trend_direction(bi, centers, close)
    signal = classify_buy_sell(close, bi, centers, div)

    last_price = float(close[-1])
    pos_vs_center = None
    if centers:
        zd, zg = centers[-1][2], centers[-1][3]
        if last_price > zg:   pos_vs_center = "中枢上方(强)"
        elif last_price < zd: pos_vs_center = "中枢下方(弱)"
        else:                 pos_vs_center = "中枢内(震荡)"

    return {
        "ok": True, "label": label,
        "n_bi": len(bi), "n_center": len(centers),
        "trend": trend,
        "centers": centers[-2:],
        "divergence": div,
        "pos_vs_center": pos_vs_center,
        "signal": signal,
        "last_price": round(last_price, 3),
    }


def analyze_multi(daily_df, weekly_df, min30_df=None):
    """多级别联立分析（中线框架）。
    daily_df / weekly_df / min30_df 需含 high/low/close，按时间升序。
    返回大(周线)/中(日线)/小(30分钟)三级别 + 综合判断。
    min30_df 为 None 时小级别退化用日线近段。"""
    out = {"ok": True}

    # 大级别: 周线 -> 趋势方向
    if weekly_df is not None and len(weekly_df) >= 8:
        big = analyze(weekly_df.tail(WEEK_BARS), min_gap=3, label="周线")
    else:
        big = {"ok": False, "trend": "未知", "label": "周线"}
    out["big"] = big

    # 中级别: 日线 -> 中枢 + 买卖点
    mid = analyze(daily_df.tail(DAY_BARS), min_gap=4, label="日线")
    out["mid"] = mid

    # 小级别: 30分钟线(真) -> 背驰 + 买卖点精确化；无则退化日线近段
    if min30_df is not None and len(min30_df) >= 16:
        small = analyze(min30_df.tail(SMALL_30M_BARS), min_gap=4, label="30分钟")
        out["small_source"] = "30min"
    else:
        small = analyze(daily_df.tail(SMALL_BARS), min_gap=2, label="日线近段")
        out["small_source"] = "daily_tail"
    out["small"] = small

    # 综合
    out["big_trend"]    = big.get("trend", "未知")
    out["mid_signal"]   = mid.get("signal")
    out["mid_pos"]      = mid.get("pos_vs_center")
    out["mid_div"]      = mid.get("divergence", {}).get("type")
    out["small_signal"] = small.get("signal")
    out["small_div"]    = small.get("divergence", {}).get("type")
    return out


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    import uqer
    from uqer import DataAPI
    tok = json.loads(Path("/Users/apple/Desktop/quant-backtest/timing_model/config/uqer_token.json").read_text())["token"]
    uqer.Client(token=tok)
    tk = sys.argv[1] if len(sys.argv) > 1 else "688146"

    d = DataAPI.MktEqudAdjGet(ticker=tk, beginDate="20251201", endDate="20260605",
        field="tradeDate,openPrice,highestPrice,lowestPrice,closePrice", pandas="1")
    d = d.rename(columns={"openPrice":"open","highestPrice":"high","lowestPrice":"low","closePrice":"close"})
    d = d.sort_values("tradeDate").reset_index(drop=True)

    w = DataAPI.MktEquwGet(ticker=tk, beginDate="20250901", endDate="20260605",
        field="endDate,openPrice,highestPrice,lowestPrice,closePrice", pandas="1")
    w = w.rename(columns={"openPrice":"open","highestPrice":"high","lowestPrice":"low","closePrice":"close"})
    w = w.sort_values("endDate").reset_index(drop=True)

    res = analyze_multi(d, w)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=float))
