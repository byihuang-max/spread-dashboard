#!/usr/bin/env python3
import datetime as dt
import os
import time

import pandas as pd
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
START_DATE = '20241227'
END_DATE = dt.date.today().strftime('%Y%m%d')
LOOKBACK_DAYS = 10

NORTHBOUND_CSV = os.path.join(CACHE_DIR, 'northbound.csv')
NORTHBOUND_DETAIL_CSV = os.path.join(CACHE_DIR, 'northbound_detail.csv')
ETF_FLOW_CSV = os.path.join(CACHE_DIR, 'etf_flow.csv')
ETF_FLOW_DETAIL_CSV = os.path.join(CACHE_DIR, 'etf_flow_detail.csv')
MARGIN_CSV = os.path.join(CACHE_DIR, 'margin.csv')
MARGIN_DETAIL_CSV = os.path.join(CACHE_DIR, 'margin_detail.csv')
SW_DAILY_CSV = os.path.join(CACHE_DIR, 'sw_daily.csv')
INDUSTRY_ETF_CSV = os.path.join(CACHE_DIR, 'industry_etf.csv')
INDUSTRY_ETF_DETAIL_CSV = os.path.join(CACHE_DIR, 'industry_etf_detail.csv')

BROAD_ETF_MAP = {
    '510300.SH': '沪深300ETF',
    '510050.SH': '上证50ETF',
    '159915.SZ': '创业板ETF',
    '588000.SH': '科创50ETF',
    '512100.SH': '中证1000ETF',
    '510500.SH': '中证500ETF',
    '159338.SZ': 'A500ETF',
}

INDUSTRY_ETF_MAP = {
    '银行': '512800.SH',
    '非银金融': '512070.SH',
    '国防军工': '512660.SH',
    '医药生物': '512010.SH',
    '食品饮料': '515180.SH',
    '有色金属': '512400.SH',
    '电子': '159870.SZ',
    '计算机': '512580.SH',
    '电力设备': '516160.SH',
    '汽车': '516110.SH',
    '机械设备': '516950.SH',
    '基础化工': '516220.SH',
    '钢铁': '515210.SH',
    '煤炭': '515220.SH',
    '房地产': '512200.SH',
    '建筑装饰': '516970.SH',
    '通信': '515880.SH',
    '传媒': '512980.SH',
    '家用电器': '159996.SZ',
    '农林牧渔': '159825.SZ',
    '公用事业': '159928.SZ',
    '社会服务': '159766.SZ',
    '美容护理': '562800.SH',
    '石油石化': '515790.SH',
    '交通运输': '512690.SH',
}


def ts_api(api_name, fields='', **kwargs):
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30, proxies={'http': None, 'https': None})
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed for {api_name}: {e}")
            time.sleep(2)
    return pd.DataFrame()


def norm_date(s):
    return pd.to_datetime(str(s).strip()).strftime('%Y%m%d')


def read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'trade_date' in df.columns:
        df['trade_date'] = df['trade_date'].astype(str).str.strip().map(norm_date)
    return df


def incremental_start(df, col='trade_date', fallback=START_DATE, lookback_days=LOOKBACK_DAYS):
    if df.empty or col not in df.columns or df[col].dropna().empty:
        return fallback
    last = pd.to_datetime(df[col].astype(str).max()) - pd.Timedelta(days=lookback_days)
    return max(fallback, last.strftime('%Y%m%d'))


def merge_dedup(old, new, keys):
    if old.empty:
        return new.copy()
    if new.empty:
        return old.copy()
    return pd.concat([old, new], ignore_index=True).drop_duplicates(keys, keep='last')


def fetch_northbound():
    print('增量拉取北向/南向资金...')
    old = read_csv(NORTHBOUND_DETAIL_CSV)
    start = incremental_start(old)
    new = ts_api(
        'moneyflow_hsgt',
        fields='trade_date,north_money,south_money,hgt,sgt,ggt_ss,ggt_sz',
        start_date=start,
        end_date=END_DATE,
    )
    if new.empty and old.empty:
        print('  无数据')
        return
    if not new.empty:
        new['trade_date'] = new['trade_date'].map(norm_date)
        for col in ['north_money', 'south_money', 'hgt', 'sgt', 'ggt_ss', 'ggt_sz']:
            new[col] = pd.to_numeric(new[col], errors='coerce')
    detail = merge_dedup(old, new, ['trade_date']).sort_values('trade_date')
    detail.to_csv(NORTHBOUND_DETAIL_CSV, index=False)
    daily = detail[['trade_date', 'north_money', 'south_money']].copy()
    daily['north_net'] = daily['north_money'] / 10000
    daily['south_net'] = daily['south_money'] / 10000
    daily[['trade_date', 'north_net', 'south_net']].to_csv(NORTHBOUND_CSV, index=False)
    print(f"  北向/南向: {len(daily)}条，最新 {daily.iloc[-1]['trade_date']}")


