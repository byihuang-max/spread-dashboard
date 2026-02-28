#!/usr/bin/env python3
"""风格轧差 - 信号摘要生成"""
import os, json
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, 'style_spread_signals.json')


def safe_float(v):
    try:
        f = float(v)
        return f if not np.isnan(f) else None
    except:
        return None


def main():
    signals = []

    # Sheet1: 周期vs成长
    df1 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet1.csv'))
    nav_col = '中证红利-科创50净值'
    if nav_col in df1.columns:
        vals = df1[nav_col].dropna()
        if len(vals) >= 5:
            latest = float(vals.iloc[-1])
            chg5 = (latest / float(vals.iloc[-6]) - 1) * 100 if len(vals) >= 6 else None
            if chg5 is not None:
                if chg5 > 1:
                    signals.append(f'周期>成长 红利跑赢科创50 ({chg5:+.1f}%/5日) 🔴')
                elif chg5 < -1:
                    signals.append(f'成长>周期 科创50跑赢红利 ({chg5:+.1f}%/5日) 🟢')
                else:
                    signals.append(f'周期vs成长 窄幅震荡 ({chg5:+.1f}%/5日)')

    # Sheet2: 双创等权
    df2 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet2.csv'))
    for col in ['创业板指涨跌幅%', '科创50涨跌幅%']:
        if col in df2.columns:
            vals = df2[col].dropna()
            if len(vals) >= 5:
                sum5 = float(vals.tail(5).sum())
                name = col.replace('涨跌幅%', '')
                if sum5 > 3:
                    signals.append(f'{name}5日累涨 {sum5:+.1f}% ↗')
                elif sum5 < -3:
                    signals.append(f'{name}5日累跌 {sum5:+.1f}% ↘')

    # Sheet3: 周期行业
    df3 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet3.csv'))
    cycle_cols = [c for c in df3.columns if c.endswith('%') and c != '周期等权%']
    hot_sectors = []
    for col in cycle_cols:
        vals = df3[col].dropna()
        if len(vals) >= 1:
            latest = float(vals.iloc[-1])
            if latest > 2:
                hot_sectors.append(f"{col.replace('%','')}+{latest:.1f}%")
    if hot_sectors:
        signals.append(f"周期热点: {', '.join(hot_sectors[:3])} 🔥")

    # Sheet4: 拥挤度轧差
    df4 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet4.csv'))
    if '轧差净值' in df4.columns:
        vals = df4['轧差净值'].dropna()
        if len(vals) >= 5:
            latest = float(vals.iloc[-1])
            chg5 = (latest / float(vals.iloc[-6]) - 1) * 100 if len(vals) >= 6 else None
            if chg5 is not None:
                if chg5 > 1:
                    signals.append(f'高拥挤跑赢低拥挤 ({chg5:+.1f}%/5日) ⚠️追高')
                elif chg5 < -1:
                    signals.append(f'低拥挤跑赢高拥挤 ({chg5:+.1f}%/5日) ✅均值回归')

    if 'Top6行业' in df4.columns:
        top6 = df4['Top6行业'].dropna().iloc[-1] if df4['Top6行业'].notna().any() else ''
        if top6:
            signals.append(f'当前高拥挤: {top6}')

    if not signals:
        signals = ['风格轧差无极端信号 ✅']

    result = {'signals': signals, 'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT}")
    for s in signals:
        print(f"  - {s}")


if __name__ == '__main__':
    main()
