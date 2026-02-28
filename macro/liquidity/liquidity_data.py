#!/usr/bin/env python3
"""
境内流动性 - 数据拉取（增量模式）
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


# ── 增量工具函数 ──

def read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_date(csv_path, date_col):
    df = read_csv(csv_path)
    if df.empty:
        return None
    return str(df[date_col].max())


def save_incremental(csv_path, new_data, date_col):
    """追加新数据到已有CSV，去重+排序"""
    if new_data.empty:
        return
    old = read_csv(csv_path)
    combined = pd.concat([old, new_data]).drop_duplicates(subset=[date_col]).sort_values(date_col)
    combined.to_csv(csv_path, index=False)
    print(f"  保存 {len(combined)} 条 (新增 {len(combined) - len(old)})")


def main():
    print("=" * 50)
    print("境内流动性 - 数据拉取（增量模式）")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')
    default_start_60 = (dt.date.today() - dt.timedelta(days=120)).strftime('%Y%m%d')
    default_start_24m = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m%d')

    # ── 1. Shibor ──
    print("拉取 Shibor...")
    shibor_path = os.path.join(CACHE_DIR, 'shibor.csv')
    last = get_last_date(shibor_path, 'date')
    if last:
        start = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        if start > end:
            print("  已是最新，跳过")
        else:
            print(f"  增量拉取: {start} → {end}")
    else:
        start = default_start_60
        print(f"  首次全量拉取: {start} → {end}")

    if not (last and start > end):
        shibor = ts_api('shibor',
                         fields='date,on,1w,2w,1m,3m,6m,9m,1y',
                         start_date=start, end_date=end)
        save_incremental(shibor_path, shibor, 'date')

    time.sleep(0.5)

    # ── 2. DR007 ──
    print("拉取 DR007...")
    dr_path = os.path.join(CACHE_DIR, 'dr007.csv')
    last = get_last_date(dr_path, 'trade_date')
    if last:
        cal_start = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        if cal_start > end:
            print("  已是最新，跳过")
        else:
            print(f"  增量拉取: {cal_start} → {end}")
    else:
        cal_start = default_start_60
        print(f"  首次全量拉取: {cal_start} → {end}")

    if not (last and cal_start > end):
        trade_cal = ts_api('trade_cal', fields='cal_date,is_open',
                            exchange='SSE', start_date=cal_start, end_date=end)
        trade_dates = []
        if not trade_cal.empty:
            trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].sort_values().tolist()

        dr_data = []
        for td in trade_dates:
            df = ts_api('repo_daily',
                        fields='ts_code,trade_date,repo_maturity,close,amount',
                        trade_date=td)
            if not df.empty:
                dr7 = df[df['repo_maturity'] == 'DR007']
                if not dr7.empty:
                    dr_data.append(dr7.iloc[0].to_dict())
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
            new_dr = pd.DataFrame(dr_data)
            save_incremental(dr_path, new_dr, 'trade_date')

    time.sleep(0.5)

    # ── 3. M1/M2 ──
    print("拉取 M1/M2...")
    m_path = os.path.join(CACHE_DIR, 'money_supply.csv')
    last = get_last_date(m_path, 'month')
    if last:
        # month 列格式为 YYYYMM，下一个月
        last_ts = pd.Timestamp(str(last) + '01') if len(str(last)) == 6 else pd.Timestamp(str(last))
        next_month = last_ts + pd.DateOffset(months=1)
        start_m = next_month.strftime('%Y%m')
        end_m = dt.date.today().strftime('%Y%m')
        if start_m > end_m:
            print("  已是最新，跳过")
        else:
            print(f"  增量拉取: {start_m} → {end_m}")
    else:
        start_m = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m')
        end_m = dt.date.today().strftime('%Y%m')
        print(f"  首次全量拉取: {start_m} → {end_m}")

    if not (last and start_m > end_m):
        m_data = ts_api('cn_m',
                         fields='month,m0_yoy,m1_yoy,m2_yoy',
                         start_month=start_m, end_month=end_m)
        save_incremental(m_path, m_data, 'month')

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
