#!/usr/bin/env python3
"""
超额环境回溯归因
================
对产品净值的每个周频点，回溯计算当时的环境因子状态。
用于前端图表的hover tooltip归因解释。

输出：excess_attribution.json
"""
import json, os, math, statistics
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(os.path.dirname(BASE))

def load(path):
    with open(path, 'r') as f:
        return json.load(f)

def safe_load(path, default=None):
    try:
        return load(path)
    except:
        return default

# ═══ 数据加载 ═══
qs_data = load(os.path.join(BASE, 'quant_stock_data.json'))
fund_nav = load(os.path.join(DASH, 'size_spread', 'fund_nav', 'fund_nav_quant-stock.json'))
cross_vol_hist = safe_load(os.path.join(BASE, 'cross_vol_history.json'), {})

chart = fund_nav['fund']['chart']
nav_dates = chart['dates']       # ['2025-01-03', ...]  周频
nav_excess = chart['excess']     # 累计超额序列

# 把日频数据按 trade_date 索引方便查找
def build_index(arr, date_key='date'):
    """日频数组 → {date_str: record}"""
    idx = {}
    for r in arr:
        idx[r[date_key]] = r
    return idx

amount_idx = build_index(qs_data['total_amount'])
share_idx = build_index(qs_data['index_share'])
basis_idx = build_index(qs_data['basis'])
factor_idx = build_index(qs_data['factor'])

# 截面波动率历史
cv_data = cross_vol_hist.get('data', [])
cv_idx = {}
for r in cv_data:
    cv_idx[r['date']] = r

# 基差历史序列（用于算分位数）
all_im = [d.get('IM', 0) for d in qs_data['basis']]

# 指数日线（用于虹吸验证）
import csv
def load_index_csv():
    path = os.path.join(BASE, 'qs_index_daily.csv')
    data = {}
    try:
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('ts_code', '')
                if not code: continue
                if code not in data: data[code] = []
                data[code].append({
                    'date': row.get('trade_date', ''),
                    'close': float(row.get('close', 0)),
                    'amount': float(row.get('amount', 0)) if row.get('amount') else 0,
                })
        for code in data:
            data[code].sort(key=lambda x: x['date'])
    except:
        pass
    return data

idx_daily = load_index_csv()
# 按日期索引
idx_daily_map = {}
for code, series in idx_daily.items():
    idx_daily_map[code] = {r['date']: r for r in series}

def date_to_yyyymmdd(d):
    """'2025-01-03' → '20250103'"""
    return d.replace('-', '')

def get_nearby_dates(target_yyyymmdd, n_before=5, n_after=0):
    """获取target附近的交易日列表（从成交额数据中查）"""
    all_dates = sorted(amount_idx.keys())
    try:
        pos = all_dates.index(target_yyyymmdd)
    except ValueError:
        # 找最近的
        for i, d in enumerate(all_dates):
            if d >= target_yyyymmdd:
                pos = i
                break
        else:
            pos = len(all_dates) - 1
    start = max(0, pos - n_before + 1)
    end = min(len(all_dates), pos + n_after + 1)
    return all_dates[start:end]


