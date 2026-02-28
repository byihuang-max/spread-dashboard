#!/usr/bin/env python3
"""风格轧差 - 信号摘要生成（含4个tab独立结论）"""
import os, json
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, 'style_spread_signals.json')


def safe_tail(series, n=5):
    vals = series.dropna()
    return vals.tail(n) if len(vals) >= n else vals


def nav_change(series, n=5):
    vals = series.dropna()
    if len(vals) < n + 1:
        return None
    return (float(vals.iloc[-1]) / float(vals.iloc[-n-1]) - 1) * 100


def main():
    signals = []
    tab_signals = {}

    # ═══ Tab1: 经济敏感轧差 ═══
    df1 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet1.csv'))
    tab1 = []
    nav_col = '中证红利-科创50净值'
    if nav_col in df1.columns:
        chg5 = nav_change(df1[nav_col], 5)
        chg20 = nav_change(df1[nav_col], 20)
        vals = df1[nav_col].dropna()
        if len(vals) > 0:
            latest_nav = float(vals.iloc[-1])
            total_ret = (latest_nav - 1) * 100
            tab1.append(f'净值 {latest_nav:.4f}，累计收益 {total_ret:+.1f}%')
        if chg5 is not None:
            if chg5 > 1:
                tab1.append(f'近5日周期跑赢成长 {chg5:+.1f}%，经济景气预期上行 🔴')
                signals.append(f'周期>成长 ({chg5:+.1f}%/5日) 🔴')
            elif chg5 < -1:
                tab1.append(f'近5日成长跑赢周期 {chg5:+.1f}%，市场偏好防御/成长 🟢')
                signals.append(f'成长>周期 ({chg5:+.1f}%/5日) 🟢')
            else:
                tab1.append(f'近5日周期vs成长窄幅震荡 {chg5:+.1f}%')
        if chg20 is not None:
            direction = '周期占优' if chg20 > 0 else '成长占优'
            tab1.append(f'近20日趋势: {direction} ({chg20:+.1f}%)')

    # 周期热点
    for col in ['有色金属涨跌幅%', '煤炭涨跌幅%', '钢铁涨跌幅%']:
        if col in df1.columns:
            vals = df1[col].dropna()
            if len(vals) > 0 and float(vals.iloc[-1]) > 2:
                tab1.append(f'{col.replace("涨跌幅%","")}今日+{float(vals.iloc[-1]):.1f}% 🔥')

    tab_signals['eco'] = tab1 if tab1 else ['经济敏感轧差无极端信号']

    # ═══ Tab2: 拥挤-反身性 ═══
    df4 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet4.csv'))
    tab2 = []
    if '轧差净值' in df4.columns:
        chg5 = nav_change(df4['轧差净值'], 5)
        chg20 = nav_change(df4['轧差净值'], 20)
        vals = df4['轧差净值'].dropna()
        if len(vals) > 0:
            latest_nav = float(vals.iloc[-1])
            total_ret = (latest_nav - 1) * 100
            tab2.append(f'高拥挤-低拥挤净值 {latest_nav:.4f}，累计 {total_ret:+.1f}%')
        if chg5 is not None:
            if chg5 > 1:
                tab2.append(f'近5日高拥挤跑赢 {chg5:+.1f}%，趋势延续/追高风险 ⚠️')
                signals.append(f'高拥挤跑赢 ({chg5:+.1f}%/5日) ⚠️')
            elif chg5 < -1:
                tab2.append(f'近5日低拥挤跑赢 {chg5:+.1f}%，均值回归有效 ✅')
                signals.append(f'低拥挤跑赢 ({chg5:+.1f}%/5日) ✅')
            else:
                tab2.append(f'近5日拥挤度轧差窄幅震荡 {chg5:+.1f}%')
        if chg20 is not None:
            direction = '动量延续' if chg20 > 0 else '均值回归'
            tab2.append(f'近20日趋势: {direction} ({chg20:+.1f}%)')

    if 'Top6行业' in df4.columns and df4['Top6行业'].notna().any():
        tab2.append(f'当前高拥挤: {df4["Top6行业"].dropna().iloc[-1]}')
        signals.append(f'当前高拥挤: {df4["Top6行业"].dropna().iloc[-1]}')
    if 'Bottom6行业' in df4.columns and df4['Bottom6行业'].notna().any():
        tab2.append(f'当前低拥挤: {df4["Bottom6行业"].dropna().iloc[-1]}')

    tab_signals['crowd'] = tab2 if tab2 else ['拥挤度轧差无极端信号']

    # ═══ Tab3: 风格轧差净值 ═══
    tab3 = []
    # 从quant_stock factor数据读取风格对比
    qp = os.path.join(os.path.dirname(BASE), 'env_fit', 'quant_stock', 'quant_stock_data.json')
    if os.path.exists(qp):
        try:
            qd = json.load(open(qp))
            factors = qd.get('factor', [])
            if factors and len(factors) >= 6:
                latest = factors[-1]
                prev5 = factors[-6]
                prev20 = factors[-21] if len(factors) >= 21 else factors[0]
                for f in ['价值', '成长', '红利', '小盘']:
                    chg = (latest.get(f, 1) / prev5.get(f, 1) - 1) * 100
                    chg20 = (latest.get(f, 1) / prev20.get(f, 1) - 1) * 100
                    emoji = '↗' if chg > 0 else '↘'
                    tab3.append(f'{f}因子: 5日{chg:+.1f}% {emoji}  20日{chg20:+.1f}%')
                # 判断风格
                best_5d = max(['价值', '成长', '红利', '小盘'],
                             key=lambda f: (latest.get(f, 1) / prev5.get(f, 1) - 1))
                tab3.insert(0, f'近5日{best_5d}因子领跑')
        except:
            pass

    if not tab3:
        # 退而求其次从sheet1算红利vs科创
        if nav_col in df1.columns:
            vals = df1[nav_col].dropna()
            if len(vals) > 0:
                latest = float(vals.iloc[-1])
                tab3.append(f'红利-科创50净值 {latest:.4f}，{"红利占优" if latest > 1 else "科创占优"}')
    tab_signals['style'] = tab3 if tab3 else ['风格轧差无极端信号']

    # ═══ Tab4: 双创等权 ═══
    df2 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet2.csv'))
    tab4 = []
    if '等权平均涨跌幅%' in df2.columns:
        vals = df2['等权平均涨跌幅%'].dropna()
        if len(vals) >= 5:
            sum5 = float(vals.tail(5).sum())
            sum20 = float(vals.tail(20).sum()) if len(vals) >= 20 else None
            # 计算净值
            cum = 1.0
            for v in vals:
                cum *= (1 + float(v) / 100)
            tab4.append(f'双创等权净值 {cum:.4f}，累计 {(cum-1)*100:+.1f}%')
            emoji = '🟢' if sum5 > 0 else '🔴'
            tab4.append(f'近5日累计 {sum5:+.1f}% {emoji}')
            if sum20 is not None:
                tab4.append(f'近20日累计 {sum20:+.1f}%')

    for col in ['创业板指涨跌幅%', '科创50涨跌幅%']:
        if col in df2.columns:
            vals = df2[col].dropna()
            if len(vals) >= 5:
                sum5 = float(vals.tail(5).sum())
                name = col.replace('涨跌幅%', '')
                tab4.append(f'{name}5日 {sum5:+.1f}%')
                if abs(sum5) > 3:
                    signals.append(f'{name}5日{"累涨" if sum5>0 else "累跌"} {sum5:+.1f}%')

    tab_signals['dual'] = tab4 if tab4 else ['双创等权无极端信号']

    # 周期热点（全局信号）
    df3 = pd.read_csv(os.path.join(BASE, 'style_spread_sheet3.csv'))
    hot_sectors = []
    for col in df3.columns:
        if col.endswith('%') and col != '周期等权%':
            vals = df3[col].dropna()
            if len(vals) > 0 and float(vals.iloc[-1]) > 2:
                hot_sectors.append(f"{col.replace('%','')}{float(vals.iloc[-1]):+.1f}%")
    if hot_sectors:
        signals.append(f"周期热点: {', '.join(hot_sectors[:3])} 🔥")

    if not signals:
        signals = ['风格轧差无极端信号 ✅']

    result = {
        'signals': signals,
        'tab_signals': tab_signals,
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
    }

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT}")
    for tab, sigs in tab_signals.items():
        print(f"\n[{tab}]")
        for s in sigs:
            print(f"  - {s}")
    print(f"\n[全局信号]")
    for s in signals:
        print(f"  - {s}")


if __name__ == '__main__':
    main()
