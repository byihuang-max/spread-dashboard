#!/usr/bin/env python3
"""
美股风险监控 - 计算+输出JSON
读取CSV数据，计算趋势，标注危机事件
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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
    """加载CSV数据"""
    path = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
    return df


def calc_trend(series, window=20):
    """计算趋势方向"""
    if len(series) < window:
        return "→"
    recent = series.tail(window)
    slope = np.polyfit(range(len(recent)), recent, 1)[0]
    if slope > 0.01:
        return "↗"
    elif slope < -0.01:
        return "↘"
    else:
        return "→"


def calc_level(current, thresholds):
    """判断风险等级"""
    if current >= thresholds.get('danger', float('inf')):
        return "🔴"
    elif current >= thresholds.get('warning', float('inf')):
        return "🟡"
    else:
        return "🟢"


def process_indicator(df, name, category, thresholds, value_col='close', invert=False, note=''):
    """处理单个指标"""
    if df.empty:
        return None
    
    df = df.dropna(subset=[value_col])
    if df.empty:
        return None
    
    current = float(df.iloc[-1][value_col])
    if invert:
        current = -current
    
    # 计算变化
    change_1d = None
    change_1w = None
    change_1m = None
    
    if len(df) >= 2:
        prev_1d = float(df.iloc[-2][value_col])
        change_1d = current - prev_1d
    
    if len(df) >= 6:
        prev_1w = float(df.iloc[-6][value_col])
        change_1w = current - prev_1w
    
    if len(df) >= 22:
        prev_1m = float(df.iloc[-22][value_col])
        change_1m = current - prev_1m
    
    # 趋势
    trend = calc_trend(df[value_col])
    
    # 等级
    level = calc_level(current, thresholds)
    
    # 历史数据（最近5年，约1260个交易日）
    history = []
    for _, row in df.tail(1260).iterrows():
        history.append({
            'date': row['date'].strftime('%Y-%m-%d'),  # 完整年-月-日
            'value': round(float(row[value_col]), 2)
        })
    
    return {
        'name': name,
        'category': category,
        'current': round(current, 2),
        'change_1d': round(change_1d, 2) if change_1d is not None else None,
        'change_1w': round(change_1w, 2) if change_1w is not None else None,
        'change_1m': round(change_1m, 2) if change_1m is not None else None,
        'trend': trend,
        'level': level,
        'thresholds': thresholds,
        'history': history,
        'note': note
    }


def calc():
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'crisis_events': CRISIS_EVENTS,
        'indicators': []
    }
    
    # 1. VIX
    vix_df = load_csv('us_vix.csv')
    vix = process_indicator(
        vix_df, 'VIX 恐慌指数', '情绪',
        {'safe': 15, 'warning': 20, 'danger': 30},
        note='VIX上升=市场恐慌增加。>30=极度恐慌，历史上常伴随崩盘。快速飙升比绝对值更危险。'
    )
    if vix:
        result['indicators'].append(vix)
    
    # 2. 标普500
    sp_df = load_csv('us_sp500.csv')
    if not sp_df.empty:
        sp_df['ma200'] = sp_df['close'].rolling(200).mean()
        sp_df['distance'] = (sp_df['close'] - sp_df['ma200']) / sp_df['ma200'] * 100
        sp = process_indicator(
            sp_df, '标普500 vs 200MA', '技术',
            {'safe': 0, 'warning': -5, 'danger': -10},
            value_col='distance',
            note='跌破200日均线=长期趋势转弱。<-10%=技术性熊市确认。'
        )
        if sp:
            result['indicators'].append(sp)
    
    # 3. 黄金
    gold_df = load_csv('us_gold.csv')
    gold = process_indicator(
        gold_df, '黄金价格', '跨市场',
        {'safe': 2000, 'warning': 2200, 'danger': 2500},
        note='黄金上涨=避险情绪升温。突破新高=对法币/股市信心下降。'
    )
    if gold:
        result['indicators'].append(gold)
    
    # 4. 美元指数
    dxy_df = load_csv('us_dxy.csv')
    dxy = process_indicator(
        dxy_df, '美元指数 DXY', '跨市场',
        {'safe': 100, 'warning': 105, 'danger': 110},
        note='美元飙升=全球避险+新兴市场压力。>110=强美元危机，资本回流美国。'
    )
    if dxy:
        result['indicators'].append(dxy)
    
    # 5. 纳斯达克
    nasdaq_df = load_csv('us_nasdaq.csv')
    if not nasdaq_df.empty:
        nasdaq_df['ma200'] = nasdaq_df['close'].rolling(200).mean()
        nasdaq_df['distance'] = (nasdaq_df['close'] - nasdaq_df['ma200']) / nasdaq_df['ma200'] * 100
        nasdaq = process_indicator(
            nasdaq_df, '纳指 vs 200MA', '技术',
            {'safe': 0, 'warning': -5, 'danger': -10},
            value_col='distance',
            note='科技股趋势指标。跌破200MA=AI/科技泡沫破裂风险。'
        )
        if nasdaq:
            result['indicators'].append(nasdaq)
    
    # 6. 比特币
    btc_df = load_csv('us_bitcoin.csv')
    btc = process_indicator(
        btc_df, '比特币', '跨市场',
        {'safe': 50000, 'warning': 40000, 'danger': 30000},
        invert=True,
        note='风险资产情绪指标。暴跌=流动性紧张+风险偏好下降。'
    )
    if btc:
        result['indicators'].append(btc)
    
    # 7. 原油
    oil_df = load_csv('us_crude_oil.csv')
    oil = process_indicator(
        oil_df, 'WTI原油', '跨市场',
        {'safe': 70, 'warning': 90, 'danger': 110},
        note='通胀+地缘风险指标。>100=通胀压力+经济衰退风险并存。'
    )
    if oil:
        result['indicators'].append(oil)
    
    # 8. 10年期美债收益率
    tnx_df = load_csv('us_10y_treasury.csv')
    tnx = process_indicator(
        tnx_df, '10年期美债收益率', '流动性',
        {'safe': 3.5, 'warning': 4.5, 'danger': 5.5},
        note='融资成本基准。>5%=借贷成本高企，股市估值承压。'
    )
    if tnx:
        result['indicators'].append(tnx)
    
    # 9. 10Y-2Y利差
    spread_df = load_csv('us_10y2y_spread.csv')
    if not spread_df.empty:
        spread = process_indicator(
            spread_df, '10Y-2Y利差', '流动性',
            {'safe': 0, 'warning': -0.5, 'danger': -1.0},
            value_col='value'
        )
        if spread:
            result['indicators'].append(spread)
    
    # 6. TED利差
    ted_df = load_csv('us_ted_spread.csv')
    if not ted_df.empty:
        ted = process_indicator(
            ted_df, 'TED利差', '流动性',
            {'safe': 0.3, 'warning': 0.5, 'danger': 1.0},
            value_col='value'
        )
        if ted:
            result['indicators'].append(ted)
    
    # 7. 失业率
    unemp_df = load_csv('us_unemployment.csv')
    if not unemp_df.empty:
        unemp = process_indicator(
            unemp_df, '失业率', '基本面',
            {'safe': 4.5, 'warning': 5.5, 'danger': 7.0},
            value_col='value'
        )
        if unemp:
            result['indicators'].append(unemp)
    
    # 8. ISM PMI
    ism_df = load_csv('us_ism_pmi.csv')
    if not ism_df.empty:
        ism = process_indicator(
            ism_df, 'ISM PMI', '基本面',
            {'safe': 50, 'warning': 48, 'danger': 45},
            value_col='value',
            invert=True  # PMI越低越危险
        )
        if ism:
            result['indicators'].append(ism)
    
    # 输出JSON
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n输出: {OUTPUT_JSON}")
    print(f"指标数量: {len(result['indicators'])}")
    print(f"危机事件: {len(result['crisis_events'])}")


if __name__ == '__main__':
    calc()
