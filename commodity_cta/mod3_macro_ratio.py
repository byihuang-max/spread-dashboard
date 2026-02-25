#!/usr/bin/env python3
"""
模块三：宏观比价信号（CSV增量模式）
从 fut_daily.csv 读取数据，计算铜金比、油金比、工业品/农产品比
输出：mod3_macro_ratio.json + mod3_macro_ratio.csv（含公式列）
"""

import json, os, csv, math
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'mod3_macro_ratio.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod3_macro_ratio.csv')

INDUSTRIAL_BASKET = ['RB', 'CU', 'AL', 'MA', 'TA', 'EG']
AGRI_BASKET = ['M', 'P', 'SR', 'C', 'OI', 'CF']

def log(msg):
    print(msg, flush=True)


def load_fut_csv():
    if not os.path.exists(FUT_CSV):
        log(f"ERROR: {FUT_CSV} 不存在，先跑 commodity_data.py")
        return None
    series = defaultdict(list)
    with open(FUT_CSV, 'r', newline='', encoding='gb18030') as f:
        for row in csv.DictReader(f):
            sym = row.get('symbol', '')
            close = row.get('close', '')
            if not sym or not close:
                continue
            series[sym].append({
                'date': row['trade_date'],
                'close': float(close),
                'pre_close': float(row['pre_close']) if row.get('pre_close') else None,
            })
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


def calc_ratio_stats(ratio_series):
    if len(ratio_series) < 2:
        return None
    dates = [r[0] for r in ratio_series]
    vals = [r[1] for r in ratio_series]
    latest = vals[-1]

    # 20日变化%
    if len(vals) >= 21:
        chg_20d = (vals[-1] - vals[-21]) / vals[-21] * 100
    elif len(vals) >= 2:
        chg_20d = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] != 0 else 0
    else:
        chg_20d = 0

    # 60日分位数
    window = vals[-60:] if len(vals) >= 60 else vals
    sorted_w = sorted(window)
    rank = sum(1 for v in sorted_w if v <= latest)
    pctile_60d = rank / len(sorted_w) if sorted_w else 0.5

    # MA5斜率 → 趋势
    if len(vals) >= 6:
        ma5_now = sum(vals[-5:]) / 5
        ma5_prev = sum(vals[-6:-1]) / 5
        slope = (ma5_now - ma5_prev) / ma5_prev * 100 if ma5_prev else 0
        if slope > 0.3:
            trend = '上升'
        elif slope < -0.3:
            trend = '下降'
        else:
            trend = '横盘'
    else:
        trend = '数据不足'
        slope = 0

    return {
        'latest': round(latest, 6),
        'chg_20d_pct': round(chg_20d, 2),
        'pctile_60d': round(pctile_60d, 4),
        'trend': trend,
        'ma5_slope_pct': round(slope, 4),
        'n_days': len(vals),
        'series': [{'date': d, 'value': round(v, 6)} for d, v in ratio_series],
    }


def calc_basket_nav(series, symbols, common_dates):
    """计算篮子等权归1复利净值"""
    nav = 1.0
    nav_series = []
    sym_close_map = {}
    for s in symbols:
        if s in series:
            sym_close_map[s] = {d['date']: d['close'] for d in series[s]}

    prev_date = None
    for d in common_dates:
        if prev_date is None:
            nav_series.append((d, nav))
            prev_date = d
            continue
        rets = []
        for s in symbols:
            cm = sym_close_map.get(s, {})
            if d in cm and prev_date in cm and cm[prev_date] > 0:
                rets.append(cm[d] / cm[prev_date] - 1)
        if rets:
            avg_ret = sum(rets) / len(rets)
            nav *= (1 + avg_ret)
        nav_series.append((d, round(nav, 6)))
        prev_date = d
    return nav_series


