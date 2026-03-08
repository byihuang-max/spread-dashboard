#!/usr/bin/env python3
"""
美股风险监控 - 数据获取（增量模式）
数据源: yfinance + FRED API
时间范围: 2007-01-01 至今（覆盖3次危机）
"""
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# FRED API Key（需要从 https://fred.stlouisfed.org/docs/api/api_key.html 获取）
FRED_API_KEY = None  # 暂时为空，后续补充

# 默认回填天数（首次运行）
DEFAULT_BACKFILL_DAYS = 6570  # 约18年（2007至今）


def get_csv_last_date(csv_path):
    """获取CSV最后日期"""
    if not os.path.exists(csv_path):
        return None
    df = pd.read_csv(csv_path)
    if df.empty or 'date' not in df.columns:
        return None
    df['date'] = pd.to_datetime(df['date'])
    return df['date'].max()


def get_start_date(csv_path, default_days=DEFAULT_BACKFILL_DAYS):
    """确定起始日期（增量逻辑）"""
    last_date = get_csv_last_date(csv_path)
    if last_date is None:
        # 首次运行：回填到2007年
        return (datetime.now() - timedelta(days=default_days)).strftime('%Y-%m-%d')
    else:
        # 增量：从最后日期+1天开始
        return (last_date + timedelta(days=1)).strftime('%Y-%m-%d')


def fetch_yfinance_data(ticker, csv_name):
    """通用yfinance数据获取"""
    csv_path = os.path.join(CACHE_DIR, csv_name)
    start_date = get_start_date(csv_path)
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"获取 {ticker} 数据: {start_date} -> {end_date}")
    
    try:
        # 使用 Ticker 对象获取数据
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(start=start_date, end=end_date)
        
        if hist.empty:
            print(f"  无新数据")
            return
        
        # 整理格式
        df_new = pd.DataFrame({
            'date': hist.index.strftime('%Y-%m-%d'),
            'close': hist['Close'].values
        })
        
        # 合并旧数据
        if os.path.exists(csv_path):
            df_old = pd.read_csv(csv_path)
            df = pd.concat([df_old, df_new], ignore_index=True)
            df = df.drop_duplicates(subset=['date'], keep='last')
        else:
            df = df_new
        
        df = df.sort_values('date').reset_index(drop=True)
        df.to_csv(csv_path, index=False)
        print(f"  ✓ 保存 {len(df_new)} 条新数据")
    
    except Exception as e:
        print(f"  ✗ 失败: {e}")


def fetch_vix():
    """VIX 恐慌指数"""
    fetch_yfinance_data('^VIX', 'us_vix.csv')


def fetch_sp500():
    """标普500指数"""
    fetch_yfinance_data('^GSPC', 'us_sp500.csv')


def fetch_gold():
    """黄金价格"""
    fetch_yfinance_data('GC=F', 'us_gold.csv')


def fetch_dxy():
    """美元指数"""
    fetch_yfinance_data('DX-Y.NYB', 'us_dxy.csv')


def fetch_nasdaq():
    """纳斯达克指数"""
    fetch_yfinance_data('^IXIC', 'us_nasdaq.csv')


def fetch_bitcoin():
    """比特币"""
    fetch_yfinance_data('BTC-USD', 'us_bitcoin.csv')


def fetch_crude_oil():
    """原油价格"""
    fetch_yfinance_data('CL=F', 'us_crude_oil.csv')


def fetch_10y_treasury():
    """10年期美债收益率"""
    fetch_yfinance_data('^TNX', 'us_10y_treasury.csv')


def fetch_put_call_ratio():
    """Put/Call Ratio（用CBOE数据或从期权链计算）"""
    # 简化版：暂时跳过，后续补充
    print("Put/Call Ratio: 暂时跳过（需要CBOE数据）")
    pass


def fetch_fred_data(series_id, csv_name):
    """通用FRED数据获取"""
    if FRED_API_KEY is None:
        print(f"跳过 {series_id}: 未配置FRED_API_KEY")
        return
    
    csv_path = os.path.join(CACHE_DIR, csv_name)
    start_date = get_start_date(csv_path)
    
    print(f"获取 {series_id} 数据: {start_date} -> 今天")
    
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        
        data = fred.get_series(series_id, observation_start=start_date)
        if data.empty:
            print(f"  无新数据")
            return
        
        df_new = pd.DataFrame({
            'date': data.index.strftime('%Y-%m-%d'),
            'value': data.values
        })
        
        # 合并旧数据
        if os.path.exists(csv_path):
            df_old = pd.read_csv(csv_path)
            df = pd.concat([df_old, df_new], ignore_index=True)
            df = df.drop_duplicates(subset=['date'], keep='last')
        else:
            df = df_new
        
        df = df.sort_values('date').reset_index(drop=True)
        df.to_csv(csv_path, index=False)
        print(f"  ✓ 保存 {len(df_new)} 条新数据")
    
    except Exception as e:
        print(f"  ✗ 失败: {e}")


def fetch_treasury_spread():
    """10Y-2Y利差"""
    fetch_fred_data('T10Y2Y', 'us_10y2y_spread.csv')


def fetch_ted_spread():
    """TED利差（3M LIBOR - 3M T-Bill）"""
    fetch_fred_data('TEDRATE', 'us_ted_spread.csv')


def fetch_unemployment():
    """失业率"""
    fetch_fred_data('UNRATE', 'us_unemployment.csv')


def fetch_ism_pmi():
    """ISM制造业PMI"""
    fetch_fred_data('MANEMP', 'us_ism_pmi.csv')


def main():
    print("=" * 50)
    print("美股风险监控 - 数据获取")
    print("=" * 50)
    
    # yfinance 数据
    print("\n[yfinance 数据]")
    fetch_vix()
    fetch_sp500()
    fetch_nasdaq()
    fetch_gold()
    fetch_dxy()
    fetch_bitcoin()
    fetch_crude_oil()
    fetch_10y_treasury()
    fetch_put_call_ratio()
    
    # FRED 数据
    print("\n[FRED 数据]")
    if FRED_API_KEY:
        fetch_treasury_spread()
        fetch_ted_spread()
        fetch_unemployment()
        fetch_ism_pmi()
    else:
        print("⚠️  未配置 FRED_API_KEY，跳过FRED数据")
        print("   获取免费key: https://fred.stlouisfed.org/docs/api/api_key.html")
    
    print("\n✓ 数据获取完成")


if __name__ == '__main__':
    main()
