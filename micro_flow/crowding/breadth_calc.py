#!/usr/bin/env python3
"""
行业拥挤度 — 横截面占比 / 边际加速 / breadth / 量价状态 计算层

在 crowding_calc.py 之后运行：读取已有 crowding.json，补充以下新字段后写回，
不破坏现有的资金流向 / 北向活跃度 / 时序量比逻辑。

新增字段：
- cross_section : 横截面占比 + 占比历史分位（谁占全市场的钱多，集中度处历史什么位置）
- accel_rank    : 拥挤度边际加速 TOP/BOTTOM（占比 5日/20日变化排名，资金涌向哪）
- breadth_l1    : 一级行业涨跌家数比 + 涨跌停（赚钱效应 / 情绪温度）
- breadth_l2    : 二级行业 breadth（下钻用）
- vp_matrix     : 量价状态矩阵（占比分位 × breadth → 四象限状态）
- market_emotion: 全市场涨停/跌停温度
"""
import json
import os

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'crowding.json')
SHARE_SERIES_JSON = os.path.join(SCRIPT_DIR, 'share_series.json')  # 占比时间序列(前端折线图用)

SHARE_HIST_CSV = os.path.join(CACHE_DIR, 'sw_share_hist.csv')
BREADTH_L1_CSV = os.path.join(CACHE_DIR, 'breadth_l1.csv')
BREADTH_L2_CSV = os.path.join(CACHE_DIR, 'breadth_l2.csv')
LIMIT_DETAIL_CSV = os.path.join(CACHE_DIR, 'limit_detail.csv')


def load_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if 'trade_date' in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'].astype(str).str.strip(), format='%Y%m%d')
    return df


def pct_rank(series, value):
    """value 在 series 历史中的分位（0~1）"""
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) < 20 or pd.isna(value):
        return None
    return float((s < value).mean())


def resolve_ref_date(share, bl1):
    """
    统一对齐到三个源都齐全的最近交易日，避免盘中时滞展示半天数据。
    条件：该日同时存在于 占比历史 与 breadth，且 breadth 涨跌停非全 0（limit_list_d 已结算）。
    """
    if share.empty or bl1.empty:
        return None
    share_dates = set(share['trade_date'].unique())
    b = bl1.copy()
    for c in ['limit_up', 'limit_down', 'up', 'down']:
        b[c] = pd.to_numeric(b[c], errors='coerce').fillna(0)
    by_date = b.groupby('trade_date').agg(
        lim=('limit_up', 'sum'), limd=('limit_down', 'sum'), ud=('up', 'sum'))
    for d in sorted(by_date.index, reverse=True):
        if d not in share_dates:
            continue
        row = by_date.loc[d]
        # 全市场涨跌停同时为 0 视为未结算（极罕见真为 0）
        if row['ud'] > 0 and (row['lim'] + row['limd']) > 0:
            return d
    # 兜底：取两源交集的最近日
    inter = sorted(share_dates & set(bl1['trade_date'].unique()), reverse=True)
    return inter[0] if inter else None


# ════════════════════════════════════════════════════════
#  横截面占比 + 占比历史分位 + 边际加速
# ════════════════════════════════════════════════════════
def calc_cross_section(share, ref_date=None):
    """
    share: sw_share_hist.csv（ts_code, trade_date, amount, name, share）
    ref_date: 统一对齐日（None 则取占比历史最新日）
    返回 (cross_section_list, accel_dict)
    """
    if share.empty:
        return [], {}

    share = share.copy()
    share['share'] = pd.to_numeric(share['share'], errors='coerce')
    dates = sorted(share['trade_date'].unique())
    latest = ref_date if (ref_date is not None and ref_date in dates) else dates[-1]
    # 只用 latest 及之前的历史算分位/变化，避免未来数据穿越
    share = share[share['trade_date'] <= latest]
    cur = share[share['trade_date'] == latest]

    # 每个行业的占比时间序列（算分位 + 变化）
    pivot = share.pivot_table(index='trade_date', columns='name', values='share', aggfunc='first').sort_index()

    cross = []
    for name in cur['name'].unique():
        if name not in pivot.columns:
            continue
        ser = pivot[name].dropna()
        if ser.empty:
            continue
        latest_share = float(ser.iloc[-1])
        # 占比历史分位（全样本）
        rank = pct_rank(ser, latest_share)
        # 5日 / 20日变化（占比的边际）
        chg_5 = float(latest_share - ser.iloc[-6]) if len(ser) > 6 else None
        chg_20 = float(latest_share - ser.iloc[-21]) if len(ser) > 21 else None
        cross.append({
            'name': name,
            'share': round(latest_share, 4),
            'share_pct': round(latest_share * 100, 2),
            'rank': round(rank, 3) if rank is not None else None,
            'chg_5d': round(chg_5, 5) if chg_5 is not None else None,
            'chg_20d': round(chg_20, 5) if chg_20 is not None else None,
        })

    cross.sort(key=lambda x: x['share'], reverse=True)

    # 边际加速排名（5日 / 20日占比变化）
    valid5 = [c for c in cross if c['chg_5d'] is not None]
    valid20 = [c for c in cross if c['chg_20d'] is not None]
    accel = {
        'date': pd.Timestamp(latest).strftime('%Y-%m-%d'),
        'week_up': sorted(valid5, key=lambda x: x['chg_5d'], reverse=True)[:5],
        'week_down': sorted(valid5, key=lambda x: x['chg_5d'])[:5],
        'month_up': sorted(valid20, key=lambda x: x['chg_20d'], reverse=True)[:5],
        'month_down': sorted(valid20, key=lambda x: x['chg_20d'])[:5],
    }
    return cross, accel


