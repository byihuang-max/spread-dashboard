#!/usr/bin/env python3
"""
拥挤度监控 - 计算 & 生成JSON
每个申万一级行业三维评估：
  1. 价格动量（5日累计涨跌幅）
  2. 资金验证（行业ETF份额5日变化）
  3. 拥挤度（成交额/MA20偏离度）
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
        # 处理纯数字日期 (20260227) 和字符串日期 (2026-02-27) 混合情况
        # 先统一转字符串，再用 mixed 格式解析
        df['trade_date'] = df['trade_date'].astype(str).str.strip()
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='mixed', dayfirst=False)
    return df


def calc_crowding():
    north = load_csv('northbound.csv')
    etf = load_csv('etf_flow.csv')
    margin = load_csv('margin.csv')
    sw = load_csv('sw_daily.csv')
    ind_etf = load_csv('industry_etf.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'three_flows': {},
        'direction_chart': [],
        'rolling_cum': [],
        'industry_heatmap': [],
        'crowding_signal': {},
        'margin_trend': [],
    }

    # ══════════════════════════════════════════
    # 三路资金（和之前一样）
    # ══════════════════════════════════════════
    dfs = []
    if not north.empty:
        dfs.append(north.set_index('trade_date')[['north_net']])
    if not etf.empty:
        dfs.append(etf.set_index('trade_date')[['etf_share_chg']])
    if not margin.empty:
        dfs.append(margin.set_index('trade_date')[['margin_chg', 'margin_balance']])

    if dfs:
        merged = pd.concat(dfs, axis=1, sort=True).sort_index()
        merged = merged.dropna(subset=[c for c in ['north_net'] if c in merged.columns])
        recent = merged.tail(60).copy()

        # 方向判断
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

        dir_values = [v['direction'] for v in directions.values()]
        if len(set(dir_values)) == 1 and len(dir_values) >= 2:
            consensus = dir_values[0]
            consensus_label = '三路共振流入 🟢' if consensus == 'inflow' else '三路共振流出 🔴'
        elif len(dir_values) >= 2:
            consensus_label = '偏多分歧 🟡' if dir_values.count('inflow') >= 2 else '偏空分歧 🟡'
        else:
            consensus_label = '数据不足'

        result['three_flows'] = {'details': directions, 'consensus': consensus_label}

        # 图表数据
        chart_data = []
        for idx, row in recent.iterrows():
            d = {'date': idx.strftime('%m-%d')}
            for col in ['north_net', 'etf_share_chg', 'margin_chg']:
                if col in row:
                    d[col] = round(float(row[col]), 2) if pd.notna(row[col]) else None
            chart_data.append(d)
        result['direction_chart'] = chart_data

        # 20日滚动累计
        rolling_data = []
        for col, label in labels.items():
            if col not in merged.columns:
                continue
            s = merged[col].fillna(0)
            cum20 = s.rolling(20, min_periods=1).sum()
            recent_cum = cum20.tail(60)
            series = [{'date': idx.strftime('%m-%d'), 'value': round(float(val), 2)}
                      for idx, val in recent_cum.items()]
            rolling_data.append({'name': label, 'key': col, 'data': series})
        result['rolling_cum'] = rolling_data

        # 两融余额趋势
        if 'margin_balance' in merged.columns:
            mb_recent = merged['margin_balance'].dropna().tail(60)
            result['margin_trend'] = [
                {'date': idx.strftime('%m-%d'), 'balance': round(float(val), 0)}
                for idx, val in mb_recent.items()
            ]
    else:
        consensus_label = '数据不足'

    # ══════════════════════════════════════════
    # 行业三维评估
    # ══════════════════════════════════════════
    if not sw.empty:
        sw['pct_change'] = pd.to_numeric(sw['pct_change'], errors='coerce')
        sw['amount'] = pd.to_numeric(sw['amount'], errors='coerce')

        dates_sorted = sorted(sw['trade_date'].unique())
        last5 = dates_sorted[-5:] if len(dates_sorted) >= 5 else dates_sorted

        # ── 行业ETF 5日份额变化 ──
        etf_5d_chg = {}
        if not ind_etf.empty:
            ind_etf['trade_date'] = pd.to_datetime(ind_etf['trade_date'])
            ind_etf['share_chg'] = pd.to_numeric(ind_etf['share_chg'], errors='coerce')
            etf_last5 = ind_etf[ind_etf['trade_date'].isin(last5)]
            etf_5d_chg = etf_last5.groupby('industry')['share_chg'].sum().to_dict()

        # ── 逐行业计算 ──
        industries = []
        for name, grp in sw.groupby('name'):
            grp = grp.sort_values('trade_date')

            # 1. 5日涨跌幅
            grp5 = grp[grp['trade_date'].isin(last5)]
            if grp5.empty:
                continue
            cum_ret = ((1 + grp5['pct_change'].fillna(0) / 100).prod() - 1) * 100

            # 2. 拥挤度：成交额 / MA20
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
                crowding_ratio = 1.0
                latest_amt = amounts[-1] if len(amounts) > 0 else 0

            # 拥挤度标签
            if crowding_ratio > 1.5:
                crowd_label = 'hot'       # 🔥 拥挤
            elif crowding_ratio > 1.2:
                crowd_label = 'warm'      # 偏热
            elif crowding_ratio < 0.7:
                crowd_label = 'cold'      # ❄️ 冷清
            elif crowding_ratio < 0.85:
                crowd_label = 'cool'      # 偏冷
            else:
                crowd_label = 'normal'

            # 3. ETF 资金流向
            etf_chg = etf_5d_chg.get(name, None)
            if etf_chg is not None:
                etf_chg_val = round(float(etf_chg), 2)
                etf_dir = 'inflow' if etf_chg > 0 else 'outflow'
            else:
                etf_chg_val = None
                etf_dir = None

            # 综合标签
            tags = []
            if crowd_label == 'hot':
                tags.append('🔥拥挤')
            elif crowd_label == 'cold':
                tags.append('❄️冷清')
            if etf_dir == 'inflow':
                tags.append('▲ETF流入')
            elif etf_dir == 'outflow':
                tags.append('▼ETF流出')

            # 组合信号
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

    # ══════════════════════════════════════════
    # 拥挤度综合信号
    # ══════════════════════════════════════════
    signals = []
    if 'consensus_label' in dir() and '共振' in consensus_label:
        signals.append(consensus_label)

    if not north.empty:
        n20 = north['north_net'].tail(20)
        if len(n20) > 0:
            latest_n = n20.iloc[-1]
            pct = n20.rank(pct=True).iloc[-1]
            if pct > 0.9:
                signals.append(f'北向单日极端流入({latest_n:.1f}亿) ⚠️')
            elif pct < 0.1:
                signals.append(f'北向单日极端流出({latest_n:.1f}亿) ⚠️')

    if not margin.empty:
        mb = margin['margin_balance'].dropna()
        if len(mb) > 60:
            pct60 = (mb.iloc[-1] - mb.tail(60).min()) / (mb.tail(60).max() - mb.tail(60).min() + 1e-9)
            if pct60 > 0.9:
                signals.append(f'两融余额60日高位({mb.iloc[-1]:.0f}亿) 🔴')
            elif pct60 < 0.1:
                signals.append(f'两融余额60日低位({mb.iloc[-1]:.0f}亿) 🟢')

    # 行业级别信号汇总
    ind_signals = [i for i in result.get('industry_heatmap', []) if i.get('signal')]
    for i in ind_signals:
        signals.append(f"{i['name']} {i['signal']}({i['pct_5d']:+.1f}%)")

    result['crowding_signal'] = {
        'signals': signals if signals else ['当前无极端信号 ✅'],
        'consensus': result.get('three_flows', {}).get('consensus', '数据不足'),
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    print(f"共识: {result['crowding_signal']['consensus']}")
    for s in result['crowding_signal']['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc_crowding()
