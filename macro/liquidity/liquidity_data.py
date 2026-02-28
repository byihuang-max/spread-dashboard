#!/usr/bin/env python3
"""
境内流动性 - 数据拉取
Shibor / DR007 / 逆回购 / M1M2
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'


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


def main():
    print("=" * 50)
    print("境内流动性 - 数据拉取")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')
    start_60 = (dt.date.today() - dt.timedelta(days=120)).strftime('%Y%m%d')
    start_24m = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m%d')

    # 1. Shibor (60日)
    print("拉取 Shibor...")
    shibor = ts_api('shibor',
                     fields='date,on,1w,2w,1m,3m,6m,9m,1y',
                     start_date=start_60, end_date=end)
    if not shibor.empty:
        shibor.to_csv(os.path.join(CACHE_DIR, 'shibor.csv'), index=False)
        print(f"  Shibor: {len(shibor)}条")

    time.sleep(0.5)

    # 2. 回购利率 DR007 (60日)
    print("拉取 DR007...")
    # repo_daily 按天拉，筛选 DR007
    trade_cal = ts_api('trade_cal', fields='cal_date,is_open',
                        exchange='SSE', start_date=start_60, end_date=end)
    trade_dates = []
    if not trade_cal.empty:
        trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].sort_values().tolist()[-60:]

    dr_data = []
    for td in trade_dates[-60:]:
        df = ts_api('repo_daily',
                    fields='ts_code,trade_date,repo_maturity,close,amount',
                    trade_date=td)
        if not df.empty:
            dr7 = df[df['repo_maturity'] == 'DR007']
            if not dr7.empty:
                dr_data.append(dr7.iloc[0].to_dict())
            # 也拿 R007
            r7 = df[df['repo_maturity'] == 'R007']
            if not r7.empty:
                row = dr7.iloc[0].to_dict() if not dr7.empty else {}
                row['r007_close'] = float(r7.iloc[0]['close']) if pd.notna(r7.iloc[0]['close']) else None
                if dr_data and dr_data[-1]['trade_date'] == td:
                    dr_data[-1]['r007_close'] = row.get('r007_close')
                else:
                    dr_data.append(row)
        time.sleep(0.3)

    if dr_data:
        dr_df = pd.DataFrame(dr_data)
        dr_df.to_csv(os.path.join(CACHE_DIR, 'dr007.csv'), index=False)
        print(f"  DR007: {len(dr_df)}条")

    time.sleep(0.5)

    # 3. M1/M2 (24个月)
    print("拉取 M1/M2...")
    start_m = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m')
    end_m = dt.date.today().strftime('%Y%m')
    m_data = ts_api('cn_m',
                     fields='month,m0_yoy,m1_yoy,m2_yoy',
                     start_month=start_m, end_month=end_m)
    if not m_data.empty:
        m_data.to_csv(os.path.join(CACHE_DIR, 'money_supply.csv'), index=False)
        print(f"  M1/M2: {len(m_data)}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
