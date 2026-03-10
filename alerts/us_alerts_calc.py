#!/usr/bin/env python3
"""
美股风险监控 - 5维打分 + 综合评分
布局与A股红灯预警一致: 综合评分 + 维度卡片 + 趋势图
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'us_alerts.json')

# 历史危机事件标注
CRISIS_EVENTS = [
    {"date": "2008-09-15", "name": "雷曼倒闭", "type": "金融危机"},
    {"date": "2008-10-10", "name": "VIX创纪录", "type": "金融危机"},
    {"date": "2020-03-16", "name": "熔断", "type": "疫情崩盘"},
    {"date": "2020-03-23", "name": "市场底部", "type": "疫情崩盘"},
    {"date": "2022-03-16", "name": "首次加息", "type": "加息周期"},
    {"date": "2022-06-15", "name": "加息75bp", "type": "加息周期"},
]


def load_csv(filename):
    path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
    return df


def make_history(df, value_col='close', tail=1260):
    """生成趋势数据（最近5年）"""
    rows = df.tail(tail)
    return [{'date': row['date'].strftime('%Y-%m-%d'),
             'value': round(float(row[value_col]), 2)}
            for _, row in rows.iterrows() if pd.notna(row[value_col])]


def calc():
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'crisis_events': CRISIS_EVENTS,
        'dimensions': {},
        'composite_score': 0,
        'composite_level': '',
        'alerts': [],
    }

    scores = {}

    # ═══════ 1. 情绪风险 (VIX) ═══════
    emo = {'name': '🔥 情绪风险', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    vix_df = load_csv('us_vix.csv')
    if not vix_df.empty:
        vix_df['close'] = pd.to_numeric(vix_df['close'], errors='coerce')
        vix_df = vix_df.dropna(subset=['close'])
        latest_vix = float(vix_df.iloc[-1]['close'])
        ma20 = float(vix_df['close'].tail(20).mean())

        emo['items'].append(f"VIX: {latest_vix:.2f} (MA20: {ma20:.2f})")
        emo['trend'] = make_history(vix_df)

        if latest_vix >= 30:
            emo['score'] += 70
            result['alerts'].append(f'🔥 VIX={latest_vix:.1f}，市场极度恐慌')
        elif latest_vix >= 20:
            emo['score'] += 40
        elif latest_vix >= 15:
            emo['score'] += 15

        # VIX急升（1周涨幅）
        if len(vix_df) >= 6:
            week_ago = float(vix_df.iloc[-6]['close'])
            vix_chg = latest_vix - week_ago
            if vix_chg > 10:
                emo['score'] += 30
                result['alerts'].append(f'🔥 VIX一周飙升{vix_chg:.1f}，恐慌急剧升温')
            elif vix_chg > 5:
                emo['score'] += 15

    emo['score'] = min(emo['score'], 100)
    scores['emotion'] = emo['score']
    if emo['score'] >= 60:
        emo['level'] = '🔴'
    elif emo['score'] >= 30:
        emo['level'] = '🟡'
    result['dimensions']['emotion'] = emo

    # ═══════ 2. 技术面 (标普/纳指 vs 200MA) ═══════
    tech = {'name': '📊 技术面', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    for csv_name, label, weight in [('us_sp500.csv', '标普500', 1.0), ('us_nasdaq.csv', '纳指', 0.8)]:
        df = load_csv(csv_name)
        if not df.empty:
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df = df.dropna(subset=['close'])
            df['ma200'] = df['close'].rolling(200).mean()
            df['distance'] = (df['close'] - df['ma200']) / df['ma200'] * 100

            latest_dist = float(df.iloc[-1]['distance']) if pd.notna(df.iloc[-1]['distance']) else None
            latest_price = float(df.iloc[-1]['close'])

            if latest_dist is not None:
                tech['items'].append(f"{label}: {latest_price:.0f} (vs 200MA: {latest_dist:+.1f}%)")

                if csv_name == 'us_sp500.csv':
                    tech['trend'] = make_history(df, 'distance')

                if latest_dist <= -10:
                    tech['score'] += int(50 * weight)
                    result['alerts'].append(f'📊 {label}跌破200MA超10%，技术性熊市')
                elif latest_dist <= -5:
                    tech['score'] += int(30 * weight)
                elif latest_dist <= 0:
                    tech['score'] += int(15 * weight)

    tech['score'] = min(tech['score'], 100)
    scores['technical'] = tech['score']
    if tech['score'] >= 60:
        tech['level'] = '🔴'
    elif tech['score'] >= 30:
        tech['level'] = '🟡'
    result['dimensions']['technical'] = tech

    # ═══════ 3. 跨市场 (黄金/美元/比特币/原油) ═══════
    cross = {'name': '🌍 跨市场', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 黄金
    gold_df = load_csv('us_gold.csv')
    if not gold_df.empty:
        gold_df['close'] = pd.to_numeric(gold_df['close'], errors='coerce')
        gold_df = gold_df.dropna(subset=['close'])
        latest_gold = float(gold_df.iloc[-1]['close'])
        cross['items'].append(f"黄金: ${latest_gold:.0f}")
        cross['trend'] = make_history(gold_df)

        if latest_gold >= 2500:
            cross['score'] += 25
        elif latest_gold >= 2200:
            cross['score'] += 10

    # 美元指数
    dxy_df = load_csv('us_dxy.csv')
    if not dxy_df.empty:
        dxy_df['close'] = pd.to_numeric(dxy_df['close'], errors='coerce')
        dxy_df = dxy_df.dropna(subset=['close'])
        latest_dxy = float(dxy_df.iloc[-1]['close'])
        cross['items'].append(f"美元DXY: {latest_dxy:.2f}")

        if latest_dxy >= 110:
            cross['score'] += 25
            result['alerts'].append(f'🌍 美元指数{latest_dxy:.1f}，强美元压力大')
        elif latest_dxy >= 105:
            cross['score'] += 15

    # 原油
    oil_df = load_csv('us_crude_oil.csv')
    if not oil_df.empty:
        oil_df['close'] = pd.to_numeric(oil_df['close'], errors='coerce')
        oil_df = oil_df.dropna(subset=['close'])
        latest_oil = float(oil_df.iloc[-1]['close'])
        cross['items'].append(f"WTI原油: ${latest_oil:.2f}")

        if latest_oil >= 110:
            cross['score'] += 25
            result['alerts'].append(f'🌍 原油${latest_oil:.0f}，通胀+衰退风险并存')
        elif latest_oil >= 90:
            cross['score'] += 15

    # 比特币
    btc_df = load_csv('us_bitcoin.csv')
    if not btc_df.empty:
        btc_df['close'] = pd.to_numeric(btc_df['close'], errors='coerce')
        btc_df = btc_df.dropna(subset=['close'])
        latest_btc = float(btc_df.iloc[-1]['close'])
        cross['items'].append(f"比特币: ${latest_btc:,.0f}")

        if len(btc_df) >= 6:
            week_ago_btc = float(btc_df.iloc[-6]['close'])
            btc_chg_pct = (latest_btc - week_ago_btc) / week_ago_btc * 100
            if btc_chg_pct <= -20:
                cross['score'] += 25
            elif btc_chg_pct <= -10:
                cross['score'] += 10

    cross['score'] = min(cross['score'], 100)
    scores['crossmarket'] = cross['score']
    if cross['score'] >= 60:
        cross['level'] = '🔴'
    elif cross['score'] >= 30:
        cross['level'] = '🟡'
    result['dimensions']['crossmarket'] = cross

    # ═══════ 4. 流动性 (美债/利差/TED) ═══════
    liq = {'name': '💧 流动性', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 10Y美债
    tnx_df = load_csv('us_10y_treasury.csv')
    if not tnx_df.empty:
        tnx_df['close'] = pd.to_numeric(tnx_df['close'], errors='coerce')
        tnx_df = tnx_df.dropna(subset=['close'])
        latest_tnx = float(tnx_df.iloc[-1]['close'])
        liq['items'].append(f"10Y美债: {latest_tnx:.2f}%")
        liq['trend'] = make_history(tnx_df)

        if latest_tnx >= 5.5:
            liq['score'] += 40
            result['alerts'].append(f'💧 10Y美债{latest_tnx:.2f}%，融资成本高企')
        elif latest_tnx >= 4.5:
            liq['score'] += 20

    # 10Y-2Y利差
    spread_df = load_csv('us_10y2y_spread.csv')
    if not spread_df.empty:
        val_col = 'value' if 'value' in spread_df.columns else 'close'
        spread_df[val_col] = pd.to_numeric(spread_df[val_col], errors='coerce')
        spread_df = spread_df.dropna(subset=[val_col])
        if not spread_df.empty:
            latest_spread = float(spread_df.iloc[-1][val_col])
            liq['items'].append(f"10Y-2Y利差: {latest_spread:+.2f}%")

            if latest_spread <= -1.0:
                liq['score'] += 30
                result['alerts'].append(f'💧 收益率曲线深度倒挂{latest_spread:+.2f}%')
            elif latest_spread <= -0.5:
                liq['score'] += 15
            elif latest_spread <= 0:
                liq['score'] += 5

    # TED利差
    ted_df = load_csv('us_ted_spread.csv')
    if not ted_df.empty:
        val_col = 'value' if 'value' in ted_df.columns else 'close'
        ted_df[val_col] = pd.to_numeric(ted_df[val_col], errors='coerce')
        ted_df = ted_df.dropna(subset=[val_col])
        if not ted_df.empty:
            latest_ted = float(ted_df.iloc[-1][val_col])
            liq['items'].append(f"TED利差: {latest_ted:.3f}")

            if latest_ted >= 1.0:
                liq['score'] += 30
                result['alerts'].append(f'💧 TED利差{latest_ted:.2f}，银行间信用风险升高')
            elif latest_ted >= 0.5:
                liq['score'] += 15

    liq['score'] = min(liq['score'], 100)
    scores['liquidity'] = liq['score']
    if liq['score'] >= 60:
        liq['level'] = '🔴'
    elif liq['score'] >= 30:
        liq['level'] = '🟡'
    result['dimensions']['liquidity'] = liq

    # ═══════ 5. 基本面 (失业率/ISM PMI) ═══════
    fund = {'name': '📉 基本面', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 失业率
    unemp_df = load_csv('us_unemployment.csv')
    if not unemp_df.empty:
        val_col = 'value' if 'value' in unemp_df.columns else 'close'
        unemp_df[val_col] = pd.to_numeric(unemp_df[val_col], errors='coerce')
        unemp_df = unemp_df.dropna(subset=[val_col])
        if not unemp_df.empty:
            latest_unemp = float(unemp_df.iloc[-1][val_col])
            fund['items'].append(f"失业率: {latest_unemp:.1f}%")
            fund['trend'] = make_history(unemp_df, val_col)

            if latest_unemp >= 7.0:
                fund['score'] += 50
                result['alerts'].append(f'📉 失业率{latest_unemp:.1f}%，衰退信号明确')
            elif latest_unemp >= 5.5:
                fund['score'] += 30
            elif latest_unemp >= 4.5:
                fund['score'] += 15

    # ISM PMI
    ism_df = load_csv('us_ism_pmi.csv')
    if not ism_df.empty:
        val_col = 'value' if 'value' in ism_df.columns else 'close'
        ism_df[val_col] = pd.to_numeric(ism_df[val_col], errors='coerce')
        ism_df = ism_df.dropna(subset=[val_col])
        if not ism_df.empty:
            latest_ism = float(ism_df.iloc[-1][val_col])
            fund['items'].append(f"ISM PMI: {latest_ism:.1f}")

            if latest_ism <= 45:
                fund['score'] += 50
                result['alerts'].append(f'📉 ISM PMI={latest_ism:.1f}，制造业深度萎缩')
            elif latest_ism <= 48:
                fund['score'] += 30
            elif latest_ism <= 50:
                fund['score'] += 15

    fund['score'] = min(fund['score'], 100)
    scores['fundamental'] = fund['score']
    if fund['score'] >= 60:
        fund['level'] = '🔴'
    elif fund['score'] >= 30:
        fund['level'] = '🟡'
    result['dimensions']['fundamental'] = fund

    # ═══════ 综合评分 ═══════
    weights = {
        'emotion': 0.20,
        'technical': 0.25,
        'crossmarket': 0.15,
        'liquidity': 0.20,
        'fundamental': 0.20,
    }
    total = sum(scores.get(k, 0) * w for k, w in weights.items())
    result['composite_score'] = round(total, 1)

    if total >= 60:
        result['composite_level'] = '高风险 🔴'
    elif total >= 40:
        result['composite_level'] = '中高风险 🟠'
    elif total >= 20:
        result['composite_level'] = '中低风险 🟡'
    else:
        result['composite_level'] = '低风险 🟢'

    if not result['alerts']:
        result['alerts'] = ['当前无极端风险信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {OUTPUT_JSON}")
    print(f"综合风险: {result['composite_score']:.1f}/100 - {result['composite_level']}")
    for a in result['alerts']:
        print(f"  ⚠️ {a}")


if __name__ == '__main__':
    calc()
