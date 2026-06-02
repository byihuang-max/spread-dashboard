#!/usr/bin/env python3
"""
拥挤度监控 — 计算层

三路资金方向（南向/ETF/两融）+ 北向活跃度 + 申万行业三维拥挤度

2024年改革后北向不再披露净买入，只有成交额，因此：
- 北向: 作为"活跃度"指标（成交额/MA20），不参与方向共振
- 南向: 累计值 diff 后得到日净流入，参与方向判断
- ETF/两融: 不变
"""
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
    south = load_csv('southbound.csv')
    etf = load_csv('etf_flow.csv')
    margin = load_csv('margin.csv')
    sw = load_csv('sw_daily.csv')
    ind_etf = load_csv('industry_etf.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'data_dates': {},
        'three_flows': {},
        'north_activity': {},
        'direction_chart': [],
        'rolling_cum': [],
        'industry_heatmap': [],
        'crowding_signal': {},
        'margin_trend': [],
    }

    # ── 数据日期 ──
    if not north.empty:
        result['data_dates']['northbound'] = north['trade_date'].max().strftime('%Y-%m-%d')
    if not south.empty:
        result['data_dates']['southbound'] = south['trade_date'].max().strftime('%Y-%m-%d')
    if not etf.empty:
        result['data_dates']['etf'] = etf['trade_date'].max().strftime('%Y-%m-%d')
    if not margin.empty:
        result['data_dates']['margin'] = margin['trade_date'].max().strftime('%Y-%m-%d')
    if not sw.empty:
        result['data_dates']['industry'] = sw['trade_date'].max().strftime('%Y-%m-%d')

    # ── 北向活跃度（独立指标，不参与方向共振）──
    if not north.empty and 'north_turnover' in north.columns:
        nt = pd.to_numeric(north.set_index('trade_date')['north_turnover'], errors='coerce').dropna()
        if len(nt) >= 20:
            ma20 = nt.rolling(20, min_periods=10).mean()
            latest_turnover = float(nt.iloc[-1])
            latest_ma20 = float(ma20.iloc[-1])
            activity_ratio = latest_turnover / latest_ma20 if latest_ma20 > 0 else 1.0
            if activity_ratio > 1.3:
                activity_label = '活跃'
            elif activity_ratio < 0.7:
                activity_label = '低迷'
            else:
                activity_label = '正常'
            result['north_activity'] = {
                'latest': round(latest_turnover, 1),
                'ma20': round(latest_ma20, 1),
                'ratio': round(activity_ratio, 2),
                'label': activity_label,
            }

    # ── 三路方向合成（南向 + ETF + 两融）──
    dfs = []
    if not south.empty and 'south_net' in south.columns:
        dfs.append(south.set_index('trade_date')[['south_net']])
    if not north.empty and 'north_turnover' in north.columns:
        dfs.append(north.set_index('trade_date')[['north_turnover']])
    if not etf.empty:
        dfs.append(etf.set_index('trade_date')[['etf_share_chg']])
    if not margin.empty:
        dfs.append(margin.set_index('trade_date')[['margin_chg', 'margin_balance']])

    consensus_label = '数据不足'
    if dfs:
        merged = pd.concat(dfs, axis=1, sort=True).sort_index()
        recent = merged.tail(60).copy()
        full = merged.copy()  # 全量数据用于图表

        # 方向判断（只对有方向意义的指标，用最近60日）
        directions = {}
        direction_cols = {
            'south_net': '南向资金',
            'etf_share_chg': 'ETF份额变化',
            'margin_chg': '两融变化',
        }
        for col, label in direction_cols.items():
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
        if len(dir_values) >= 2 and len(set(dir_values)) == 1:
            consensus = dir_values[0]
            consensus_label = '三路共振流入' if consensus == 'inflow' else '三路共振流出'
        elif len(dir_values) >= 2:
            inflow_count = dir_values.count('inflow')
            outflow_count = dir_values.count('outflow')
            consensus_label = '偏多分歧' if inflow_count >= outflow_count else '偏空分歧'

        result['three_flows'] = {'details': directions, 'consensus': consensus_label}

        # ── 每日变化图表数据（全量，前端控制窗口）──
        chart_data = []
        for idx, row in full.iterrows():
            d = {'date': idx.strftime('%Y-%m-%d')}
            for col in ['south_net', 'north_turnover', 'etf_share_chg', 'margin_chg']:
                if col in row and pd.notna(row[col]):
                    d[col] = round(float(row[col]), 2)
                else:
                    d[col] = None
            chart_data.append(d)
        result['direction_chart'] = chart_data

        # ── 20日滚动累计（全量）──
        rolling_labels = {
            'south_net': '南向资金',
            'etf_share_chg': 'ETF份额变化',
            'margin_chg': '两融变化',
        }
        rolling_data = []
        for col, label in rolling_labels.items():
            if col not in merged.columns:
                continue
            s = pd.to_numeric(merged[col], errors='coerce').fillna(0)
            cum20 = s.rolling(20, min_periods=1).sum()
            rolling_data.append({
                'name': label,
                'key': col,
                'data': [{'date': idx.strftime('%Y-%m-%d'), 'value': round(float(val), 2)} for idx, val in cum20.items()]
            })
        result['rolling_cum'] = rolling_data

        # ── 两融余额趋势（全量）──
        if 'margin_balance' in merged.columns:
            mb_all = pd.to_numeric(merged['margin_balance'], errors='coerce').dropna()
            result['margin_trend'] = [
                {'date': idx.strftime('%Y-%m-%d'), 'balance': round(float(val), 0)}
                for idx, val in mb_all.items()
            ]

    # ── 行业三维热力图（仅申万一级行业）──
    SW_LEVEL1 = {'农林牧渔','基础化工','钢铁','有色金属','电子','汽车','家用电器',
        '食品饮料','纺织服饰','轻工制造','医药生物','公用事业','交通运输',
        '房地产','商贸零售','社会服务','银行','非银金融','综合','建筑材料',
        '建筑装饰','电力设备','国防军工','计算机','传媒','通信','煤炭',
        '石油石化','环保','美容护理','机械设备'}
    if not sw.empty:
        sw = sw[sw['name'].isin(SW_LEVEL1)].copy()
        sw['pct_change'] = pd.to_numeric(sw['pct_change'], errors='coerce')
        sw['amount'] = pd.to_numeric(sw['amount'], errors='coerce')
        dates_sorted = sorted(sw['trade_date'].unique())
        last5 = dates_sorted[-5:] if len(dates_sorted) >= 5 else dates_sorted

        etf_5d_chg = {}
        if not ind_etf.empty:
            # 优先用 flow_amt(份额变化×净值=资金净流入万元)；老数据无该列时退回 share_chg
            flow_col = 'flow_amt' if 'flow_amt' in ind_etf.columns else 'share_chg'
            ind_etf[flow_col] = pd.to_numeric(ind_etf[flow_col], errors='coerce')
            etf_last5 = ind_etf[ind_etf['trade_date'].isin(last5)]
            etf_5d_chg = etf_last5.groupby('industry')[flow_col].sum(min_count=1).to_dict()

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
                tags.append('拥挤')
            elif crowd_label == 'cold':
                tags.append('冷清')
            if etf_dir == 'inflow':
                tags.append('▲ETF流入')
            elif etf_dir == 'outflow':
                tags.append('▼ETF流出')

            if cum_ret > 3 and crowd_label == 'hot' and etf_dir == 'outflow':
                signal = '⚠ 追高风险'
            elif cum_ret > 2 and etf_dir == 'inflow' and crowd_label in ('normal', 'warm'):
                signal = '资金确认'
            elif cum_ret < -2 and crowd_label == 'cold':
                signal = '超跌冷门'
            elif cum_ret < -2 and etf_dir == 'inflow':
                signal = '逆势吸筹'
            else:
                signal = None

            # 价 vs 资金 背离判定（默认只显示背离行业，其余折叠）
            # 涨+ETF流出=热闹出货(追高险)；跌+ETF流入=低迷吸筹(埋伏)
            divergence = None
            if etf_dir is not None:
                if cum_ret > 0 and etf_dir == 'outflow':
                    divergence = 'distribution'   # 价涨钱撤
                elif cum_ret < 0 and etf_dir == 'inflow':
                    divergence = 'accumulation'   # 价跌钱进

            industries.append({
                'name': name,
                'pct_5d': round(float(cum_ret), 2),
                'crowding_ratio': round(float(crowding_ratio), 2),
                'crowd_label': crowd_label,
                'etf_chg': etf_chg_val,
                'etf_dir': etf_dir,
                'divergence': divergence,
                'tags': tags,
                'signal': signal,
                'amount_latest': round(float(latest_amt), 0),
            })

        industries.sort(key=lambda x: x['pct_5d'], reverse=True)
        result['industry_heatmap'] = industries

    # ── 综合信号 ──
    signals = []
    if '共振' in consensus_label:
        signals.append(consensus_label)

    # 北向活跃度异常
    na = result.get('north_activity', {})
    if na.get('ratio', 1.0) > 1.5:
        signals.append(f"北向成交异常活跃({na['latest']:.0f}亿, 量比{na['ratio']:.2f})")
    elif na.get('ratio', 1.0) < 0.6:
        signals.append(f"北向成交异常低迷({na['latest']:.0f}亿, 量比{na['ratio']:.2f})")

    # 南向极端
    if not south.empty and 'south_net' in south.columns:
        sn = pd.to_numeric(south.set_index('trade_date')['south_net'], errors='coerce').dropna()
        if len(sn) >= 20:
            s20 = sn.tail(20)
            pct = s20.rank(pct=True).iloc[-1]
            latest_s = float(s20.iloc[-1])
            if pct > 0.9:
                signals.append(f'南向单日高位({latest_s:.1f}亿)')
            elif pct < 0.1:
                signals.append(f'南向单日低位({latest_s:.1f}亿)')

    # 两融极端
    if not margin.empty:
        mb = pd.to_numeric(margin['margin_balance'], errors='coerce').dropna()
        if len(mb) > 60:
            tail = mb.tail(60)
            pct60 = (tail.iloc[-1] - tail.min()) / (tail.max() - tail.min() + 1e-9)
            if pct60 > 0.9:
                signals.append(f'两融余额60日高位({tail.iloc[-1]:.0f}亿)')
            elif pct60 < 0.1:
                signals.append(f'两融余额60日低位({tail.iloc[-1]:.0f}亿)')

    # 行业信号
    for i in result.get('industry_heatmap', []):
        if i.get('signal'):
            signals.append(f"{i['name']} {i['signal']}({i['pct_5d']:+.1f}%)")

    result['crowding_signal'] = {
        'signals': signals if signals else ['当前无极端信号'],
        'consensus': consensus_label,
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'输出: {OUTPUT_JSON}')
    print(f"共识: {result['crowding_signal']['consensus']}")
    if na:
        print(f"北向活跃度: {na.get('label','')} (量比 {na.get('ratio','')})")


if __name__ == '__main__':
    calc_crowding()
