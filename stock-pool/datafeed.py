#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据获取层：统一封装 UQER(日线/周线/Barra) + Tushare(30分钟线)
- 日线/周线/Barra 走 UQER
- 30分钟线走 Tushare 公有版
带本地缓存，避免重复调用扫库。
"""
from __future__ import annotations
import json, os
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
UQER_TOKEN = json.loads((Path("/Users/apple/Desktop/quant-backtest/timing_model/config/uqer_token.json")).read_text())["token"]
TS_CONF = json.loads((BASE/"config/tushare_token.json").read_text())
TS_TOKEN = TS_CONF["token"]
CACHE = BASE/"data/cache"
CACHE.mkdir(parents=True, exist_ok=True)

_uqer_inited = False
_ts_pro = None

def _init_uqer():
    global _uqer_inited
    if not _uqer_inited:
        import uqer
        uqer.Client(token=UQER_TOKEN)
        _uqer_inited = True

def _init_ts():
    global _ts_pro
    if _ts_pro is None:
        import tushare as ts
        ts.set_token(TS_TOKEN)
        _ts_pro = ts.pro_api()
    return _ts_pro

def get_daily(tickers, begin, end):
    """UQER 日线复权。tickers: list[str]。返回 dict[ticker]=DataFrame(含open/high/low/close/vol/turnover)。"""
    _init_uqer()
    from uqer import DataAPI
    df = DataAPI.MktEqudAdjGet(
        ticker=",".join(tickers), beginDate=begin, endDate=end,
        field="ticker,tradeDate,openPrice,closePrice,highestPrice,lowestPrice,turnoverVol,turnoverRate,preClosePrice",
        pandas="1")
    df["tradeDate"] = df["tradeDate"].str.replace("-","")
    out = {}
    for tk, g in df.groupby("ticker"):
        g = g.sort_values("tradeDate").rename(columns={
            "openPrice":"open","closePrice":"close","highestPrice":"high",
            "lowestPrice":"low","turnoverVol":"vol","turnoverRate":"turn","preClosePrice":"preclose"})
        out[tk] = g.reset_index(drop=True)
    return out

def get_weekly(tickers, begin, end):
    """UQER 周线。返回 dict[ticker]=DataFrame。"""
    _init_uqer()
    from uqer import DataAPI
    df = DataAPI.MktEquwGet(
        ticker=",".join(tickers), beginDate=begin, endDate=end,
        field="ticker,endDate,openPrice,closePrice,highestPrice,lowestPrice", pandas="1")
    out = {}
    for tk, g in df.groupby("ticker"):
        g = g.sort_values("endDate").rename(columns={
            "openPrice":"open","closePrice":"close","highestPrice":"high","lowestPrice":"low"})
        out[tk] = g.reset_index(drop=True)
    return out

def _ts_code(ticker):
    """6位代码 -> tushare 格式 (688146 -> 688146.SH)。"""
    if ticker.startswith(("6","9")): return f"{ticker}.SH"
    if ticker.startswith(("0","2","3")): return f"{ticker}.SZ"
    if ticker.startswith(("4","8")): return f"{ticker}.BJ"
    return f"{ticker}.SH"

def get_30min(ticker, begin_dt, end_dt):
    """Tushare 30分钟线。begin_dt/end_dt 格式 'YYYY-MM-DD HH:MM:SS'。
    返回 DataFrame(含open/high/low/close/vol)，按时间升序。带缓存。"""
    cache_f = CACHE/f"min30_{ticker}_{begin_dt[:10]}_{end_dt[:10]}.csv"
    if cache_f.exists():
        return pd.read_csv(cache_f)
    pro = _init_ts()
    try:
        m = pro.stk_mins(ts_code=_ts_code(ticker), freq="30min",
                         start_date=begin_dt, end_date=end_dt)
        if m is None or len(m) == 0:
            return None
        m = m.sort_values("trade_time").rename(columns={"vol":"vol"}).reset_index(drop=True)
        m = m[["trade_time","open","high","low","close","vol"]]
        m.to_csv(cache_f, index=False)
        return m
    except Exception as e:
        print(f"[get_30min] {ticker} FAIL: {str(e)[:100]}")
        return None

def get_barra_factor_returns(begin, end):
    """UQER Barra 因子日收益（宽表）。"""
    _init_uqer()
    from uqer import DataAPI
    return DataAPI.RMFactorRetDayGet(beginDate=begin, endDate=end,
        field="tradeDate,SIZE,MOMENTUM,BETA,RESVOL", pandas="1")


if __name__ == "__main__":
    # 自测
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "688146"
    print("=== 日线 ===")
    d = get_daily([tk], "20251201", "20260605")
    print(f"{tk} 日线 {len(d[tk])} 行, 末价 {d[tk].iloc[-1]['close']}")
    print("=== 周线 ===")
    w = get_weekly([tk], "20250901", "20260605")
    print(f"{tk} 周线 {len(w[tk])} 行")
    print("=== 30分钟 ===")
    m = get_30min(tk, "2026-05-20 09:00:00", "2026-06-05 15:30:00")
    print(f"{tk} 30min {len(m) if m is not None else 0} 行")
    if m is not None: print(m.tail(3).to_string())