# ════════════════════════════════════════════════════════
#  breadth：涨跌家数比 + 涨跌停
# ════════════════════════════════════════════════════════
def calc_breadth(bdf, ref_date=None):
    """bdf: breadth_l1 或 l2（trade_date,name,up,down,flat,total,limit_up,limit_down）"""
    if bdf.empty:
        return [], None
    bdf = bdf.copy()
    for c in ['up', 'down', 'flat', 'total', 'limit_up', 'limit_down']:
        bdf[c] = pd.to_numeric(bdf[c], errors='coerce').fillna(0)
    has_avg = 'avg_chg' in bdf.columns
    if has_avg:
        bdf['avg_chg'] = pd.to_numeric(bdf['avg_chg'], errors='coerce').fillna(0)
    dates = sorted(bdf['trade_date'].unique())
    latest = ref_date if (ref_date is not None and ref_date in dates) else dates[-1]
    cur = bdf[bdf['trade_date'] == latest]

    out = []
    for _, r in cur.iterrows():
        up, down, total = r['up'], r['down'], r['total']
        denom = up + down
        up_ratio = float(up / denom) if denom > 0 else 0.5  # 涨家数占比（剔平盘）
        item = {
            'name': r['name'],
            'up': int(up), 'down': int(down), 'flat': int(r['flat']),
            'total': int(total),
            'up_ratio': round(up_ratio, 3),
            'limit_up': int(r['limit_up']), 'limit_down': int(r['limit_down']),
        }
        if has_avg:
            item['avg_chg'] = round(float(r['avg_chg']), 2)  # 等权平均涨幅（强度）
        if 'l1' in cur.columns:
            item['l1'] = r['l1']
        out.append(item)
    out.sort(key=lambda x: x['up_ratio'], reverse=True)
    return out, pd.Timestamp(latest).strftime('%Y-%m-%d')


# ════════════════════════════════════════════════════════
#  龙头案例：每个一级行业取「连板最高」+「成交额最大」两只代表票
#  借鉴龙头池算法（leader_pool_builder）：龙头 = 高度（连板）+ 资金（成交额）
# ════════════════════════════════════════════════════════
def calc_leader_cases(detail_df, ref_date=None):
    """
    detail_df: limit_detail.csv（trade_date, ts_code, stock_name, l1, l2, limit, limit_times, amount, pct_chg）
    返回 {一级行业名: {'up': [龙头票...], 'down': [跌停代表...]}}
    每个方向取两只去重：连板最高 + 成交额最大。
    """
    if detail_df.empty:
        return {}
    df = detail_df.copy()
    dates = sorted(df['trade_date'].unique())
    latest = ref_date if (ref_date is not None and ref_date in dates) else dates[-1]
    cur = df[df['trade_date'] == latest]
    if cur.empty:
        return {}

    cur = cur.copy()
    cur['limit_times'] = pd.to_numeric(cur['limit_times'], errors='coerce').fillna(1).astype(int)
    cur['amount'] = pd.to_numeric(cur['amount'], errors='coerce').fillna(0)
    cur['pct_chg'] = pd.to_numeric(cur['pct_chg'], errors='coerce').fillna(0)

    def pick_two(g):
        """连板最高 + 成交额最大，去重，最多两只"""
        picks = []
        seen = set()
        # 1. 连板最高（同高度取成交额大的）
        top_height = g.sort_values(['limit_times', 'amount'], ascending=[False, False]).iloc[0]
        picks.append(top_height)
        seen.add(top_height['ts_code'])
        # 2. 成交额最大（若与上面不同）
        top_amount = g.sort_values('amount', ascending=False).iloc[0]
        if top_amount['ts_code'] not in seen:
            picks.append(top_amount)
        return picks

    def fmt(row):
        return {
            'ts_code': row['ts_code'],
            'name': row['stock_name'],
            'limit_times': int(row['limit_times']),
            'amount': round(float(row['amount']) / 1e8, 2),  # 亿元
            'pct_chg': round(float(row['pct_chg']), 2),
            'l2': row.get('l2', ''),
        }

    result = {}
    for l1, g in cur.groupby('l1'):
        ups = g[g['limit'] == 'U']
        downs = g[g['limit'] == 'D']
        entry = {}
        if not ups.empty:
            entry['up'] = [fmt(r) for r in pick_two(ups)]
        if not downs.empty:
            # 跌停代表：成交额最大的1只（跌停不看连板高度）
            entry['down'] = [fmt(downs.sort_values('amount', ascending=False).iloc[0])]
        if entry:
            result[l1] = entry
    return result


