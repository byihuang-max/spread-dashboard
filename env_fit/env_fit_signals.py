#!/usr/bin/env python3
"""策略环境适配度 - 信号摘要生成"""
import os, json
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, 'env_fit_signals.json')


def main():
    signals = []

    # 1. 宽基量化 - 因子表现
    qp = os.path.join(BASE, 'quant_stock', 'quant_stock_data.json')
    if os.path.exists(qp):
        d = json.load(open(qp))
        factors = d.get('factor', [])
        if factors and len(factors) >= 6:
            latest = factors[-1]
            prev5 = factors[-6]
            best_factor = max(['价值', '成长', '红利', '小盘'],
                             key=lambda f: (latest.get(f, 1) / prev5.get(f, 1) - 1) if prev5.get(f, 1) else 0)
            chg = (latest.get(best_factor, 1) / prev5.get(best_factor, 1) - 1) * 100
            signals.append(f'量化: {best_factor}因子领跑 ({chg:+.1f}%/5日)')

    # 2. 强势股
    mp = os.path.join(BASE, 'momentum_stock', 'momentum_sentiment.json')
    if os.path.exists(mp):
        d = json.load(open(mp))
        daily = d.get('daily', [])
        if daily:
            latest = daily[-1]
            score = latest.get('composite')
            if score is not None:
                if score > 70:
                    signals.append(f'强势股: 情绪高涨 {score:.0f}分 🔥')
                elif score < 30:
                    signals.append(f'强势股: 情绪低迷 {score:.0f}分 ❄️')
                else:
                    signals.append(f'强势股: 情绪中性 {score:.0f}分')

    # 3. CTA
    cp = os.path.join(BASE, 'commodity_cta', 'commodity_cta.json')
    if os.path.exists(cp):
        d = json.load(open(cp))
        m1 = d.get('mod1_cta_env', {})
        trend_count = 0
        m2 = d.get('mod2_trend_scan', {})
        if isinstance(m2, dict):
            items = m2.get('items', [])
            trend_count = sum(1 for it in items if it.get('trend') in ('上涨', 'UP'))
            total = len(items) if items else 1
            signals.append(f'CTA: {trend_count}/{total}品种趋势向上')

    # 4. 转债
    cbp = os.path.join(BASE, 'cb_env', 'cb_env.json')
    if os.path.exists(cbp):
        d = json.load(open(cbp))
        score = d.get('score')
        details = d.get('score_details', [])
        if score is not None:
            if score >= 70:
                signals.append(f'转债: 环境友好 {score:.0f}分 🟢')
            elif score <= 40:
                signals.append(f'转债: 环境偏弱 {score:.0f}分 🔴')
            else:
                signals.append(f'转债: 环境中性 {score:.0f}分')

    # 5. 套利
    arb_files = ['mod1_index_arb.json', 'mod2_commodity_arb.json', 'mod3_option_arb.json']
    arb_opps = 0
    for af in arb_files:
        ap = os.path.join(BASE, 'arbitrage', af)
        if os.path.exists(ap):
            d = json.load(open(ap))
            if isinstance(d, dict):
                opps = d.get('opportunities', d.get('items', []))
                if isinstance(opps, list):
                    arb_opps += len([o for o in opps if o.get('signal') or o.get('opportunity')])
    if arb_opps > 0:
        signals.append(f'套利: {arb_opps}个机会信号')

    # 6. 商品期权双卖
    ovp = os.path.join(BASE, 'option_vol', 'option_vol.json')
    if os.path.exists(ovp):
        d = json.load(open(ovp))
        comp = d.get('mod9_composite_score', {}) if isinstance(d, dict) else {}
        regime = comp.get('regime', {}) if isinstance(comp, dict) else {}
        label = regime.get('label')
        avg_score = regime.get('avg_composite_score')
        n_sellable = regime.get('n_sellable')
        top3 = regime.get('top3', [])
        top_symbols = '/'.join(x.get('symbol') for x in top3[:3] if x.get('symbol'))
        if label == 'STRONG_SELL_VOL':
            signals.append(f'期权双卖: 系统性窗口 avg={avg_score} 可卖={n_sellable}个 {top_symbols} 🟢')
        elif label == 'SELECTIVE_SELL':
            signals.append(f'期权双卖: 精选窗口 avg={avg_score} 可卖={n_sellable}个 {top_symbols} 🟡')
        elif label == 'NEUTRAL':
            signals.append(f'期权双卖: 中性观察 avg={avg_score} {top_symbols}')
        elif label == 'AVOID_SELLING':
            signals.append(f'期权双卖: 不宜开仓 avg={avg_score} 🔴')

    if not signals:
        signals = ['策略环境无极端信号 ✅']

    result = {'signals': signals, 'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT}")
    for s in signals:
        print(f"  - {s}")


if __name__ == '__main__':
    main()
