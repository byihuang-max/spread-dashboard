#!/usr/bin/env python3
"""
红灯预警 - 数据拉取
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
BASE = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # gamt-dashboard
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


def main():
    print("=" * 50)
    print("红灯预警 - 数据拉取")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')
    start = (dt.date.today() - dt.timedelta(days=400)).strftime('%Y%m%d')  # ~1年
    start_60 = (dt.date.today() - dt.timedelta(days=120)).strftime('%Y%m%d')

    # 1. 估值数据 (index_dailybasic): 上证/沪深300/创业板 ~1年
    print("\n[1/3] 拉取估值数据...")
    for code, name in [('000001.SH', '上证'), ('000300.SH', '沪深300'), ('399006.SZ', '创业板')]:
        df = ts_api('index_dailybasic', ts_code=code,
                     start_date=start, end_date=end,
                     fields='ts_code,trade_date,pe,pe_ttm,pb,turnover_rate')
        if not df.empty:
            df.to_csv(os.path.join(CACHE_DIR, f'valuation_{code.split(".")[0]}.csv'), index=False)
            print(f"  {name}: {len(df)}条")
        time.sleep(0.5)

    # 2. 涨跌停统计 (最近60个交易日)
    print("\n[2/3] 拉取涨跌停统计...")
    # 先拿交易日
    trade_cal = ts_api('trade_cal', fields='cal_date,is_open',
                        exchange='SSE', start_date=start_60, end_date=end)
    trade_dates = []
    if not trade_cal.empty:
        trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].sort_values().tolist()[-60:]

    limit_data = []
    for td in trade_dates[-30:]:  # 最近30天够了
        df = ts_api('limit_list_d', trade_date=td,
                     fields='ts_code,trade_date,name,limit')
        if not df.empty:
            up_limit = len(df[df['limit'] == 'U'])
            down_limit = len(df[df['limit'] == 'D'])
            limit_data.append({'trade_date': td, 'up_limit': up_limit, 'down_limit': down_limit})
            print(f"  {td}: 涨停{up_limit} 跌停{down_limit}")
        time.sleep(0.3)

    if limit_data:
        pd.DataFrame(limit_data).to_csv(os.path.join(CACHE_DIR, 'limit_stats.csv'), index=False)

    # 3. 全A成交额 (用上证指数amount做代理)
    print("\n[3/3] 拉取成交额...")
    df = ts_api('index_daily', ts_code='000001.SH',
                 start_date=start_60, end_date=end,
                 fields='ts_code,trade_date,amount,vol')
    if not df.empty:
        df.to_csv(os.path.join(CACHE_DIR, 'market_amount.csv'), index=False)
        print(f"  成交额: {len(df)}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
