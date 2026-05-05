#!/usr/bin/env python3
"""
全球金融日历 - 数据拉取
数据源：Tushare pro.eco_cal（北京时间，含前值/预期/实际）
窗口：本周一 到 下周五（T-7 ~ T+14，给足缓冲）
输出：cache/eco_cal_raw.csv
"""
import os, sys, time, json
import datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'


def ts_api(api_name, **kwargs):
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': {k: v for k, v in kwargs.items() if v is not None}}
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30, proxies={'http': None, 'https': None})
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            d = j.get('data', {})
            return pd.DataFrame(d.get('items', []), columns=d.get('fields', []))
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_week_range():
    """返回 (本周一, 下下周五)"""
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())  # 本周一
    end = monday + dt.timedelta(days=18)  # 下下周五 = 本周一 + 2周4天
    return monday.strftime('%Y%m%d'), end.strftime('%Y%m%d')


def main():
    print("=" * 50)
    print("全球金融日历 - 数据拉取")
    print("=" * 50)

    start, end = get_week_range()
    print(f"窗口: {start} → {end}")

    df = ts_api('eco_cal', start_date=start, end_date=end)
    if df.empty:
        print("拉取失败或无数据")
        return

    # 列标准化 + 去除空事件名
    df = df[df['event'].notna() & (df['event'].str.strip() != '')]
    df = df.drop_duplicates(subset=['date', 'time', 'currency', 'event'])

    out = os.path.join(CACHE_DIR, 'eco_cal_raw.csv')
    df.to_csv(out, index=False, encoding='utf-8-sig')
    print(f"  保存 {len(df)} 条 → {out}")

    # 按货币分布简报
    print("\n货币分布:")
    for cur, cnt in df['currency'].value_counts().head(10).items():
        print(f"  {cur:5s} {cnt:3d}")

    print(f"\n✓ 完成 @ {dt.datetime.now().strftime('%H:%M:%S')}")


if __name__ == '__main__':
    main()