def calc_env_at(date_str):
    """
    计算某周频日期的环境因子快照。
    返回各因子的关键指标。
    """
    td = date_to_yyyymmdd(date_str)
    result = {}

    # ── 流动性 ──
    nearby = get_nearby_dates(td, n_before=20)
    amounts = []
    for d in nearby:
        r = amount_idx.get(d)
        if r:
            amounts.append(r.get('amount_yi', r.get('amount', 0)))

    if amounts:
        recent5 = amounts[-5:] if len(amounts) >= 5 else amounts
        ma5 = sum(recent5) / len(recent5)
        ma20 = sum(amounts) / len(amounts)
        latest_amt = amounts[-1]
        cv = (statistics.stdev(amounts) / ma20) if len(amounts) > 1 and ma20 > 0 else 0
        trend = '放量' if ma5 > ma20 * 1.05 else ('缩量' if ma5 < ma20 * 0.95 else '平稳')
        result['liquidity'] = {
            'amount': round(latest_amt, 0),
            'ma5': round(ma5, 0),
            'ma20': round(ma20, 0),
            'cv': round(cv, 3),
            'trend': trend,
        }

    # ── 风格集中度 + 迁移 ──
    style_keys = ['沪深300', '中证500', '中证1000', '中证2000', '科创+创业板']
    share_dates_20 = get_nearby_dates(td, n_before=20)
    share_dates_5 = share_dates_20[-5:] if len(share_dates_20) >= 5 else share_dates_20

    shares_5 = [share_idx[d] for d in share_dates_5 if d in share_idx]
    shares_20 = [share_idx[d] for d in share_dates_20 if d in share_idx]

    if shares_5:
        avg5 = {}
        avg20 = {}
        for k in style_keys:
            v5 = [s.get(k, 0) for s in shares_5]
            avg5[k] = sum(v5) / len(v5)
            v20 = [s.get(k, 0) for s in shares_20]
            avg20[k] = sum(v20) / len(v20) if v20 else avg5[k]

        total = sum(avg5.values())
        if total > 0:
            norm = {k: v / total for k, v in avg5.items()}
            hhi = sum(v ** 2 for v in norm.values())
        else:
            hhi = 0.2

        # 迁移
        deltas = {k: round(avg5[k] - avg20[k], 2) for k in style_keys}
        max_mover = max(deltas, key=lambda k: abs(deltas[k]))
        max_delta = deltas[max_mover]

        dominant = max(avg5, key=avg5.get)

        result['style'] = {
            'hhi': round(hhi, 4),
            'dominant': dominant,
            'dominant_pct': round(avg5[dominant], 1),
            'max_mover': max_mover,
            'max_delta': max_delta,
            'deltas': deltas,
        }

    # ── 基差 + 虹吸 ──
    basis_r = basis_idx.get(td)
    # 找最近的交易日
    if not basis_r:
        for d in reversed(get_nearby_dates(td, n_before=5)):
            if d in basis_idx:
                basis_r = basis_idx[d]
                break

    if basis_r:
        im = basis_r.get('IM', 0)
        ic = basis_r.get('IC', 0)
        if_b = basis_r.get('IF', 0)

        # 历史分位（截止到当前日期）
        hist_im = [d.get('IM', 0) for d in qs_data['basis'] if d['date'] <= td]
        rank = sum(1 for x in hist_im if x <= im)
        pctile = rank / len(hist_im) * 100 if hist_im else 50

        # 虹吸检查
        siphon = False
        siphon_note = ''
        is_premium = im > 0 or pctile > 80

        if is_premium and shares_5 and shares_20:
            big5 = sum(s.get('沪深300', 0) + s.get('中证500', 0) for s in shares_5) / len(shares_5)
            big20 = sum(s.get('沪深300', 0) + s.get('中证500', 0) for s in shares_20) / len(shares_20)
            surge = big5 - big20

            # 大票跑赢小票
            ret300 = ret1000 = None
            s300 = idx_daily_map.get('000300.SH', {})
            s1000 = idx_daily_map.get('000852.SH', {})
            dates_5 = get_nearby_dates(td, n_before=5)
            if len(dates_5) >= 2:
                d_end = dates_5[-1]
                d_start = dates_5[0]
                if d_end in s300 and d_start in s300:
                    ret300 = (s300[d_end]['close'] / s300[d_start]['close'] - 1) * 100
                if d_end in s1000 and d_start in s1000:
                    ret1000 = (s1000[d_end]['close'] / s1000[d_start]['close'] - 1) * 100

            outperf = (ret300 - ret1000) if (ret300 is not None and ret1000 is not None) else None
            cond_a = surge > 2.0
            cond_b = outperf is not None and outperf > 2.0
            siphon = cond_a and cond_b

            if siphon:
                siphon_note = f'占比+{surge:.1f}pp, 300跑赢{outperf:.1f}%'

        result['basis'] = {
            'im': round(im, 2),
            'ic': round(ic, 2),
            'if': round(if_b, 2),
            'pctile': round(pctile, 0),
            'siphon': siphon,
            'siphon_note': siphon_note,
        }

    # ── 离散度（如果有历史数据）──
    cv_r = cv_idx.get(td)
    if not cv_r:
        for d in reversed(get_nearby_dates(td, n_before=3)):
            d8 = d  # already yyyymmdd
            if d8 in cv_idx:
                cv_r = cv_idx[d8]
                break
    if cv_r:
        result['dispersion'] = {
            'cross_vol': cv_r.get('cross_vol', 0),
            'stock_count': cv_r.get('stock_count', 0),
        }

    # ── 因子动态 ──
    factor_dates = get_nearby_dates(td, n_before=10)
    early = factor_dates[:5]
    late = factor_dates[-5:]
    fnames = qs_data.get('factor_names', [])
    factor_chgs = {}
    for fn in fnames:
        e_vals = [factor_idx[d].get(fn, 1) for d in early if d in factor_idx]
        l_vals = [factor_idx[d].get(fn, 1) for d in late if d in factor_idx]
        if e_vals and l_vals:
            e_avg = sum(e_vals) / len(e_vals)
            l_avg = sum(l_vals) / len(l_vals)
            chg = (l_avg / e_avg - 1) * 100 if e_avg else 0
            factor_chgs[fn] = round(chg, 2)
    if factor_chgs:
        result['factors'] = factor_chgs

    return result


