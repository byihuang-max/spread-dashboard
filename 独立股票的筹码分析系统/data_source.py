#!/usr/bin/env python3
"""
数据源模块 - 从 Tushare 获取个股日线行情、换手率、资金流向
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
import math

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'


def _ts_query(api_name, fields='', **params):
    body = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params,
    }
    if fields:
        body['fields'] = fields
    resp = requests.post(TUSHARE_URL, json=body, timeout=30)
    data = resp.json()
    if data.get('code') != 0:
        return None
    items = data.get('data', {})
    if not items or not items.get('items'):
        return None
    return pd.DataFrame(items['items'], columns=items['fields'])


def get_stock_name(ts_code: str) -> str:
    df = _ts_query('stock_basic', fields='ts_code,name', ts_code=ts_code)
    if df is not None and len(df) > 0:
        return df.iloc[0]['name']
    return ts_code


def get_daily(ts_code: str, days: int = 60) -> pd.DataFrame:
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days + 30)).strftime('%Y%m%d')
    
    df_daily = _ts_query(
        'daily',
        fields='ts_code,trade_date,open,high,low,close,vol,amount',
        ts_code=ts_code, start_date=start, end_date=end
    )
    if df_daily is None:
        return None
    
    df_basic = _ts_query(
        'daily_basic',
        fields='ts_code,trade_date,turnover_rate,pe_ttm,pb,total_mv',
        ts_code=ts_code, start_date=start, end_date=end
    )
    
    df_daily['trade_date'] = pd.to_datetime(df_daily['trade_date'])
    df_daily = df_daily.sort_values('trade_date')
    
    if df_basic is not None:
        df_basic['trade_date'] = pd.to_datetime(df_basic['trade_date'])
        df_daily = df_daily.merge(df_basic[['trade_date', 'turnover_rate', 'pe_ttm', 'pb', 'total_mv']], on='trade_date', how='left')
    
    for col in ['open', 'high', 'low', 'close', 'vol', 'amount']:
        df_daily[col] = pd.to_numeric(df_daily[col], errors='coerce')
    
    if 'turnover_rate' in df_daily.columns:
        df_daily['turnover_rate'] = pd.to_numeric(df_daily['turnover_rate'], errors='coerce').fillna(0)
    else:
        df_daily['turnover_rate'] = 0
    
    df_daily = df_daily.tail(days)
    return df_daily


def get_moneyflow(ts_code: str, days: int = 20) -> pd.DataFrame:
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days + 10)).strftime('%Y%m%d')
    
    df = _ts_query(
        'moneyflow',
        fields='ts_code,trade_date,buy_elg_amount,sell_elg_amount,buy_lg_amount,sell_lg_amount',
        ts_code=ts_code, start_date=start, end_date=end
    )
    if df is None:
        return None
    
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ['buy_elg_amount', 'sell_elg_amount', 'buy_lg_amount', 'sell_lg_amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['main_net'] = (df['buy_elg_amount'] + df['buy_lg_amount']) - (df['sell_elg_amount'] + df['sell_lg_amount'])
    df['large_buy'] = df['buy_elg_amount'] + df['buy_lg_amount']
    df['large_sell'] = df['sell_elg_amount'] + df['sell_lg_amount']
    df['large_turnover'] = df['large_buy'] + df['large_sell']
    df = df.sort_values('trade_date').tail(days)
    return df


def get_stock_profile(ts_code: str) -> dict:
    df = _ts_query(
        'stock_basic',
        fields='ts_code,name,industry,market,list_date,area',
        ts_code=ts_code
    )
    if df is None or len(df) == 0:
        return {}
    row = df.iloc[0]
    return {
        'industry': row.get('industry'),
        'market': row.get('market'),
        'area': row.get('area'),
        'list_date': row.get('list_date'),
    }


def get_limit_stats(ts_code: str, days: int = 60) -> dict:
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days + 20)).strftime('%Y%m%d')
    df = _ts_query(
        'limit_list_d',
        fields='trade_date,ts_code,name,close,pct_chg,amp,fc_ratio,fd_amount,first_time,last_time,open_times,strth,limit',
        ts_code=ts_code, start_date=start, end_date=end
    )
    if df is None or len(df) == 0:
        return {
            'limit_up_count': 0,
            'special_days': 0,
            'latest_limit_date': None,
            'latest_limit_type': None,
        }
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
        df = df.sort_values('trade_date')
    latest = df.iloc[-1]
    return {
        'limit_up_count': int(len(df)),
        'special_days': int(len(df)),
        'latest_limit_date': latest['trade_date'].strftime('%Y-%m-%d') if pd.notna(latest.get('trade_date')) else None,
        'latest_limit_type': latest.get('limit'),
    }


def calc_big_order_stats(df_daily: pd.DataFrame, df_money: pd.DataFrame, windows=(30, 60)) -> dict:
    if df_daily is None or len(df_daily) == 0 or df_money is None or len(df_money) == 0:
        return {'definition': '大单=超大单+大单净额（Tushare moneyflow口径）', 'by_window': {}}
    merged = df_daily[['trade_date', 'amount', 'close']].merge(
        df_money[['trade_date', 'main_net', 'large_turnover']], on='trade_date', how='left'
    ).sort_values('trade_date')
    merged['amount'] = pd.to_numeric(merged['amount'], errors='coerce').fillna(0)
    merged['main_net'] = pd.to_numeric(merged['main_net'], errors='coerce').fillna(0)
    merged['large_turnover'] = pd.to_numeric(merged['large_turnover'], errors='coerce').fillna(0)
    out = {}
    for w in windows:
        sub = merged.tail(w).copy()
        if len(sub) == 0:
            continue
        ratio = sub['large_turnover'] / sub['amount'].replace(0, pd.NA)
        ratio = pd.to_numeric(ratio, errors='coerce').fillna(0)
        z = 0.0
        if len(ratio) >= 5 and float(ratio.std()) > 1e-9:
            z = float((ratio.iloc[-1] - ratio.mean()) / ratio.std())
        threshold = float(ratio.quantile(0.8)) if len(ratio) >= 5 else float(ratio.max())
        big_days = int((ratio >= threshold).sum()) if threshold > 0 else 0
        latest_is_big = bool(len(ratio) and ratio.iloc[-1] >= threshold and threshold > 0)
        net_sum = float(sub['main_net'].sum())
        out[str(w)] = {
            'big_days': big_days,
            'avg_big_ratio': round(float(ratio.mean()) if len(ratio) else 0, 4),
            'latest_big_ratio': round(float(ratio.iloc[-1]) if len(ratio) else 0, 4),
            'latest_ratio_zscore': round(z, 2),
            'latest_is_big': latest_is_big,
            'net_sum': round(net_sum, 2),
        }
    return {
        'definition': '大单=超大单+大单买卖额；观察指标=大单成交额/当日总成交额，近30/60日按历史80%分位识别异常大单日。',
        'by_window': out,
    }


def estimate_industry_comparison(df_daily: pd.DataFrame, profile: dict) -> dict:
    if df_daily is None or len(df_daily) < 2:
        return {'industry': profile.get('industry') if profile else None, 'stock_return_20d': None, 'industry_avg_20d': None, 'excess_vs_industry': None, 'note': '行业均值待补接口'}
    close = pd.to_numeric(df_daily['close'], errors='coerce')
    stock_return_20d = None
    if len(close) >= 20 and close.iloc[-20] and not math.isnan(close.iloc[-20]):
        stock_return_20d = (float(close.iloc[-1]) / float(close.iloc[-20]) - 1) * 100
    return {
        'industry': profile.get('industry') if profile else None,
        'stock_return_20d': round(stock_return_20d, 2) if stock_return_20d is not None else None,
        'industry_avg_20d': None,
        'excess_vs_industry': None,
        'note': '行业均值待补接口，先展示公司所属行业与个股近20日涨幅。',
    }