def fetch_etf_flow():
    print('增量拉取宽基ETF份额...')
    old = read_csv(ETF_FLOW_DETAIL_CSV)
    start = incremental_start(old)
    parts = []
    for code in BROAD_ETF_MAP:
        df = ts_api(
            'fund_share',
            fields='ts_code,trade_date,fd_share',
            ts_code=code,
            start_date=start,
            end_date=END_DATE,
        )
        if not df.empty:
            df['trade_date'] = df['trade_date'].map(norm_date)
            df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
            parts.append(df)
        time.sleep(0.25)
    if not parts and old.empty:
        print('  无数据')
        return
    new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=['ts_code', 'trade_date', 'fd_share'])
    detail = merge_dedup(old, new, ['ts_code', 'trade_date']).sort_values(['ts_code', 'trade_date'])
    detail['share_chg'] = detail.groupby('ts_code')['fd_share'].diff()
    detail.to_csv(ETF_FLOW_DETAIL_CSV, index=False)
    daily = detail.groupby('trade_date', as_index=False).agg(
        etf_share_chg=('share_chg', lambda s: float(s.sum(min_count=1)) if s.notna().any() else None)
    )
    daily['etf_share_chg'] = daily['etf_share_chg'].fillna(0.0)
    daily = daily.sort_values('trade_date')
    daily.to_csv(ETF_FLOW_CSV, index=False)
    print(f"  宽基ETF: {len(daily)}条，最新 {daily.iloc[-1]['trade_date']}")


def fetch_margin():
    print('增量拉取两融数据...')
    old = read_csv(MARGIN_DETAIL_CSV)
    start = incremental_start(old)
    new = ts_api(
        'margin',
        fields='trade_date,exchange_id,rzye,rqye,rzrqye',
        start_date=start,
        end_date=END_DATE,
    )
    if new.empty and old.empty:
        print('  无数据')
        return
    if not new.empty:
        new['trade_date'] = new['trade_date'].map(norm_date)
        for col in ['rzye', 'rqye', 'rzrqye']:
            new[col] = pd.to_numeric(new[col], errors='coerce')
    detail = merge_dedup(old, new, ['trade_date', 'exchange_id']).sort_values(['trade_date', 'exchange_id'])
    detail.to_csv(MARGIN_DETAIL_CSV, index=False)
    detail['margin_balance_raw'] = detail['rzrqye'].fillna(detail['rzye'].fillna(0) + detail['rqye'].fillna(0))
    daily = detail.groupby('trade_date', as_index=False).agg(
        margin_balance_raw=('margin_balance_raw', 'sum'),
        exchange_cnt=('exchange_id', 'nunique'),
    )
    daily = daily[daily['exchange_cnt'] >= 3].copy()
    daily['margin_balance'] = daily['margin_balance_raw'] / 1e8
    daily = daily.sort_values('trade_date')
    daily['margin_chg'] = daily['margin_balance'].diff()
    daily[['trade_date', 'margin_balance', 'margin_chg']].to_csv(MARGIN_CSV, index=False)
    print(f"  两融余额: {len(daily)}条，最新 {daily.iloc[-1]['trade_date']}")


def fetch_sw_daily():
    print('增量拉取申万一级行业...')
    old = read_csv(SW_DAILY_CSV)
    start = incremental_start(old)
    new = ts_api(
        'sw_daily',
        fields='ts_code,trade_date,close,pct_change,amount,name',
        start_date=start,
        end_date=END_DATE,
    )
    if new.empty and old.empty:
        print('  无数据')
        return
    if not new.empty:
        new['trade_date'] = new['trade_date'].map(norm_date)
        new['pct_change'] = pd.to_numeric(new['pct_change'], errors='coerce')
        new['amount'] = pd.to_numeric(new['amount'], errors='coerce')
    df = merge_dedup(old, new, ['ts_code', 'trade_date']).sort_values(['ts_code', 'trade_date'])
    df.to_csv(SW_DAILY_CSV, index=False)
    print(f"  申万行业: {len(df)}条，最新 {df['trade_date'].max()}")


def fetch_industry_etf():
    print('增量拉取行业ETF份额...')
    old = read_csv(INDUSTRY_ETF_DETAIL_CSV)
    start = incremental_start(old)
    parts = []
    for industry, code in INDUSTRY_ETF_MAP.items():
        df = ts_api(
            'fund_share',
            fields='ts_code,trade_date,fd_share',
            ts_code=code,
            start_date=start,
            end_date=END_DATE,
        )
        if not df.empty:
            df['industry'] = industry
            df['trade_date'] = df['trade_date'].map(norm_date)
            df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
            parts.append(df)
        time.sleep(0.25)
    if not parts and old.empty:
        print('  无数据')
        return
    new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=['ts_code', 'trade_date', 'fd_share', 'industry'])
    detail = merge_dedup(old, new, ['ts_code', 'trade_date']).sort_values(['ts_code', 'trade_date'])
    detail['share_chg'] = detail.groupby('ts_code')['fd_share'].diff()
    detail.to_csv(INDUSTRY_ETF_DETAIL_CSV, index=False)
    detail.to_csv(INDUSTRY_ETF_CSV, index=False)
    print(f"  行业ETF: {len(detail)}条，最新 {detail['trade_date'].max()}")


def main():
    print('=' * 50)
    print('拥挤度监控 - 增量更新')
    print('=' * 50)
    print(f'区间: {START_DATE} ~ {END_DATE}')
    fetch_northbound()
    fetch_etf_flow()
    fetch_margin()
    fetch_sw_daily()
    fetch_industry_etf()
    print('\n✅ 数据更新完成')


if __name__ == '__main__':
    main()