# ════════════════════════════════════════════════════════
#  量价状态矩阵：占比分位（量/资金集中度） × breadth（价/赚钱效应）
# ════════════════════════════════════════════════════════
def calc_vp_matrix(cross, breadth_l1, leader_cases=None):
    """
    占比边际（chg_5d 升/降）作"量"维度，up_ratio（>0.5 强 / <0.5 弱）作"价"维度。
    四象限：
      量升价强 → 量价齐升   量升价弱 → 量升价不跟（见顶预警）
      量降价强 → 缩量上涨   量降价弱 → 量价齐跌
    叠加占比历史分位 rank：rank>0.9 标拥挤顶风险。
    """
    breadth_map = {b['name']: b for b in breadth_l1}
    leader_cases = leader_cases or {}
    matrix = []
    for c in cross:
        b = breadth_map.get(c['name'])
        if b is None:
            continue
        chg5 = c.get('chg_5d')
        up_ratio = b['up_ratio']
        rank = c.get('rank')

        vol_up = (chg5 is not None and chg5 > 0)
        price_strong = up_ratio >= 0.5

        if vol_up and price_strong:
            state = '量价齐升'
            tone = 'up'
        elif vol_up and not price_strong:
            state = '量升价不跟'
            tone = 'warn'
        elif (not vol_up) and price_strong:
            state = '缩量上涨'
            tone = 'cool'
        else:
            state = '量价齐跌'
            tone = 'down'

        # 拥挤顶风险：占比历史高位 + 量升价不跟
        risk = None
        if rank is not None and rank > 0.9 and state == '量升价不跟':
            risk = '拥挤顶预警'
        elif rank is not None and rank > 0.9 and state == '量价齐升':
            risk = '高位拥挤'
        elif rank is not None and rank < 0.1 and state == '量价齐跌':
            risk = '低位出清'

        matrix.append({
            'name': c['name'],
            'share_pct': c['share_pct'],
            'rank': rank,
            'chg_5d': chg5,
            'up_ratio': up_ratio,
            'avg_chg': b.get('avg_chg'),
            'state': state,
            'tone': tone,
            'risk': risk,
            'leaders': leader_cases.get(c['name'], {}),
        })
    matrix.sort(key=lambda x: (x['rank'] if x['rank'] is not None else 0), reverse=True)
    return matrix


def export_share_series(share):
    """
    导出占比时间序列为独立 JSON（前端折线图 + 量比计算用）。
    格式：{ dates: [...], series: { "电子": [...], ... }, amount: { "电子": [...], ... } }
    series = 占比百分比（如 30.77），amount = 原始成交额（千元）。
    """
    if share.empty:
        return
    share = share.copy()
    share['share'] = pd.to_numeric(share['share'], errors='coerce')
    share['amount'] = pd.to_numeric(share['amount'], errors='coerce')
    pivot_share = share.pivot_table(index='trade_date', columns='name', values='share', aggfunc='first').sort_index()
    pivot_amount = share.pivot_table(index='trade_date', columns='name', values='amount', aggfunc='first').sort_index()
    dates = [pd.Timestamp(d).strftime('%Y-%m-%d') for d in pivot_share.index]
    series = {}
    amount = {}
    for col in pivot_share.columns:
        series[col] = [round(float(v * 100), 2) if pd.notna(v) else None for v in pivot_share[col]]
        amount[col] = [round(float(v), 0) if pd.notna(v) else None for v in pivot_amount[col]]
    out = {'dates': dates, 'series': series, 'amount': amount}
    with open(SHARE_SERIES_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'  占比时间序列: {len(dates)}天 × {len(series)}行业 → {SHARE_SERIES_JSON}')


