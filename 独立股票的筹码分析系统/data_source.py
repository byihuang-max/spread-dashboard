#!/usr/bin/env python3
"""
数据源模块 - 从 Tushare 获取个股日线行情、换手率、资金流向
"""
import requests
import pandas as pd
from datetime import datetime, timedelta

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
    df = df.sort_values('trade_date').tail(days)
    return df
