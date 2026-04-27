#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - 增量数据拉取
存储：原始价格（nav_data）+ 成交量（vol_data），渲染时归一化

【重要说明】
纯价格指数（^NDX ^DJI ^N225 ^KS11）没有成交量数据，
用QQQ（纳斯达克100ETF）作为纳指成交量的代理。
其他有量的资产：BTC-USD、3033.HK、588000.SS、GC=F、CL=F
"""

import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta


# 需要成交量的资产（同 calc_meme.py 中的 VOL_WEIGHTS，这里同步定义）
# 若这些资产有价格历史但缺成交量，fetch_data 会自动补拉
VOL_WEIGHTS = {
    'BTC':              0.35,
    '纳斯达克ETF(QQQ)': 0.25,
    '恒生科技ETF':       0.20,
    '科创50ETF':        0.20,
}


def load_existing_data():
    """加载现有数据（原始价格 + 成交量）"""
    if os.path.exists('antifragile_nav.json'):
        with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('nav_data', {}), data.get('vol_data', {})
    return {}, {}


def get_asset_start_date(existing_asset_data):
    """
    按单个资产确定增量起始日期：
    - 有历史数据 → 从最新日期的次日开始
    - 无历史数据 → 拉最近1年
    """
    if existing_asset_data:
        latest_date = max(pd.to_datetime(list(existing_asset_data.keys())))
        return latest_date + timedelta(days=1)
    return datetime.now() - timedelta(days=365)


def fetch_yfinance_ticker(ticker, start_date, end_date):
    """
    拉取单个ticker的历史 Close + Volume 数据
    返回：(close_series, vol_series)，失败时返回 (None, None)
    注意：纯价格指数的Volume通常为0，会被过滤掉
    """
    try:
        data = yf.download(
            ticker, start=start_date, end=end_date,
            progress=False, auto_adjust=True
        )
        if data.empty or 'Close' not in data.columns:
            return None, None

        # ── 价格 ──────────────────────────────
        close_data = data['Close']
        # 兼容新版yfinance返回MultiIndex DataFrame的情况
        if isinstance(close_data, pd.DataFrame):
            close_data = close_data.iloc[:, 0]
        if not isinstance(close_data, pd.Series):
            close_data = pd.Series([float(close_data)], index=[data.index[-1]])

        # ── 成交量 ────────────────────────────
        vol_data = None
        if 'Volume' in data.columns:
            vol_series = data['Volume']
            if isinstance(vol_series, pd.DataFrame):
                vol_series = vol_series.iloc[:, 0]
            if not isinstance(vol_series, pd.Series):
                vol_series = pd.Series([float(vol_series)], index=[data.index[-1]])
            # 过滤0成交量（纯价格指数如^NDX会返回0）
            vol_series = vol_series[vol_series > 0]
            if not vol_series.empty:
                vol_data = vol_series

        return close_data, vol_data

    except Exception as e:
        print(f"  yfinance {ticker} 失败: {e}")
        return None, None


def main():
    # ────────────────────────────────────────────
    # 资产配置表
    # 格式：yfinance ticker → 显示名称
    # ────────────────────────────────────────────
    yf_tickers = {
        '^NDX':      '纳斯达克100',          # 价格指数，无量
        '3033.HK':   '恒生科技ETF',          # ETF，有量
        '588000.SS': '科创50ETF',            # ETF，有量
        'BTC-USD':   'BTC',                  # 币，有量（最敏感的Meme指标）
        '^N225':     '日经225',              # 价格指数，无量
        '^KS11':     '韩国KOSPI',            # 价格指数，无量
        '^DJI':      '道琼斯',              # 价格指数，无量
        'GC=F':      'COMEX黄金',            # 期货，有量
        'CL=F':      'WTI原油',             # 期货，有量（仅中位数对标）
        'USDJPY=X':  '美元兑日元',           # 汇率，无量，用于日元套息监控
        'QQQ':       '纳斯达克ETF(QQQ)',     # ETF，有量，作为纳指成交量代理
    }

    # 加载现有数据
    existing_nav, existing_vol = load_existing_data()
    end_date = datetime.now()

    # 深拷贝（避免直接修改原始数据）
    merged_nav = {k: dict(v) for k, v in existing_nav.items()}
    merged_vol = {k: dict(v) for k, v in existing_vol.items()}

    print(f"📅 增量拉取至: {end_date.strftime('%Y-%m-%d')}")

    # 需要补拉成交量的资产（已有价格历史但缺成交量数据）
    VOL_NEEDED = set(VOL_WEIGHTS.keys())  # 来自 calc_meme.py 的权重表

    for ticker, name in yf_tickers.items():
        # 价格数据的起始日期
        asset_nav = existing_nav.get(name, {})
        start_date = get_asset_start_date(asset_nav)

        # 若该资产需要量但 vol_data 中没有历史，从价格起点开始补拉
        asset_vol = existing_vol.get(name, {})
        if name in VOL_NEEDED and not asset_vol and asset_nav:
            vol_start = min(pd.to_datetime(list(asset_nav.keys())))
            if vol_start < start_date:
                print(f"  {name}: 成交量缺失，从 {vol_start.strftime('%Y-%m-%d')} 补拉...")
                start_date = vol_start  # 扩展拉取范围到价格起点，同时补量

        print(f"  {name} ({ticker}): 从 {start_date.strftime('%Y-%m-%d')} 开始...")

        close_series, vol_series = fetch_yfinance_ticker(
            ticker,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )

        if close_series is None or close_series.empty:
            print(f"  {name}: 无新数据")
            continue

        # 存价格
        new_nav = {
            (k.strftime('%Y-%m-%d') if hasattr(k, 'strftime') else str(k)): float(v)
            for k, v in close_series.items()
        }
        if name in merged_nav:
            merged_nav[name].update(new_nav)
        else:
            merged_nav[name] = new_nav
        print(f"  {name}: +{len(new_nav)} 条价格（共 {len(merged_nav[name])} 天）")

        # 存成交量（只有真实有量的资产才存）
        if vol_series is not None and not vol_series.empty:
            new_vol = {
                (k.strftime('%Y-%m-%d') if hasattr(k, 'strftime') else str(k)): float(v)
                for k, v in vol_series.items()
            }
            merged_vol.setdefault(name, {}).update(new_vol)
            print(f"  {name}: +{len(new_vol)} 条成交量（共 {len(merged_vol[name])} 天）")

    # ── 保存 ──────────────────────────────────
    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'nav_data':    merged_nav,   # 原始价格（归一化在render_html.py做）
        'vol_data':    merged_vol,   # 原始成交量（calc_meme.py使用）
    }

    with open('antifragile_nav.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 保存完成")
    print(f"   价格数据：{len(merged_nav)} 个资产")
    print(f"   成交量数据：{len(merged_vol)} 个资产 → {list(merged_vol.keys())}")


if __name__ == '__main__':
    main()
