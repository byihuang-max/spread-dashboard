#!/usr/bin/env python3
import json
import os

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'crowding.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'].astype(str).str.strip(), format='%Y%m%d')
    return df


def calc_crowding():
    north = load_csv('northbound.csv')
    etf = load_csv('etf_flow.csv')
    margin = load_csv('margin.csv')
    sw = load_csv('sw_daily.csv')
    ind_etf = load_csv('industry_etf.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'data_dates': {},
        'three_flows': {},
        'direction_chart': [],
        'rolling_cum': [],
        'industry_heatmap': [],
        'crowding_signal': {},
        'margin_trend': [],
    }

    if not north.empty:
        result['data_dates']['northbound'] = north['trade_date'].max().strftime('%Y-%m-%d')
    if not etf.empty:
        result['data_dates']['etf'] = etf['trade_date'].max().strftime('%Y-%m-%d')
    if not margin.empty:
        result['data_dates']['margin'] = margin['trade_date'].max().strftime('%Y-%m-%d')
    if not sw.empty:
        result['data_dates']['industry'] = sw['trade_date'].max().strftime('%Y-%m-%d')

    dfs = []
    if not north.empty:
        cols = [c for c in ['north_net', 'south_net'] if c in north.columns]
        dfs.append(north.set_index('trade_date')[cols])
    if not etf.empty:
        dfs.append(etf.set_index('trade_date')[['etf_share_chg']])
    if not margin.empty:
        dfs.append(margin.set_index('trade_date')[['margin_chg', 'margin_balance']])

    consensus_label = '数据不足'
    if dfs:
        merged = pd.concat(dfs, axis=1, sort=True).sort_index()
        recent = merged.tail(60).copy()

        directions = {}
        labels = {
            'north_net': '北向资金',
            'south_net': '南向资金',
            'etf_share_chg': 'ETF份额变化',
            'margin_chg': '两融变化',
        }
        for col, label in labels.items():
            if col not in recent.columns:
                continue
            s = pd.to_numeric(recent[col], errors='coerce')
            valid = s.dropna()
            if valid.empty:
                continue
            ma5 = valid.rolling(5, min_periods=1).mean()
            ma20 = valid.rolling(20, min_periods=5).mean()
            latest_dir = 'inflow' if ma5.iloc[-1] > ma20.iloc[-1] else 'outflow'
            directions[col] = {
                'name': label,
                'direction': latest_dir,
                'latest': round(float(valid.iloc[-1]), 2),
                'ma5': round(float(ma5.iloc[-1]), 2),
                'ma20': round(float(ma20.iloc[-1]), 2) if pd.notna(ma20.iloc[-1]) else None,
            }

        dir_values = [v['direction'] for v in directions.values()]
        if len(dir_values) >= 3 and len(set(dir_values)) == 1:
            consensus = dir_values[0]
            consensus_label = '四路共振流入 🟢' if consensus == 'inflow' else '四路共振流出 🔴'
        elif len(dir_values) >= 3:
            inflow_count = dir_values.count('inflow')
            outflow_count = dir_values.count('outflow')
            consensus_label = '偏多分歧 🟡' if inflow_count >= outflow_count else '偏空分歧 🟡'

        result['three_flows'] = {'details': directions, 'consensus': consensus_label}

        chart_data = []
        for idx, row in recent.iterrows():
            d = {'date': idx.strftime('%m-%d')}
            for col in ['north_net', 'south_net', 'etf_share_chg', 'margin_chg']:
                if col in row and pd.notna(row[col]):
                    d[col] = round(float(row[col]), 2)
                else:
                    d[col] = None
            chart_data.append(d)
        result['direction_chart'] = chart_data

        rolling_data = []
        for col, label in labels.items():
            if col not in merged.columns:
                continue
            s = pd.to_numeric(merged[col], errors='coerce').fillna(0)
            cum20 = s.rolling(20, min_periods=1).sum()
            recent_cum = cum20.tail(60)
            rolling_data.append({
                'name': label,
                'key': col,
                'data': [{'date': idx.strftime('%m-%d'), 'value': round(float(val), 2)} for idx, val in recent_cum.items()]
            })
        result['rolling_cum'] = rolling_data

        if 'margin_balance' in merged.columns:
            mb_recent = pd.to_numeric(merged['margin_balance'], errors='coerce').dropna().tail(60)
            result['margin_trend'] = [
                {'date': idx.strftime('%m-%d'), 'balance': round(float(val), 0)}
                for idx, val in mb_recent.items()
            ]

    if not sw.empty:
        sw['pct_change'] = pd.to_numeric(sw['pct_change'], errors='coerce')
        sw['amount'] = pd.to_numeric(sw['amount'], errors='coerce')
        dates_sorted = sorted(sw['trade_date'].unique())
        last5 = dates_sorted[-5:] if len(dates_sorted) >= 5 else dates_sorted

        etf_5d_chg = {}
        if not ind_etf.empty:
            ind_etf['share_chg'] = pd.to_numeric(ind_etf['share_chg'], errors='coerce')
            etf_last5 = ind_etf[ind_etf['trade_date'].isin(last5)]
            etf_5d_chg = etf_last5.groupby('industry')['share_chg'].sum(min_count=1).to_dict()

        industries = []
        for name, grp in sw.groupby('name'):
            grp = grp.sort_values('trade_date')
            grp5 = grp[grp['trade_date'].isin(last5)]
            if grp5.empty:
                continue
            cum_ret = ((1 + grp5['pct_change'].fillna(0) / 100).prod() - 1) * 100

            amounts = grp['amount'].values
            if len(amounts) >= 20:
                ma20_amt = np.mean(amounts[-20:])
                latest_amt = amounts[-1]
                crowding_ratio = latest_amt / ma20_amt if ma20_amt > 0 else 1.0
            elif len(amounts) >= 5:
                ma_amt = np.mean(amounts)
                latest_amt = amounts[-1]
                crowding_ratio = latest_amt / ma_amt if ma_amt > 0 else 1.0
            else:
                latest_amt = amounts[-1] if len(amounts) else 0
                crowding_ratio = 1.0

            if crowding_ratio > 1.5:
                crowd_label = 'hot'
            elif crowding_ratio > 1.2:
                crowd_label = 'warm'
            elif crowding_ratio < 0.7:
                crowd_label = 'cold'
            elif crowding_ratio < 0.85:
                crowd_label = 'cool'
            else:
                crowd_label = 'normal'

            etf_chg = etf_5d_chg.get(name)
            if etf_chg is not None and pd.notna(etf_chg):
                etf_chg_val = round(float(etf_chg), 2)
                etf_dir = 'inflow' if etf_chg > 0 else 'outflow'
            else:
                etf_chg_val = None
                etf_dir = None

            tags = []
            if crowd_label == 'hot':
                tags.append('🔥拥挤')
            elif crowd_label == 'cold':
                tags.append('❄️冷清')
            if etf_dir == 'inflow':
                tags.append('▲ETF流入')
            elif etf_dir == 'outflow':
                tags.append('▼ETF流出')

            if cum_ret > 3 and crowd_label == 'hot' and etf_dir == 'outflow':
                signal = '⚠️ 追高风险'
            elif cum_ret > 2 and etf_dir == 'inflow' and crowd_label in ('normal', 'warm'):
                signal = '✅ 资金确认'
            elif cum_ret < -2 and crowd_label == 'cold':
                signal = '👀 超跌冷门'
            elif cum_ret < -2 and etf_dir == 'inflow':
                signal = '🔄 逆势吸筹'
            else:
                signal = None

            industries.append({
                'name': name,
                'pct_5d': round(float(cum_ret), 2),
                'crowding_ratio': round(float(crowding_ratio), 2),
                'crowd_label': crowd_label,
                'etf_chg': etf_chg_val,
                'etf_dir': etf_dir,
                'tags': tags,
                'signal': signal,
                'amount_latest': round(float(latest_amt), 0),
            })

        industries.sort(key=lambda x: x['pct_5d'], reverse=True)
        result['industry_heatmap'] = industries

    signals = []
    if '共振' in consensus_label:
        signals.append(consensus_label)

    if not north.empty and 'north_net' in north.columns:
        n20 = north['north_net'].tail(20)
        if len(n20) > 0:
            latest_n = n20.iloc[-1]
            pct = n20.rank(pct=True).iloc[-1]
            if pct > 0.9:
                signals.append(f'北向单日高位({latest_n:.1f}亿) ⚠️')
            elif pct < 0.1:
                signals.append(f'北向单日低位({latest_n:.1f}亿) ⚠️')

    if not north.empty and 'south_net' in north.columns:
        s20 = north['south_net'].tail(20)
        if len(s20) > 0:
            latest_s = s20.iloc[-1]
            pct = s20.rank(pct=True).iloc[-1]
            if pct > 0.9:
                signals.append(f'南向单日高位({latest_s:.1f}亿) ⚠️')
            elif pct < 0.1:
                signals.append(f'南向单日低位({latest_s:.1f}亿) ⚠️')

    if not margin.empty:
        mb = pd.to_numeric(margin['margin_balance'], errors='coerce').dropna()
        if len(mb) > 60:
            tail = mb.tail(60)
            pct60 = (tail.iloc[-1] - tail.min()) / (tail.max() - tail.min() + 1e-9)
            if pct60 > 0.9:
                signals.append(f'两融余额60日高位({tail.iloc[-1]:.0f}亿) 🔴')
            elif pct60 < 0.1:
                signals.append(f'两融余额60日低位({tail.iloc[-1]:.0f}亿) 🟢')

    for i in result.get('industry_heatmap', []):
        if i.get('signal'):
            signals.append(f"{i['name']} {i['signal']}({i['pct_5d']:+.1f}%)")

    result['crowding_signal'] = {
        'signals': signals if signals else ['当前无极端信号 ✅'],
        'consensus': consensus_label,
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'输出: {OUTPUT_JSON}')
    print(f"共识: {result['crowding_signal']['consensus']}")


if __name__ == '__main__':
    calc_crowding()