def main():
    if not os.path.exists(OUTPUT_JSON):
        print(f'未找到 {OUTPUT_JSON}，请先运行 crowding_calc.py')
        result = {}
    else:
        with open(OUTPUT_JSON, encoding='utf-8') as f:
            result = json.load(f)

    share = load_csv(SHARE_HIST_CSV)
    bl1 = load_csv(BREADTH_L1_CSV)
    bl2 = load_csv(BREADTH_L2_CSV)
    detail = load_csv(LIMIT_DETAIL_CSV)

    # 统一对齐到三源齐全的最近交易日
    ref_date = resolve_ref_date(share, bl1)
    if ref_date is not None:
        print(f'  对齐基准日: {pd.Timestamp(ref_date).strftime("%Y-%m-%d")}')

    cross, accel = calc_cross_section(share, ref_date)
    breadth_l1, b1_date = calc_breadth(bl1, ref_date)
    breadth_l2, b2_date = calc_breadth(bl2, ref_date)
    leader_cases = calc_leader_cases(detail, ref_date)
    vp_matrix = calc_vp_matrix(cross, breadth_l1, leader_cases)

    # 全市场情绪温度（一级行业涨跌停加总）
    total_lu = sum(b['limit_up'] for b in breadth_l1)
    total_ld = sum(b['limit_down'] for b in breadth_l1)
    total_up = sum(b['up'] for b in breadth_l1)
    total_down = sum(b['down'] for b in breadth_l1)
    mkt_denom = total_up + total_down
    market_emotion = {
        'date': b1_date,
        'limit_up': total_lu,
        'limit_down': total_ld,
        'up': total_up,
        'down': total_down,
        'up_ratio': round(total_up / mkt_denom, 3) if mkt_denom > 0 else None,
    }

    result['cross_section'] = cross
    result['accel_rank'] = accel
    result['breadth_l1'] = {'date': b1_date, 'data': breadth_l1}
    result['breadth_l2'] = {'date': b2_date, 'data': breadth_l2}
    result['vp_matrix'] = vp_matrix
    result['market_emotion'] = market_emotion

    # 拥挤/breadth 信号存独立字段，每次全量覆盖（幂等，不污染 crowding_calc 的 base 信号）
    extra_signals = []
    for m in vp_matrix:
        if m['risk'] == '拥挤顶预警':
            extra_signals.append(f"{m['name']} 拥挤顶预警(占比{m['share_pct']:.1f}% 分位{m['rank']*100:.0f}% 放量但赚钱效应弱)")
        elif m['risk'] == '高位拥挤':
            extra_signals.append(f"{m['name']} 高位拥挤(占比分位{m['rank']*100:.0f}%)")
    if accel.get('week_up'):
        top = accel['week_up'][0]
        if top['chg_5d'] and top['chg_5d'] > 0:
            extra_signals.append(f"资金加速涌入 {top['name']}(周占比+{top['chg_5d']*100:.2f}pct)")
    if market_emotion['limit_up'] is not None:
        if total_lu >= 60 and total_lu > total_ld * 1.5:
            extra_signals.append(f"全市场情绪亢奋(涨停{total_lu}/跌停{total_ld})")
        elif total_ld >= 40 and total_ld > total_lu * 1.5:
            extra_signals.append(f"全市场情绪恐慌(跌停{total_ld}/涨停{total_lu})")

    # 去重保序
    seen, dedup = set(), []
    for s in extra_signals:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    result['breadth_signals'] = dedup

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 输出占比时间序列(独立 JSON,前端折线图用)
    export_share_series(share)

    print(f'输出: {OUTPUT_JSON}')
    print(f'  横截面占比: {len(cross)} 行业, 最新 {accel.get("date")}')
    print(f'  breadth 一级: {len(breadth_l1)} / 二级: {len(breadth_l2)}, 最新 {b1_date}')
    print(f'  量价状态矩阵: {len(vp_matrix)} 行业')
    print(f'  情绪温度: 涨停{total_lu} 跌停{total_ld}')
    if accel.get('week_up'):
        print('  周度加速TOP3:', [(x['name'], round(x['chg_5d']*100, 2)) for x in accel['week_up'][:3]])


if __name__ == '__main__':
    main()
