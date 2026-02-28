#!/usr/bin/env python3
"""
境内流动性 - 计算 & 生成JSON
"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'liquidity.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def calc():
    shibor = load_csv('shibor.csv')
    dr = load_csv('dr007.csv')
    money = load_csv('money_supply.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'signals': [],
    }

    # ── Shibor 期限结构 ──
    if not shibor.empty:
        shibor = shibor.sort_values('date')
        tenors = ['on', '1w', '2w', '1m', '3m', '6m', '9m', '1y']
        tenor_labels = ['O/N', '1W', '2W', '1M', '3M', '6M', '9M', '1Y']

        # 当日
        latest = shibor.iloc[-1]
        today_curve = [round(float(latest[t]), 4) if pd.notna(latest.get(t)) else None for t in tenors]

        # 1周前 & 1月前
        week_ago = shibor.iloc[-6] if len(shibor) >= 6 else shibor.iloc[0]
        month_ago = shibor.iloc[-22] if len(shibor) >= 22 else shibor.iloc[0]
        week_curve = [round(float(week_ago[t]), 4) if pd.notna(week_ago.get(t)) else None for t in tenors]
        month_curve = [round(float(month_ago[t]), 4) if pd.notna(month_ago.get(t)) else None for t in tenors]

        result['shibor_term'] = {
            'tenors': tenor_labels,
            'today': today_curve,
            'week_ago': week_curve,
            'month_ago': month_curve,
            'today_date': str(latest['date']),
        }

        # Shibor O/N 时序
        result['shibor_on'] = [
            {'date': str(r['date'])[4:6] + '-' + str(r['date'])[6:8] if len(str(r['date'])) == 8 else str(r['date']),
             'value': round(float(r['on']), 4) if pd.notna(r.get('on')) else None}
            for _, r in shibor.iterrows()
        ]

        # 信号
        on_val = float(latest['on']) if pd.notna(latest.get('on')) else None
        if on_val is not None:
            if on_val < 1.2:
                result['signals'].append(f'Shibor隔夜 {on_val:.3f}%，资金极度宽松 🟢')
            elif on_val > 2.5:
                result['signals'].append(f'Shibor隔夜 {on_val:.3f}%，资金面偏紧 🔴')

    # ── DR007 ──
    if not dr.empty:
        dr['close'] = pd.to_numeric(dr['close'], errors='coerce')
        dr = dr.dropna(subset=['close']).sort_values('trade_date')

        result['dr007'] = [
            {'date': str(r['trade_date'])[4:6] + '-' + str(r['trade_date'])[6:8] if len(str(r['trade_date'])) == 8 else str(r['trade_date']),
             'dr007': round(float(r['close']), 4),
             'r007': round(float(r['r007_close']), 4) if 'r007_close' in r and pd.notna(r.get('r007_close')) else None}
            for _, r in dr.iterrows()
        ]

        latest_dr = float(dr.iloc[-1]['close'])
        ma20 = dr['close'].tail(20).mean()
        if latest_dr < ma20 * 0.9:
            result['signals'].append(f'DR007 {latest_dr:.2f}% 低于20日均值，资金面宽松 🟢')
        elif latest_dr > ma20 * 1.15:
            result['signals'].append(f'DR007 {latest_dr:.2f}% 高于20日均值，资金面收紧 🔴')

    # ── M1/M2 ──
    if not money.empty:
        money = money.sort_values('month')
        for col in ['m1_yoy', 'm2_yoy', 'm0_yoy']:
            money[col] = pd.to_numeric(money[col], errors='coerce')
        money['scissors'] = money['m1_yoy'] - money['m2_yoy']

        result['money_supply'] = [
            {'month': str(r['month']),
             'm1': round(float(r['m1_yoy']), 1) if pd.notna(r['m1_yoy']) else None,
             'm2': round(float(r['m2_yoy']), 1) if pd.notna(r['m2_yoy']) else None,
             'scissors': round(float(r['scissors']), 1) if pd.notna(r['scissors']) else None}
            for _, r in money.iterrows()
        ]

        latest_m = money.dropna(subset=['m1_yoy', 'm2_yoy']).iloc[-1]
        scissors = float(latest_m['scissors'])
        if scissors > 0:
            result['signals'].append(f"M1-M2剪刀差 {scissors:+.1f}%，资金活化 🟢")
        elif scissors < -5:
            result['signals'].append(f"M1-M2剪刀差 {scissors:+.1f}%，资金趋于保守 🟡")

    if not result['signals']:
        result['signals'] = ['流动性指标无极端信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
