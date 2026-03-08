#!/usr/bin/env python3
"""
红灯预警 - 数据拉取（CSV增量模式）
5维度: 流动性 / 估值 / 情绪 / 外部冲击 / 微观恶化
大部分复用已有cache，只新拉: 估值(index_dailybasic) + 涨跌停(stk_limit) + 成交额(daily)
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# 复用路径
BASE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
LIQUIDITY_CACHE = os.path.join(BASE, 'macro', 'liquidity', 'cache')
RATES_CACHE = os.path.join(BASE, 'macro', 'rates', 'cache')
CROWDING_CACHE = os.path.join(BASE, 'micro_flow', 'crowding', 'cache')
OPTION_JSON = os.path.join(BASE, 'micro_flow', 'option_sentiment', 'option_sentiment.json')


def ts_api(api_name, fields='', **kwargs):
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30)
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg','')[:60]}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_csv_last_date(csv_path, date_col='trade_date'):
    """获取CSV最后日期"""
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path)
        if df.empty or date_col not in df.columns:
            return None
        return df[date_col].max()
    except:
        return None


def get_start_date(csv_path, default_days=400):
    """获取起始日期：CSV最后日期+1天 或 默认回溯"""
    last = get_csv_last_date(csv_path)
    if last:
        next_day = pd.to_datetime(last) + pd.Timedelta(days=1)
        return next_day.strftime('%Y%m%d')
    return (dt.date.today() - dt.timedelta(days=default_days)).strftime('%Y%m%d')


def main():
    print("=" * 50)
    print("红灯预警 - 数据拉取（增量模式）")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')

    # 1. 估值数据 (index_dailybasic): 上证/沪深300/创业板 增量
    print("\n[1/3] 拉取估值数据（增量）...")
    for code, name in [('000001.SH', '上证'), ('000300.SH', '沪深300'), ('399006.SZ', '创业板')]:
        csv_path = os.path.join(CACHE_DIR, f'valuation_{code.split(".")[0]}.csv')
        start = get_start_date(csv_path)
        
        df = ts_api('index_dailybasic', ts_code=code,
                     start_date=start, end_date=end,
                     fields='ts_code,trade_date,pe,pe_ttm,pb,turnover_rate')
        
        if not df.empty:
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
            # 合并到CSV
            if os.path.exists(csv_path):
                old = pd.read_csv(csv_path)
                old['trade_date'] = old['trade_date'].astype(str)
                df = pd.concat([old, df]).drop_duplicates('trade_date').sort_values('trade_date')
            df.to_csv(csv_path, index=False)
            print(f"  {name}: {len(df)}条")
        else:
            print(f"  {name}: 无新数据")
        time.sleep(0.5)

    # 2. 涨跌停统计 (最近30个交易日，保持原逻辑)
    print("\n[2/3] 拉取涨跌停统计（最近30天）...")
    start_60 = (dt.date.today() - dt.timedelta(days=120)).strftime('%Y%m%d')
    trade_cal = ts_api('trade_cal', fields='cal_date,is_open',
                        exchange='SSE', start_date=start_60, end_date=end)
    trade_dates = []
    if not trade_cal.empty:
        trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].sort_values().tolist()[-30:]

    limit_data = []
    for td in trade_dates:
        df = ts_api('limit_list_d', trade_date=td,
                     fields='ts_code,trade_date,name,limit')
        if not df.empty:
            up_limit = len(df[df['limit'] == 'U'])
            down_limit = len(df[df['limit'] == 'D'])
            limit_data.append({'trade_date': td, 'up_limit': up_limit, 'down_limit': down_limit})
        time.sleep(0.5)
    
    if limit_data:
        limit_df = pd.DataFrame(limit_data)
        limit_df.to_csv(os.path.join(CACHE_DIR, 'limit_stats.csv'), index=False)
        print(f"  涨跌停: {len(limit_df)}天")

    # 3. 成交额 (最近60天，保持原逻辑)
    print("\n[3/3] 拉取全A成交额（最近60天）...")
    start_60 = (dt.date.today() - dt.timedelta(days=120)).strftime('%Y%m%d')
    amount_df = ts_api('daily', fields='trade_date,amount',
                        start_date=start_60, end_date=end)
    if not amount_df.empty:
        amount_df['trade_date'] = pd.to_datetime(amount_df['trade_date']).dt.strftime('%Y%m%d')
        amount_df['amount'] = pd.to_numeric(amount_df['amount'], errors='coerce')
        daily_amount = amount_df.groupby('trade_date')['amount'].sum().reset_index()
        daily_amount.to_csv(os.path.join(CACHE_DIR, 'daily_amount.csv'), index=False)
        print(f"  成交额: {len(daily_amount)}天")

    print("\n✅ 数据拉取完成")


if __name__ == '__main__':
    main()
