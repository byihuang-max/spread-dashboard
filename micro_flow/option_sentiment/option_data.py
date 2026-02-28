#!/usr/bin/env python3
"""
期权情绪面板 - 数据拉取
标的：300ETF(510300) / 500ETF(510500) / 科创50ETF(588000)
数据：opt_basic(合约信息) + opt_daily(日线含OI) + ETF日线(标的价格)
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# 关注的标的
UNDERLYINGS = {
    'OP000300.SH': {'name': '沪深300',    'etf': '000300.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
    'OP000016.SH': {'name': '上证50',     'etf': '000016.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
    'OP510500.SH': {'name': '中证500ETF', 'etf': '510500.SH', 'exchange': 'SSE',   'price_src': 'fund_daily'},
    'OP000852.SH': {'name': '中证1000',   'etf': '000852.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
}


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
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_trade_dates(n=60):
    end = dt.date.today().strftime('%Y%m%d')
    start = (dt.date.today() - dt.timedelta(days=n * 2)).strftime('%Y%m%d')
    df = ts_api('trade_cal', fields='cal_date,is_open',
                exchange='SSE', start_date=start, end_date=end)
    if df.empty:
        return []
    df = df[df['is_open'] == 1].sort_values('cal_date')
    return df['cal_date'].tolist()[-n:]


def fetch_opt_basic():
    """获取全部活跃期权合约信息"""
    print("拉取期权合约信息...")
    all_contracts = []
    for opt_code, info in UNDERLYINGS.items():
        df = ts_api('opt_basic',
                    fields='ts_code,name,opt_code,call_put,exercise_price,maturity_date,list_date,delist_date,per_unit',
                    exchange=info['exchange'], opt_code=opt_code)
        if df.empty:
            print(f"  {info['name']} 无合约")
            continue
        # 只保留未到期的
        today = dt.date.today().strftime('%Y%m%d')
        df = df[df['delist_date'] >= today].copy()
        df['underlying'] = opt_code
        df['underlying_name'] = info['name']
        all_contracts.append(df)
        print(f"  {info['name']}: {len(df)}个活跃合约")
        time.sleep(0.3)
    if not all_contracts:
        return pd.DataFrame()
    return pd.concat(all_contracts).reset_index(drop=True)


def fetch_opt_daily(trade_dates):
    """拉取期权日线（按天拉，包含OI）"""
    print("拉取期权日线...")
    recent = trade_dates[-25:]  # 25天够算20日分位
    all_data = []
    for td in recent:
        for ex in sorted(set(info['exchange'] for info in UNDERLYINGS.values())):
            df = ts_api('opt_daily',
                        fields='ts_code,trade_date,close,settle,vol,amount,oi',
                        trade_date=td, exchange=ex)
            if not df.empty:
                all_data.append(df)
            time.sleep(0.35)
    if not all_data:
        print("  期权日线无数据!")
        return pd.DataFrame()
    result = pd.concat(all_data).reset_index(drop=True)
    print(f"  期权日线: {len(result)}条, {len(recent)}天")
    return result


def fetch_etf_daily(trade_dates):
    """拉取标的ETF日线（用于BS模型）"""
    print("拉取标的ETF价格...")
    start, end = trade_dates[0], trade_dates[-1]
    all_data = []
    for opt_code, info in UNDERLYINGS.items():
        src = info.get('price_src', 'fund_daily')
        df = ts_api(src,
                    fields='ts_code,trade_date,close',
                    ts_code=info['etf'], start_date=start, end_date=end)
        if df.empty and src == 'fund_daily':
            df = ts_api('daily',
                        fields='ts_code,trade_date,close',
                        ts_code=info['etf'], start_date=start, end_date=end)
        if df.empty and src == 'index_daily':
            df = ts_api('daily',
                        fields='ts_code,trade_date,close',
                        ts_code=info['etf'], start_date=start, end_date=end)
        if not df.empty:
            all_data.append(df)
            print(f"  {info['name']}: {len(df)}条")
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    return pd.concat(all_data).reset_index(drop=True)


def main():
    print("=" * 50)
    print("期权情绪面板 - 数据拉取")
    print("=" * 50)

    trade_dates = get_trade_dates(60)
    if not trade_dates:
        print("获取交易日失败!")
        sys.exit(1)
    print(f"交易日: {trade_dates[0]} ~ {trade_dates[-1]}, 共{len(trade_dates)}天")

    contracts = fetch_opt_basic()
    opt_daily = fetch_opt_daily(trade_dates)
    etf_daily = fetch_etf_daily(trade_dates)

    for name, df, fname in [
        ('合约', contracts, 'opt_contracts.csv'),
        ('期权日线', opt_daily, 'opt_daily.csv'),
        ('ETF日线', etf_daily, 'etf_daily.csv'),
    ]:
        if not df.empty:
            df.to_csv(os.path.join(CACHE_DIR, fname), index=False)
            print(f"  {name}: {len(df)}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
