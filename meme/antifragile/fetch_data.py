#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - 增量数据拉取（存原始价格，渲染时归一化）
"""

import requests
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta

def load_existing_data():
    """加载现有数据（原始价格）"""
    if os.path.exists('antifragile_nav.json'):
        with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('nav_data', {})
    return {}

def get_asset_start_date(existing_asset_data):
    """按单个资产确定起始日期（有历史则增量，无则拉1年）"""
    if existing_asset_data:
        latest_date = max(pd.to_datetime(list(existing_asset_data.keys())))
        return latest_date + timedelta(days=1)
    return datetime.now() - timedelta(days=365)

def fetch_yfinance_ticker(ticker, start_date, end_date):
    """拉取单个ticker的历史Close数据"""
    try:
        data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if data.empty or 'Close' not in data.columns:
            return None
        close_data = data['Close']
        # 兼容多列DataFrame（新版yfinance）
        if isinstance(close_data, pd.DataFrame):
            close_data = close_data.iloc[:, 0]
        # 单行时squeeze会变标量，确保是Series
        if not isinstance(close_data, pd.Series):
            close_data = pd.Series([float(close_data)], index=[data.index[-1]])
        return close_data
    except Exception as e:
        print(f"  yfinance {ticker} 失败: {e}")
        return None

def main():
    """主函数"""
    # 资产配置（8个核心资产 + WTI原油仅用于中位数对标）
    yf_tickers = {
        '^NDX':      '纳斯达克100',
        '3033.HK':   '恒生科技ETF',
        '588000.SS': '科创50ETF',
        'BTC-USD':   'BTC',
        '^N225':     '日经225',
        '^KS11':     '韩国KOSPI',
        '^DJI':      '道琼斯',
        'GC=F':      'COMEX黄金',
        'CL=F':      'WTI原油',   # 仅中位数对标用，不进相关性矩阵
    }

    # 加载现有原始价格数据
    existing_data = load_existing_data()
    end_date = datetime.now()
    merged = {k: dict(v) for k, v in existing_data.items()}  # 深拷贝

    print(f"📅 增量拉取至: {end_date.strftime('%Y-%m-%d')}")

    for ticker, name in yf_tickers.items():
        asset_data = existing_data.get(name, {})
        start_date = get_asset_start_date(asset_data)
        print(f"  {name} ({ticker}): 从 {start_date.strftime('%Y-%m-%d')} 开始拉取...")

        series = fetch_yfinance_ticker(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if series is None or series.empty:
            print(f"  {name}: 无新数据")
            continue

        new_dict = {
            (k.strftime('%Y-%m-%d') if hasattr(k, 'strftime') else str(k)): float(v)
            for k, v in series.items()
        }
        if name in merged:
            merged[name].update(new_dict)
        else:
            merged[name] = new_dict
        print(f"  {name}: +{len(new_dict)} 条，共 {len(merged[name])} 天")

    # 保存原始价格JSON（归一化在渲染时做）
    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'nav_data': merged
    }

    with open('antifragile_nav.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 保存CSV（原始价格）
    df = pd.DataFrame(merged)
    df.index.name = 'date'
    df.to_csv('antifragile_nav.csv', encoding='utf-8-sig')

    print(f"\n✅ 数据已保存（原始价格，共 {len(merged)} 个资产）")

if __name__ == '__main__':
    main()
