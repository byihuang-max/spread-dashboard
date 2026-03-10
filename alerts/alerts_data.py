#!/usr/bin/env python3
"""
红灯预警 - 数据拉取（CSV增量模式）
5维度: 流动性 / 估值 / 情绪 / 外部冲击 / 微观恶化
大部分复用已有cache，只新拉: 估值(index_dailybasic) + 涨跌停(limit_list_d) + 成交额
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
    """调用 Tushare 私有 API"""
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30, proxies={'http': None, 'https': None})
            if not r.text.strip():
                if attempt < 2:
                    time.sleep(1)
                    continue
                return pd.DataFrame()
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
        next_day = pd.to_datetime(str(last)) + pd.Timedelta(days=1)
        return next_day.strftime('%Y%m%d')
    return (dt.date.today() - dt.timedelta(days=default_days)).strftime('%Y%m%d')


def get_recent_trade_dates(n=30):
    """通过拉取上证指数日线获取最近交易日"""
    start = (dt.date.today() - dt.timedelta(days=n * 2)).strftime('%Y%m%d')
    end = dt.date.today().strftime('%Y%m%d')
    df = ts_api('index_dailybasic', ts_code='000001.SH',
                start_date=start, end_date=end,
                fields='ts_code,trade_date')
    if df.empty:
        return []
    dates = sorted(df['trade_date'].astype(str).unique())
    return dates[-n:]


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
            if os.path.exists(csv_path):
                old = pd.read_csv(csv_path)
                old['trade_date'] = old['trade_date'].astype(str)
                df = pd.concat([old, df]).drop_duplicates('trade_date').sort_values('trade_date')
            df.to_csv(csv_path, index=False)
            print(f"  {name}: {len(df)}条")
        else:
            print(f"  {name}: 无新数据")
        time.sleep(0.3)

    # 2. 涨跌停统计 (最近30个交易日)
    print("\n[2/3] 拉取涨跌停统计（最近30天）...")
    trade_dates = get_recent_trade_dates(30)
    print(f"  获取到 {len(trade_dates)} 个交易日")

    # 读取已有数据，只拉增量
    limit_csv = os.path.join(CACHE_DIR, 'limit_stats.csv')
    existing_dates = set()
    if os.path.exists(limit_csv):
        old_limit = pd.read_csv(limit_csv)
        existing_dates = set(old_limit['trade_date'].astype(str))

    limit_data = []
    new_dates = [d for d in trade_dates if d not in existing_dates]
    for td in new_dates:
        df = ts_api('limit_list_d', trade_date=td,
                     fields='ts_code,trade_date,name,limit')
        if not df.empty:
            up_limit = len(df[df['limit'] == 'U'])
            down_limit = len(df[df['limit'] == 'D'])
            limit_data.append({'trade_date': td, 'up_limit': up_limit, 'down_limit': down_limit})
        time.sleep(0.3)
    
    if limit_data:
        new_df = pd.DataFrame(limit_data)
        if os.path.exists(limit_csv):
            old_df = pd.read_csv(limit_csv)
            old_df['trade_date'] = old_df['trade_date'].astype(str)
            combined = pd.concat([old_df, new_df]).drop_duplicates('trade_date').sort_values('trade_date')
        else:
            combined = new_df
        combined.to_csv(limit_csv, index=False)
        print(f"  涨跌停: 新增{len(limit_data)}天，共{len(combined)}天")
    else:
        print(f"  涨跌停: 无需更新")

    # 3. 成交额 (用上证指数 amount 代替全市场成交额)
    print("\n[3/3] 拉取全A成交额（增量）...")
    amount_csv = os.path.join(CACHE_DIR, 'daily_amount.csv')
    start_amount = get_start_date(amount_csv, default_days=120)
    
    # 用沪深300的daily数据获取成交额（private API 支持带ts_code的daily）
    amount_df = ts_api('daily', ts_code='000001.SH',
                        start_date=start_amount, end_date=end,
                        fields='trade_date,amount')
    if not amount_df.empty:
        amount_df['trade_date'] = pd.to_datetime(amount_df['trade_date']).dt.strftime('%Y%m%d')
        amount_df['amount'] = pd.to_numeric(amount_df['amount'], errors='coerce')
        if os.path.exists(amount_csv):
            old_amount = pd.read_csv(amount_csv)
            old_amount['trade_date'] = old_amount['trade_date'].astype(str)
            amount_df = pd.concat([old_amount, amount_df]).drop_duplicates('trade_date').sort_values('trade_date')
        amount_df.to_csv(amount_csv, index=False)
        print(f"  成交额: {len(amount_df)}天")
    else:
        print(f"  成交额: 无新数据")

    print("\n✅ 数据拉取完成")


if __name__ == '__main__':
    main()
