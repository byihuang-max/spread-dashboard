#!/usr/bin/env python3
"""
拥挤度监控 - 计算 & 生成JSON
1. 三路资金方向一致性（北向/ETF/两融）
2. 行业资金流向热力图
3. 拥挤度综合信号
"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'crowding.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'])
    return df


def calc_direction_signal(series, window=5):
    """计算资金方向: MA5 > MA20 为正，否则为负"""
    ma5 = series.rolling(window).mean()
    ma20 = series.rolling(20).mean()
    return np.where(ma5 > ma20, 1, -1)


def calc_crowding():
    north = load_csv('northbound.csv')
    etf = load_csv('etf_flow.csv')
    margin = load_csv('margin.csv')
    industry = load_csv('industry_flow.csv')
    
    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'three_flows': {},
        'direction_chart': [],
        'industry_heatmap': [],
        'crowding_signal': {},
    }
    
    # ── 合并三路数据 ──
    # 找共同日期范围
    dfs = []
    if not north.empty:
        dfs.append(north.set_index('trade_date')[['north_net']])
    if not etf.empty:
        dfs.append(etf.set_index('trade_date')[['etf_share_chg']])
    if not margin.empty:
        dfs.append(margin.set_index('trade_date')[['margin_chg', 'margin_balance']])
    
    if not dfs:
        print("无数据可计算!")
        with open(OUTPUT_JSON, 'w') as f:
            json.dump(result, f, ensure_ascii=False)
        return
    
    merged = pd.concat(dfs, axis=1).sort_index()
    merged = merged.dropna(subset=[c for c in ['north_net'] if c in merged.columns])
    
    # 最近60天用于图表
    recent = merged.tail(60).copy()
    
    # ── 三路方向一致性 ──
    directions = {}
    labels = {'north_net': '北向资金', 'etf_share_chg': 'ETF净流入', 'margin_chg': '两融变化'}
    
    for col, label in labels.items():
        if col not in recent.columns:
            continue
        s = recent[col].fillna(0)
        ma5 = s.rolling(5, min_periods=1).mean()
        ma20 = s.rolling(20, min_periods=5).mean()
        latest_dir = 'inflow' if ma5.iloc[-1] > ma20.iloc[-1] else 'outflow'
        directions[col] = {
            'name': label,
            'direction': latest_dir,
            'latest': round(float(s.iloc[-1]), 2),
            'ma5': round(float(ma5.iloc[-1]), 2),
            'ma20': round(float(ma20.iloc[-1]), 2),
        }
    
    # 一致性判断
    dir_values = [v['direction'] for v in directions.values()]
    if len(set(dir_values)) == 1 and len(dir_values) >= 2:
        consensus = dir_values[0]
        consensus_label = '三路共振流入 🟢' if consensus == 'inflow' else '三路共振流出 🔴'
    elif len(dir_values) >= 2:
        inflow_count = dir_values.count('inflow')
        if inflow_count >= 2:
            consensus_label = '偏多分歧 🟡'
        else:
            consensus_label = '偏空分歧 🟡'
    else:
        consensus_label = '数据不足'
    
    result['three_flows'] = {
        'details': directions,
        'consensus': consensus_label,
    }
    
    # ── 图表数据（60天时序）──
    chart_data = []
    for idx, row in recent.iterrows():
        d = {'date': idx.strftime('%m-%d')}
        for col in ['north_net', 'etf_share_chg', 'margin_chg']:
            if col in row:
                d[col] = round(float(row[col]), 2) if pd.notna(row[col]) else None
        chart_data.append(d)
    result['direction_chart'] = chart_data
    
    # ── 累计净流入（20日滚动）──
    rolling_data = []
    for col, label in labels.items():
        if col not in merged.columns:
            continue
        s = merged[col].fillna(0)
        cum20 = s.rolling(20, min_periods=1).sum()
        recent_cum = cum20.tail(60)
        series = []
        for idx, val in recent_cum.items():
            series.append({
                'date': idx.strftime('%m-%d'),
                'value': round(float(val), 2),
            })
        rolling_data.append({'name': label, 'key': col, 'data': series})
    result['rolling_cum'] = rolling_data
    
    # ── 行业热力图（最近5日净流入排名）──
    if not industry.empty:
        industry['trade_date'] = pd.to_datetime(industry['trade_date'])
        # net_amount 单位万元 -> 亿
        if 'net_amount' in industry.columns:
            industry['net_amount'] = industry['net_amount'].astype(float)
            # 按行业汇总最近5日
            ind_sum = industry.groupby('name')['net_amount'].sum().reset_index()
            ind_sum.columns = ['industry', 'net_5d']
            # 转亿（如果单位是万元）
            if ind_sum['net_5d'].abs().max() > 1e6:
                ind_sum['net_5d'] = ind_sum['net_5d'] / 1e4
            elif ind_sum['net_5d'].abs().max() > 1e3:
                ind_sum['net_5d'] = ind_sum['net_5d'] / 1e4
            ind_sum = ind_sum.sort_values('net_5d', ascending=False)
            
            # 每日数据（用于热力图）
            daily_ind = []
            for td in sorted(industry['trade_date'].unique()):
                day_data = industry[industry['trade_date'] == td]
                for _, row in day_data.iterrows():
                    val = float(row['net_amount'])
                    if abs(val) > 1e6:
                        val = val / 1e4
                    elif abs(val) > 1e3:
                        val = val / 1e4
                    daily_ind.append({
                        'date': pd.Timestamp(td).strftime('%m-%d'),
                        'industry': str(row['name']),
                        'net': round(val, 2),
                    })
            
            result['industry_heatmap'] = {
                'summary': [{'industry': r['industry'], 'net_5d': round(r['net_5d'], 2)} 
                           for _, r in ind_sum.iterrows()],
                'daily': daily_ind,
            }
    
    # ── 拥挤度综合信号 ──
    signals = []
    
    # 1. 三路共振
    if '共振' in consensus_label:
        signals.append(consensus_label)
    
    # 2. 北向极值（20日内最大/最小）
    if 'north_net' in merged.columns:
        n20 = merged['north_net'].tail(20)
        latest_n = n20.iloc[-1] if len(n20) > 0 else 0
        pct = n20.rank(pct=True).iloc[-1] if len(n20) > 0 else 0.5
        if pct > 0.9:
            signals.append(f'北向单日极端流入({latest_n:.1f}亿) ⚠️')
        elif pct < 0.1:
            signals.append(f'北向单日极端流出({latest_n:.1f}亿) ⚠️')
    
    # 3. 两融余额高位
    if 'margin_balance' in merged.columns:
        mb = merged['margin_balance'].dropna()
        if len(mb) > 60:
            pct60 = (mb.iloc[-1] - mb.tail(60).min()) / (mb.tail(60).max() - mb.tail(60).min() + 1e-9)
            if pct60 > 0.9:
                signals.append(f'两融余额60日高位({mb.iloc[-1]:.0f}亿) 🔴')
            elif pct60 < 0.1:
                signals.append(f'两融余额60日低位({mb.iloc[-1]:.0f}亿) 🟢')
    
    result['crowding_signal'] = {
        'signals': signals if signals else ['当前无极端信号 ✅'],
        'consensus': consensus_label,
    }
    
    # ── 两融余额趋势 ──
    if 'margin_balance' in merged.columns:
        mb_recent = merged['margin_balance'].dropna().tail(60)
        result['margin_trend'] = [
            {'date': idx.strftime('%m-%d'), 'balance': round(float(val), 0)}
            for idx, val in mb_recent.items()
        ]
    
    # 保存
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    print(f"信号: {consensus_label}")
    if signals:
        for s in signals:
            print(f"  - {s}")


if __name__ == '__main__':
    calc_crowding()
