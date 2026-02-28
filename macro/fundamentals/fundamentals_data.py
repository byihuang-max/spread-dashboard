#!/usr/bin/env python3
"""经济基本面 - 数据拉取: PMI / CPI / PPI"""
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
    print("经济基本面 - 数据拉取")
    print("=" * 50)

    start_m = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m')
    end_m = dt.date.today().strftime('%Y%m')

    # PMI - 不传fields，拿全部字段再筛选
    print("拉取 PMI...")
    pmi = ts_api('cn_pmi', start_month=start_m, end_month=end_m)
    if not pmi.empty:
        # 统一列名: PMI010000=制造业PMI, PMI020100=非制造业PMI, MONTH=月份
        col_map = {}
        for c in pmi.columns:
            cl = c.upper()
            if cl == 'MONTH':
                col_map[c] = 'month'
            elif cl == 'PMI010000':
                col_map[c] = 'pmi'
            elif cl == 'PMI020100':
                col_map[c] = 'pmi_nmp'
            elif cl == 'PMI':
                col_map[c] = 'pmi'
            elif cl == 'PMI_NMP':
                col_map[c] = 'pmi_nmp'
        pmi = pmi.rename(columns=col_map)
        # 只保留需要的列
        keep = [c for c in ['month', 'pmi', 'pmi_nmp'] if c in pmi.columns]
        pmi = pmi[keep]
        pmi.to_csv(os.path.join(CACHE_DIR, 'pmi.csv'), index=False)
        print(f"  PMI: {len(pmi)}条")

    time.sleep(0.5)

    # CPI
    print("拉取 CPI...")
    cpi = ts_api('cn_cpi',
                  fields='month,nt_yoy',
                  start_month=start_m, end_month=end_m)
    if not cpi.empty:
        cpi.to_csv(os.path.join(CACHE_DIR, 'cpi.csv'), index=False)
        print(f"  CPI: {len(cpi)}条")

    time.sleep(0.5)

    # PPI
    print("拉取 PPI...")
    ppi = ts_api('cn_ppi',
                  fields='month,ppi_yoy',
                  start_month=start_m, end_month=end_m)
    if not ppi.empty:
        ppi.to_csv(os.path.join(CACHE_DIR, 'ppi.csv'), index=False)
        print(f"  PPI: {len(ppi)}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
