#!/usr/bin/env python3
"""
全球利率与汇率 - 数据拉取
中国10Y国债(yc_cb) / 美债10Y(us_tycr) / USDCNY+USDCNH(iFind)
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# iFind
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAyLTA5IDE5OjE3OjQwIn0=.eyJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyIjp7ImFjY291bnQiOiJncnN6aDAwMSIsImF1dGhVc2VySW5mbyI6eyJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbXSwiaGFzQUlQcmVkaWN0IjpmYWxzZSwiaGFzQUlUYWxrIjpmYWxzZSwiaGFzQ0lDQyI6ZmFsc2UsImhhc0NTSSI6ZmFsc2UsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1heE9uTGluZSI6MSwibm9EaXNrIjpmYWxzZSwicHJvZHVjdFR5cGUiOiJTVVBFUkNPTU1BTkRQUk9EVUNUIiwicmVmcmVzaFRva2VuRXhwaXJlZFRpbWUiOiIyMDI2LTAzLTA5IDE5OjAwOjU1Iiwic2Vzc3Npb24iOiI0YzRjYjhhNTdiNWQwYzA3N2UxNTEwMzIxN2M2YWNjYSIsInNpZEluZm8iOns2NDoiMTExMTExMTExMTExMTExMTExMTExMTExIiwxOiIxMDEiLDI6IjEiLDY3OiIxMDExMTExMTExMTExMTExMTExMTExMTEiLDM6IjEiLDY5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw1OiIxIiw2OiIxIiw3MToiMTExMTExMTExMTExMTExMTExMTExMTAwIiw3OiIxMTExMTExMTExMSIsODoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDEiLDEzODoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTM5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDA6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQyOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDM6IjExIiw4MDoiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MToiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MjoiMTExMTExMTExMTExMTExMTExMTEwMTEwIiw4MzoiMTExMTExMTExMTExMTExMTExMDAwMDAwIiw4NToiMDExMTExMTExMTExMTExMTExMTExMTExIiw4NzoiMTExMTExMTEwMDExMTExMDExMTExMTExIiw4OToiMTExMTExMTEwMTEwMTExMTExMTAxMTExIiw5MDoiMTExMTEwMTExMTExMTExMTExMTExMTExMTAiLDkzOiIxMTExMTExMTExMTExMTExMTAwMDAxMTExIiw5NDoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsOTY6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk5OiIxMDAiLDEwMDoiMTExMTAxMTExMTExMTExMTExMCIsMTAyOiIxIiw0NDoiMTEiLDEwOToiMSIsNTM6IjExMTExMTExMTExMTExMTExMTExMTExMSIsNTQ6IjExMDAwMDAwMDAxMTAwMDAwMTAxMDAwMDAxMDAxMDAwMDAwIiw1NzoiMDAwMDAwMDAwMDAwMDAwMDAwMDAxMDAwMDAwMDAiLDYyOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDYzOiIxMTExMTExMTExMTExMTExMTExMTExMTEifSwidGltZXN0YW1wIjoiMTc3MDYzNTg2MDcxOSIsInRyYW5zQXV0aCI6ZmFsc2UsInR0bFZhbHVlIjowLCJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyVHlwZSI6Ik9GRklDSUFMIiwid2lmaW5kTGltaXRNYXAiOnt9fX0=.7AAB9445C9074F4FD9C933A4ECF96C3359428E3393255673AFE507504D9E7270'


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


def get_ifind_token():
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
    except Exception as e:
        print(f"  iFind token error: {e}")
    return None


def ifind_rt(access_token, codes, indicators='latest'):
    try:
        r = requests.post(f'{IFIND_BASE}/real_time_quotation',
            json={'codes': codes, 'indicators': indicators},
            headers={'Content-Type': 'application/json', 'access_token': access_token},
            timeout=15)
        return r.json()
    except Exception as e:
        print(f"  iFind error: {e}")
        return None


def read_csv(path):
    """读取CSV，不存在则返回空DataFrame"""
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_date(csv_path, date_col='trade_date'):
    """获取CSV中最后一个日期（字符串）"""
    df = read_csv(csv_path)
    if df.empty or date_col not in df.columns:
        return None
    return str(df[date_col].max())


def save_incremental(new_data, csv_path, date_col):
    """增量追加：与已有CSV合并、去重、排序后保存"""
    if new_data.empty:
        return
    old = read_csv(csv_path)
    combined = pd.concat([old, new_data]).drop_duplicates(subset=[date_col]).sort_values(date_col)
    combined.to_csv(csv_path, index=False)


def main():
    print("=" * 50)
    print("全球利率与汇率 - 数据拉取（增量模式）")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')
    default_start = (dt.date.today() - dt.timedelta(days=400)).strftime('%Y%m%d')

    # 1. 中国10Y国债收益率
    cn10y_path = os.path.join(CACHE_DIR, 'cn10y.csv')
    last_cn = get_last_date(cn10y_path, 'trade_date')
    if last_cn:
        cn_start = (pd.Timestamp(last_cn) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        print(f"拉取中国国债收益率（增量: {cn_start} → {end}）...")
    else:
        cn_start = default_start
        print(f"拉取中国国债收益率（全量: {cn_start} → {end}）...")

    if cn_start <= end:
        trade_cal = ts_api('trade_cal', fields='cal_date,is_open',
                            exchange='SSE', start_date=cn_start, end_date=end)
        trade_dates = []
        if not trade_cal.empty:
            trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].sort_values().tolist()

        cn10y_data = []
        for td in trade_dates:
            df = ts_api('yc_cb',
                        fields='ts_code,trade_date,curve_type,curve_term,yield',
                        ts_code='1001.CB', curve_type='0', trade_date=td)
            if not df.empty:
                df['curve_term'] = pd.to_numeric(df['curve_term'], errors='coerce')
                df['yield'] = pd.to_numeric(df['yield'], errors='coerce')
                y10 = df[(df['curve_term'] >= 9.5) & (df['curve_term'] <= 10.5)]
                if not y10.empty:
                    cn10y_data.append({'trade_date': td, 'cn10y': round(float(y10.iloc[0]['yield']), 4)})
            time.sleep(0.3)

        if cn10y_data:
            save_incremental(pd.DataFrame(cn10y_data), cn10y_path, 'trade_date')
            print(f"  中国10Y: 新增{len(cn10y_data)}条")
        else:
            print("  中国10Y: 无新数据")
    else:
        print("  中国10Y: 已是最新")

    time.sleep(0.5)

    # 2. 美国国债收益率
    us_path = os.path.join(CACHE_DIR, 'us_treasury.csv')
    last_us = get_last_date(us_path, 'date')
    if last_us:
        us_start = (pd.Timestamp(last_us) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        print(f"拉取美国国债收益率（增量: {us_start} → {end}）...")
    else:
        us_start = default_start
        print(f"拉取美国国债收益率（全量: {us_start} → {end}）...")

    if us_start <= end:
        us_data = ts_api('us_tycr',
                          fields='date,y1,y2,y3,y5,y10,y30',
                          start_date=us_start, end_date=end)
        if not us_data.empty:
            save_incremental(us_data, us_path, 'date')
            print(f"  美债: 新增{len(us_data)}条")
        else:
            print("  美债: 无新数据")
    else:
        print("  美债: 已是最新")

    time.sleep(0.5)

    # 3. 汇率 (iFind)
    print("拉取汇率 (iFind)...")
    at = get_ifind_token()
    if at:
        print("  iFind token OK")
        resp = ifind_rt(at, 'USDCNY.FX,USDCNH.FX', 'latest,change,pct_change')
        if resp and resp.get('errorcode') == 0:
            tables = resp.get('tables', [])
            fx_rows = []
            for t in tables:
                code = t.get('thscode', '')
                vals = t.get('table', {})
                latest = vals.get('latest', [None])[0]
                chg = vals.get('change', [None])[0]
                pct = vals.get('pct_change', [None])[0]
                fx_rows.append({'code': code, 'latest': latest, 'change': chg, 'pct_change': pct})
            if fx_rows:
                pd.DataFrame(fx_rows).to_csv(os.path.join(CACHE_DIR, 'fx_realtime.csv'), index=False)
                print(f"  汇率: {len(fx_rows)}条")
    else:
        print("  iFind token 获取失败")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
