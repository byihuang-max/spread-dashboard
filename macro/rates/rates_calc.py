#!/usr/bin/env python3
"""全球利率与汇率 - 计算"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'rates.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def fmt_date(d):
    s = str(d).replace('-', '')
    return f"{s[4:6]}-{s[6:8]}" if len(s) == 8 else str(d)


def calc():
    cn10y = load_csv('cn10y.csv')
    us = load_csv('us_treasury.csv')
    fx = load_csv('fx_realtime.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'signals': [],
    }

    # ── 中国10Y ──
    if not cn10y.empty:
        cn10y['cn10y'] = pd.to_numeric(cn10y['cn10y'], errors='coerce')
        cn10y = cn10y.dropna().sort_values('trade_date')
        result['cn10y'] = [{'date': fmt_date(r['trade_date']), 'value': round(float(r['cn10y']), 4)}
                           for _, r in cn10y.iterrows()]

    # ── 美债 ──
    if not us.empty:
        us['y10'] = pd.to_numeric(us['y10'], errors='coerce')
        us = us.dropna(subset=['y10']).sort_values('date')
        result['us10y'] = [{'date': fmt_date(r['date']), 'value': round(float(r['y10']), 4)}
                           for _, r in us.iterrows()]

    # ── 中美利差 ──
    if not cn10y.empty and not us.empty:
        cn_dict = dict(zip(cn10y['trade_date'].astype(str).str.replace('-', ''), cn10y['cn10y']))
        spread_data = []
        for _, r in us.iterrows():
            d = str(r['date']).replace('-', '')
            us_val = float(r['y10'])
            cn_val = cn_dict.get(d)
            if cn_val is not None:
                spread_data.append({'date': fmt_date(d), 'spread': round(float(cn_val) - us_val, 4)})
        result['spread'] = spread_data

        if spread_data:
            latest_spread = spread_data[-1]['spread']
            if latest_spread < -1.5:
                result['signals'].append(f"中美利差 {latest_spread:+.2f}%，资金外流压力大 🔴")
            elif latest_spread > -0.5:
                result['signals'].append(f"中美利差 {latest_spread:+.2f}%，利差压力缓解 🟢")
            else:
                result['signals'].append(f"中美利差 {latest_spread:+.2f}%")

    # ── 汇率 ──
    if not fx.empty:
        fx_info = {}
        for _, r in fx.iterrows():
            fx_info[r['code']] = {
                'latest': float(r['latest']) if pd.notna(r['latest']) else None,
                'change': float(r['change']) if pd.notna(r['change']) else None,
                'pct_change': float(r['pct_change']) if pd.notna(r['pct_change']) else None,
            }
        result['fx'] = fx_info

        cny = fx_info.get('USDCNY.FX', {})
        cnh = fx_info.get('USDCNH.FX', {})
        if cny.get('latest') and cnh.get('latest'):
            spread = cnh['latest'] - cny['latest']
            result['fx_spread'] = round(spread, 4)
            if abs(spread) > 0.03:
                result['signals'].append(f"在岸离岸价差 {spread*1000:.0f}点，{'离岸偏弱' if spread > 0 else '离岸偏强'} ⚠️")

    if not result['signals']:
        result['signals'] = ['利率汇率无极端信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