# ═══ Main ═══
if __name__ == '__main__':
    print('📊 超额环境回溯归因')
    print(f'  产品净值: {len(nav_dates)}个周频点')
    print(f'  截面波动率历史: {len(cv_data)}天')

    # 计算每个周频点的环境快照
    points = []
    for i in range(len(nav_dates)):
        date = nav_dates[i]
        ex = nav_excess[i]
        delta = (nav_excess[i] - nav_excess[i-1]) if i > 0 else 0

        # 环境标签
        if delta < -0.01:
            zone = 'bad'       # 明显回撤
        elif delta < -0.003:
            zone = 'weak'      # 小回撤/走平
        elif delta > 0.01:
            zone = 'good'      # 顺风
        else:
            zone = 'neutral'

        env = calc_env_at(date)

        points.append({
            'date': date,
            'excess': round(ex, 6),
            'delta': round(delta, 6),
            'zone': zone,
            'env': env,
        })

        if i % 10 == 0:
            print(f'  {date} excess={ex:.4f} Δ={delta:+.4f} [{zone}]')

    # 识别连续难做时段
    bad_periods = []
    streak_start = None
    for i, p in enumerate(points):
        if p['zone'] in ('bad', 'weak'):
            if streak_start is None:
                streak_start = i
        else:
            if streak_start is not None:
                # 结束一段
                dd = points[streak_start]['excess'] - points[i-1]['excess']
                bad_periods.append({
                    'start': points[streak_start]['date'],
                    'end': points[i-1]['date'],
                    'start_idx': streak_start,
                    'end_idx': i-1,
                    'drawdown': round(dd, 6),
                    'weeks': i - streak_start,
                })
                streak_start = None

    if streak_start is not None:
        dd = points[streak_start]['excess'] - points[-1]['excess']
        bad_periods.append({
            'start': points[streak_start]['date'],
            'end': points[-1]['date'],
            'start_idx': streak_start,
            'end_idx': len(points)-1,
            'drawdown': round(dd, 6),
            'weeks': len(points) - streak_start,
        })

    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'points': points,
        'bad_periods': bad_periods,
        'nav_dates': nav_dates,
        'nav_excess': [round(x, 6) for x in nav_excess],
        'fund_nav': chart.get('fund_nav', []),
        'index_nav': chart.get('index_nav', []),
    }

    out_path = os.path.join(BASE, 'excess_attribution.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 输出 {len(points)} 个点 → {out_path}')
    print(f'  难做时段: {len(bad_periods)} 段')
    for bp in bad_periods:
        print(f'    {bp["start"]} ~ {bp["end"]} ({bp["weeks"]}周) 超额{bp["drawdown"]:+.4f}')
