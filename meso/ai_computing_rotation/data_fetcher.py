"""AI 算力链轮动监控 — 数据拉取层

数据源：
- A 股行情 + ETF 份额：Tushare Pro（直连，不走代理）
- 美股锚（SOXX 费城半导体）：iFind EDB（直连，不走代理）
"""

import json
import sys
import time
import datetime as dt
import requests
import pandas as pd
import numpy as np
from pathlib import Path

from config import (
    TUSHARE_TOKEN, TUSHARE_URL,
    BASKETS, ETF_LIST, US_ANCHOR, LOOKBACK_DAYS,
)

# iFind MCP 调用
IFIND_DIR = Path.home() / ".openclaw/extensions/ifind-finance-data"
sys.path.insert(0, str(IFIND_DIR))

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CACHE_FILE = DATA_DIR / "daily_cache.parquet"
ETF_CACHE  = DATA_DIR / "etf_share_cache.parquet"


# ── Tushare 通用请求 ─────────────────────────────────────

def _ts_query(api_name: str, fields: str = "", **params) -> pd.DataFrame:
    """直连 Tushare Pro，返回 DataFrame。"""
    payload = {
        "api_name": api_name,
        "token": TUSHARE_TOKEN,
        "params": params,
        "fields": fields,
    }
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=payload, timeout=30)
            j = r.json()
            if j.get("code") != 0:
                raise RuntimeError(f"Tushare error: {j.get('msg')}")
            data = j["data"]
            return pd.DataFrame(data["items"], columns=data["fields"])
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise
    return pd.DataFrame()


def _trade_dates(start: str, end: str) -> list[str]:
    """获取交易日历。"""
    df = _ts_query("trade_cal", "", exchange="SSE",
                   start_date=start, end_date=end, is_open="1")
    return sorted(df["cal_date"].tolist())


# ── A 股日线 ─────────────────────────────────────────────

def fetch_stock_daily(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """拉单只股票日线（日期, 收盘价, 成交额）。"""
    df = _ts_query(
        "daily",
        "ts_code,trade_date,close,amount",
        ts_code=ts_code, start_date=start, end_date=end,
    )
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["close"] = df["close"].astype(float)
    df["amount"] = df["amount"].astype(float)
    return df


def fetch_basket_daily(basket_name: str, start: str, end: str) -> pd.DataFrame:
    """拉一个篮子所有成分股日线，返回宽表（index=trade_date, columns=ts_code）。

    返回两个 DataFrame: prices, amounts
    """
    stocks = BASKETS[basket_name]["stocks"]
    all_close = {}
    all_amount = {}
    for code in stocks:
        df = fetch_stock_daily(code, start, end)
        if df.empty:
            continue
        df = df.set_index("trade_date")
        all_close[code] = df["close"]
        all_amount[code] = df["amount"]
        time.sleep(0.12)  # Tushare 频率限制

    prices = pd.DataFrame(all_close)
    amounts = pd.DataFrame(all_amount)
    return prices, amounts


# ── ETF 份额 ─────────────────────────────────────────────

def fetch_etf_share(ts_code: str, start: str, end: str) -> pd.DataFrame:
    """拉 ETF 日度份额。"""
    df = _ts_query(
        "fund_share",
        "ts_code,trade_date,fd_share",
        ts_code=ts_code, start_date=start, end_date=end,
    )
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["fd_share"] = df["fd_share"].astype(float)
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def fetch_all_etf_shares(start: str, end: str) -> pd.DataFrame:
    """拉所有跟踪 ETF 的份额，返回宽表（index=trade_date, columns=ETF名称）。"""
    result = {}
    for code, name in ETF_LIST.items():
        df = fetch_etf_share(code, start, end)
        if df.empty:
            continue
        df = df.set_index("trade_date")
        result[name] = df["fd_share"]
        time.sleep(0.12)
    return pd.DataFrame(result)


# ── 批量拉取入口 ──────────────────────────────────────────

def fetch_all(end_date: str = None, lookback: int = LOOKBACK_DAYS) -> dict:
    """一次性拉取所有篮子 + ETF 数据。

    Returns:
        {
            "basket_prices": {篮子名: DataFrame},
            "basket_amounts": {篮子名: DataFrame},
            "etf_shares": DataFrame,
            "trade_dates": list,
        }
    """
    if end_date is None:
        end_date = dt.date.today().strftime("%Y%m%d")

    # 多拉一些天数以覆盖滚动窗口
    start_dt = dt.datetime.strptime(end_date, "%Y%m%d") - dt.timedelta(days=int(lookback * 1.8))
    start_date = start_dt.strftime("%Y%m%d")

    print(f"[data_fetcher] 拉取区间: {start_date} ~ {end_date}")

    dates = _trade_dates(start_date, end_date)

    basket_prices = {}
    basket_amounts = {}
    for name in BASKETS:
        print(f"  拉取篮子: {name} ({len(BASKETS[name]['stocks'])}只)")
        p, a = fetch_basket_daily(name, start_date, end_date)
        basket_prices[name] = p
        basket_amounts[name] = a

    print(f"  拉取 ETF 份额: {len(ETF_LIST)}只")
    etf = fetch_all_etf_shares(start_date, end_date)

    # 美股锚：SOXX via iFind EDB
    print("  拉取美股锚: SOXX (iFind EDB)")
    soxx = fetch_soxx_daily(start_date, end_date)
    if soxx is not None and not soxx.empty:
        # 构造与 A 股篮子同结构的 prices DataFrame
        basket_prices["美股锚"] = pd.DataFrame({"SOXX": soxx})
        basket_amounts["美股锚"] = pd.DataFrame({"SOXX": np.nan}, index=soxx.index)
        print(f"    SOXX: {len(soxx)}条数据")
    else:
        print("    ⚠️ SOXX 数据拉取失败，美股锚不可用")

    return {
        "basket_prices": basket_prices,
        "basket_amounts": basket_amounts,
        "etf_shares": etf,
        "trade_dates": dates,
    }


# ── 美股锚：iFind EDB 拉 SOXX ────────────────────────────

def fetch_soxx_daily(start: str, end: str) -> pd.Series | None:
    """通过 iFind EDB 拉费城半导体指数（SOX）日频数据。

    Args:
        start/end: YYYYMMDD 格式

    Returns:
        pd.Series (index=datetime, values=收盘价) or None
    """
    try:
        # 动态 import，避免 iFind 不可用时整个模块挂掉
        cwd_backup = Path.cwd()
        import os
        os.chdir(IFIND_DIR)  # call.py 读 mcp_config.json 用相对路径
        from call import call as ifind_call
        os.chdir(cwd_backup)

        start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:]}"
        end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:]}"

        result = ifind_call(
            "edb", "get_edb_data",
            {"query": f"费城半导体指数(SOX) {start_fmt}至{end_fmt}"}
        )

        if not result.get("ok"):
            print(f"    iFind EDB 请求失败: {result.get('error')}")
            return None

        # 解析返回数据
        data = result["data"]
        datas = data.get("result", {}).get("content", [])
        if not datas:
            return None

        text = datas[0].get("text", "")
        parsed = json.loads(text)
        inner = parsed.get("data", {}).get("datas", [{}])[0].get("data", {}).get("data", [])

        if not inner:
            return None

        df = pd.DataFrame(inner, columns=["date", "close"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df["close"].astype(float)

    except Exception as e:
        print(f"    iFind SOXX 拉取异常: {e}")
        return None

