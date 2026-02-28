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


def read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_month(csv_path, date_col='month'):
    df = read_csv(csv_path)
    if df.empty:
        return None
    return str(df[date_col].max())


def next_month(yyyymm_str):
    """给定 'YYYYMM' 字符串，返回下一个月的 'YYYYMM'"""
    y, m = int(yyyymm_str[:4]), int(yyyymm_str[4:6])
    m += 1
    if m > 12:
        y += 1
        m = 1
    return f"{y:04d}{m:02d}"


def incremental_save(new_df, csv_path, date_col='month'):
    """将 new_df 追加到已有 CSV，去重+排序"""
    if new_df.empty:
        print("  无新数据")
        return
    old = read_csv(csv_path)
    combined = pd.concat([old, new_df]).drop_duplicates(subset=[date_col]).sort_values(date_col)
    combined.to_csv(csv_path, index=False)
    print(f"  新增 {len(new_df)} 条, 合计 {len(combined)} 条")


def main():
    print("=" * 50)
    print("经济基本面 - 数据拉取 (增量模式)")
    print("=" * 50)

    default_start = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m')
    end_m = dt.date.today().strftime('%Y%m')

    # PMI - 不传fields，拿全部字段再筛选
    pmi_path = os.path.join(CACHE_DIR, 'pmi.csv')
    last = get_last_month(pmi_path)
    start_m = next_month(last) if last else default_start
    print(f"拉取 PMI... (从 {start_m} 到 {end_m})")
    if start_m > end_m:
        print("  已是最新，跳过")
    else:
        pmi = ts_api('cn_pmi', start_month=start_m, end_month=end_m)
        if not pmi.empty:
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
            keep = [c for c in ['month', 'pmi', 'pmi_nmp'] if c in pmi.columns]
            pmi = pmi[keep]
            incremental_save(pmi, pmi_path)
        else:
            print("  无新数据")

    time.sleep(0.5)

    # CPI
    cpi_path = os.path.join(CACHE_DIR, 'cpi.csv')
    last = get_last_month(cpi_path)
    start_m = next_month(last) if last else default_start
    print(f"拉取 CPI... (从 {start_m} 到 {end_m})")
    if start_m > end_m:
        print("  已是最新，跳过")
    else:
        cpi = ts_api('cn_cpi', fields='month,nt_yoy',
                      start_month=start_m, end_month=end_m)
        incremental_save(cpi, cpi_path)

    time.sleep(0.5)

    # PPI
    ppi_path = os.path.join(CACHE_DIR, 'ppi.csv')
    last = get_last_month(ppi_path)
    start_m = next_month(last) if last else default_start
    print(f"拉取 PPI... (从 {start_m} 到 {end_m})")
    if start_m > end_m:
        print("  已是最新，跳过")
    else:
        ppi = ts_api('cn_ppi', fields='month,ppi_yoy',
                      start_month=start_m, end_month=end_m)
        incremental_save(ppi, ppi_path)

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