def compute_ratios(series):
    results = {}

    # 铜金比 CU/AU
    cu_map = {d['date']: d['close'] for d in series.get('CU', [])}
    au_map = {d['date']: d['close'] for d in series.get('AU', [])}
    common = sorted(set(cu_map.keys()) & set(au_map.keys()))
    cu_au = [(d, cu_map[d] / au_map[d]) for d in common if au_map[d] > 0]
    stats = calc_ratio_stats(cu_au)
    if stats:
        stats['name'] = '铜金比'
        stats['formula'] = 'CU连续/AU连续'
        stats['meaning'] = '上升=经济预期改善，下降=避险升温'
        results['cu_au'] = stats

    # 油金比 SC/AU
    sc_map = {d['date']: d['close'] for d in series.get('SC', [])}
    sc_au = [(d, sc_map[d] / au_map[d]) for d in sorted(set(sc_map.keys()) & set(au_map.keys())) if au_map.get(d, 0) > 0]
    stats = calc_ratio_stats(sc_au)
    if stats:
        stats['name'] = '油金比'
        stats['formula'] = 'SC原油连续/AU连续'
        stats['meaning'] = '上升=通胀预期/需求强，下降=衰退预期'
        results['sc_au'] = stats

    # 工业品/农产品篮子比
    ind_syms = [s for s in INDUSTRIAL_BASKET if s in series]
    agr_syms = [s for s in AGRI_BASKET if s in series]
    if ind_syms and agr_syms:
        all_date_sets = [set(d['date'] for d in series[s]) for s in ind_syms + agr_syms]
        common = sorted(set.intersection(*all_date_sets))
        if len(common) >= 20:
            ind_nav = calc_basket_nav(series, ind_syms, common)
            agr_nav = calc_basket_nav(series, agr_syms, common)
            ind_dict = dict(ind_nav)
            agr_dict = dict(agr_nav)
            ratio_vals = [(d, ind_dict[d] / agr_dict[d]) for d in common if agr_dict.get(d, 0) > 0]
            stats = calc_ratio_stats(ratio_vals)
            if stats:
                stats['name'] = '工业品/农产品'
                stats['formula'] = f'工业篮子({",".join(ind_syms)})等权净值 / 农产品篮子({",".join(agr_syms)})等权净值'
                stats['meaning'] = '上升=工业品相对强势(经济扩张)，下降=农产品相对强势(防御)'
                results['ind_agri'] = stats

            results['_basket_nav'] = {
                'industrial': ind_nav,
                'agricultural': agr_nav,
            }

    return results


def write_output(results):
    # JSON
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # CSV（每个比价一行，含公式）
    csv_headers = [
        'ratio_name', 'latest', 'chg_20d_pct', 'pctile_60d', 'trend',
        'ma5_slope_pct', 'n_days', 'formula', 'meaning',
        'formula_chg_20d', 'formula_pctile_60d', 'formula_trend'
    ]
    rows = []
    for key in ['cu_au', 'sc_au', 'ind_agri']:
        r = results.get(key)
        if not r:
            continue
        rows.append({
            'ratio_name': r['name'],
            'latest': r['latest'],
            'chg_20d_pct': r['chg_20d_pct'],
            'pctile_60d': r['pctile_60d'],
            'trend': r['trend'],
            'ma5_slope_pct': r['ma5_slope_pct'],
            'n_days': r['n_days'],
            'formula': r.get('formula', ''),
            'meaning': r.get('meaning', ''),
            'formula_chg_20d': '(latest - value_20d_ago) / value_20d_ago × 100',
            'formula_pctile_60d': 'rank(latest in 近60日序列) / len(序列)',
            'formula_trend': '上升(MA5斜率>0.3%) | 下降(<-0.3%) | 横盘(其他)',
        })

    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    log("=" * 50)
    log("模块三：宏观比价信号（从CSV读取）")
    log("=" * 50)

    series = load_fut_csv()
    if not series:
        return

    log(f"  {len(series)} 个品种")

    results = compute_ratios(series)

    write_output(results)

    log(f"\n✅ 模块三完成")
    for key in ['cu_au', 'sc_au', 'ind_agri']:
        r = results.get(key)
        if r:
            log(f"  {r['name']}: {r['latest']:.4f} | 20日: {r['chg_20d_pct']:+.2f}% | 分位: {r['pctile_60d']:.0%} | {r['trend']}")
    log(f"  CSV: {OUT_CSV}")


if __name__ == '__main__':
    main()
