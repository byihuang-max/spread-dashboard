#!/usr/bin/env python3
"""
HALO 交易计算模块 - iFind 版本
使用 iFind 数据计算相对强弱
"""
import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PRICE_CSV = DATA_DIR / "halo_prices_ifind.csv"
OUTPUT_JSON = DATA_DIR / "halo_analysis.json"
CHINA_HISTORY = DATA_DIR / "china_halo_history.csv"
US_HISTORY = DATA_DIR / "us_halo_history.csv"

# 标的 → 基准映射（iFind 代码）
TICKER_TO_BENCHMARK = {
    # 美股 → 标普500ETF
    "SO.N": "513500.SH", "NEE.N": "513500.SH", "DUK.N": "513500.SH", "ETN.N": "513500.SH",
    "LMT.N": "513500.SH", "RTX.N": "513500.SH", "GD.N": "513500.SH", "NOC.N": "513500.SH",
    "XOM.N": "513500.SH", "JPM.N": "513500.SH", "GS.N": "513500.SH", 
    "MS.N": "513500.SH", "BAC.N": "513500.SH",
    
    # A股 → 沪深300
    "600900.SH": "000300.SH", "601985.SH": "000300.SH",
    "600150.SH": "000300.SH", "600760.SH": "000300.SH",
    "601857.SH": "000300.SH", "600036.SH": "000300.SH",
}

def load_prices():
    """加载价格数据"""
    df = pd.read_csv(PRICE_CSV)
    df['date'] = pd.to_datetime(df['date'])
    return df

def calc_relative_strength(df, ticker, benchmark):
    """计算相对强弱"""
    ticker_df = df[df['code'] == ticker].set_index('date')['close']
    bench_df = df[df['code'] == benchmark].set_index('date')['close']
    
    # 对齐日期
    aligned = pd.DataFrame({'ticker': ticker_df, 'bench': bench_df}).dropna()
    
    if aligned.empty:
        return pd.Series()
    
    # 归一化到100
    ticker_norm = (aligned['ticker'] / aligned['ticker'].iloc[0]) * 100
    bench_norm = (aligned['bench'] / aligned['bench'].iloc[0]) * 100
    
    # 相对强度
    rs = (ticker_norm / bench_norm) * 100
    return rs

def calc_nav_series(df, tickers, start_value=100):
    """计算净值序列"""
    all_dates = sorted(df['date'].unique())
    nav = start_value
    nav_series = []
    
    for date in all_dates:
        day_data = df[df['date'] == date]
        day_rets = []
        
        for ticker in tickers:
            ticker_data = day_data[day_data['code'] == ticker]
            if not ticker_data.empty:
                # 简化：用当日涨跌幅（实际应该用前一日收盘）
                close = ticker_data.iloc[0]['close']
                prev = df[(df['code'] == ticker) & (df['date'] < date)].tail(1)
                if not prev.empty:
                    ret = (close / prev.iloc[0]['close'] - 1)
                    day_rets.append(ret)
        
        if day_rets:
            nav *= (1 + sum(day_rets) / len(day_rets))
        
        nav_series.append({'date': date, 'nav': nav})
    
    return pd.DataFrame(nav_series)

if __name__ == '__main__':
    print("计算 HALO 相对强弱...")
    
    df = load_prices()
    
    # 分组
    us_tickers = [t for t in TICKER_TO_BENCHMARK.keys() if t.endswith('.N')]
    cn_tickers = [t for t in TICKER_TO_BENCHMARK.keys() if t.endswith('.SH')]
    
    # 计算美股组合
    print(f"美股: {len(us_tickers)} 只")
    us_nav = calc_nav_series(df, us_tickers)
    us_nav.to_csv(US_HISTORY, index=False)
    print(f"✅ {US_HISTORY}")
    
    # 计算A股组合
    print(f"A股: {len(cn_tickers)} 只")
    cn_nav = calc_nav_series(df, cn_tickers)
    cn_nav.to_csv(CHINA_HISTORY, index=False)
    print(f"✅ {CHINA_HISTORY}")
    
    print("✅ 完成")
