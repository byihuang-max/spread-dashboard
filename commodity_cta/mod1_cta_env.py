#!/usr/bin/env python3
"""
模块一：CTA整体环境指标（CSV增量模式）
从 fut_daily.csv 读取数据，计算每品种指标 + 汇总CTA友好度
输出：mod1_cta_env.json + mod1_cta_env.csv（含公式列）
"""

import json, os, csv, math
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'mod1_cta_env.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod1_cta_env.csv')

SECTORS = {
    '黑色系':['RB','HC','I','J','JM','SF','SM','SS'],
    '有色金属':['CU','AL','ZN','PB','NI','SN','BC','AO','SI'],
    '贵金属':['AU','AG'],
    '能源化工':['SC','FU','LU','BU','MA','EG','EB','TA','PP','L','V','PF','SA','FG','UR','PX','SP','RU','NR','BR','PG'],
    '农产品':['A','B','M','Y','P','OI','RM','CF','CY','SR','C','CS','JD','LH','AP','CJ','PK','WH','RI','RR'],
}
SYMBOL_SECTOR = {}
for sec, syms in SECTORS.items():
    for s in syms:
        SYMBOL_SECTOR[s] = sec

def log(msg):
    print(msg, flush=True)


def load_fut_csv():
    """从 fut_daily.csv 读取数据，返回 {symbol: [{date,close,pre_close,vol,amount,oi},...]}"""
    if not os.path.exists(FUT_CSV):
        log(f"ERROR: {FUT_CSV} 不存在，先跑 commodity_data.py")
        return 
    series = defaultdict(list)
    with open(FUT_CSV, 'r', newline='', encoding='gb18030') as f:
        for row in csv.DictReader(f):
            sym = row.get('symbol', '')
            if not sym:
                continue
            close = row.get('close', '')
            if not close:
                continue
            series[sym].append({
                'date': row['trade_date'],
                'close': float(close),
                'pre_close': float(row['pre_close']) if row.get('pre_close') else None,
                'vol': float(row['vol']) if row.get('vol') else 0,
                'amount': float(row['amount']) if row.get('amount') else 0,
                'oi': float(row['oi']) if row.get('oi') else 0,
            })
    # 按日期排序
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


def compute_env(series):
    """计算每品种指标 + 汇总"""
    per_symbol = {}

    for sym, data in series.items():
        if len(data) < 3:
            continue

        closes = [d['close'] for d in data]
        amounts = [d['amount'] for d in data]

        # 涨跌幅序列
        pcts = []
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                pcts.append((closes[i] / closes[i-1] - 1) * 100)
            else:
                pcts.append(0)

        # 20日年化波动率
        recent_pcts = pcts[-20:]
        if len(recent_pcts) >= 3:
            mean_r = sum(recent_pcts) / len(recent_pcts)
            var = sum((r - mean_r)**2 for r in recent_pcts) / len(recent_pcts)
            vol_20d = math.sqrt(var) * math.sqrt(252) / 100
        else:
            vol_20d = 0

        # MA20 斜率 → 趋势方向
        n_ma = min(len(closes), 20)
        ma_now = sum(closes[-n_ma:]) / n_ma
        if len(closes) > n_ma:
            ma_prev = sum(closes[-n_ma-1:-1]) / n_ma
        else:
            ma_prev = ma_now
        ma20_slope = (ma_now - ma_prev) / ma_prev * 100 if ma_prev else 0

        if ma20_slope > 0.5:
            trend_dir = '多头'
        elif ma20_slope < -0.5:
            trend_dir = '空头'
        else:
            trend_dir = '震荡'

        has_trend = trend_dir in ('多头', '空头')

        # 成交额 MA20/MA60
        n20 = min(len(amounts), 20)
        n60 = min(len(amounts), 60)
        ma20_amt = sum(amounts[-n20:]) / n20 if n20 else 0
        ma60_amt = sum(amounts[-n60:]) / n60 if n60 else 0
        volume_ratio = ma20_amt / ma60_amt if ma60_amt > 0 else 1.0

        per_symbol[sym] = {
            'symbol': sym,
            'sector': SYMBOL_SECTOR.get(sym, '其他'),
            'close': closes[-1],
            'vol_20d': round(vol_20d, 4),
            'ma20_slope': round(ma20_slope, 4),
            'trend_dir': trend_dir,
            'has_trend': has_trend,
            'volume_ratio': round(volume_ratio, 4),
            'avg_daily_amt': round(ma20_amt, 2),
        }

    # 汇总：只看活跃品种（日均成交额 > 500万）
    active = {k: v for k, v in per_symbol.items() if v['avg_daily_amt'] > 500}
    if not active:
        active = per_symbol

    n_active = len(active)
    avg_vol_20d = sum(v['vol_20d'] for v in active.values()) / n_active if n_active else 0
    trend_count = sum(1 for v in active.values() if v['has_trend'])
    trend_pct = trend_count / n_active if n_active else 0
    avg_volume_ratio = sum(v['volume_ratio'] for v in active.values()) / n_active if n_active else 1

    # 分位数映射
    vol_pctile = max(0, min(1, (avg_vol_20d - 0.10) / 0.30))

    # CTA友好度
    trend_pct_norm = trend_pct
    vol_pctile_norm = vol_pctile
    vol_ratio_norm = max(0, min(1, (avg_volume_ratio - 0.7) / 0.6))
    cta_friendly = round((0.40 * trend_pct_norm + 0.30 * vol_pctile_norm + 0.30 * vol_ratio_norm) * 100, 1)

    latest_date = max(d['date'] for data in series.values() for d in data)

    summary = {
        'date': latest_date,
        'n_active': n_active,
        'avg_vol_20d': round(avg_vol_20d, 4),
        'vol_percentile_60d': round(vol_pctile, 4),
        'trend_pct': round(trend_pct, 4),
        'trend_count': trend_count,
        'avg_volume_ratio': round(avg_volume_ratio, 4),
        'cta_friendly': cta_friendly,
        'cta_friendly_raw': {
            'trend_pct_norm': round(trend_pct_norm, 4),
            'vol_pctile_norm': round(vol_pctile_norm, 4),
            'vol_ratio_norm': round(vol_ratio_norm, 4),
        },
    }

    return summary, per_symbol


def write_output(summary, per_symbol):
    """输出 JSON + CSV"""
    # JSON（格式不变）
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({'summary': summary, 'per_symbol': per_symbol}, f, ensure_ascii=False, indent=2)

    # CSV（含公式列）
    csv_headers = [
        'symbol', 'sector', 'close', 'vol_20d', 'ma20_slope', 'trend_dir',
        'has_trend', 'volume_ratio', 'avg_daily_amt',
        'formula_vol_20d', 'formula_ma20_slope', 'formula_trend_dir',
        'formula_volume_ratio', 'formula_cta_friendly'
    ]
    rows = []
    for sym in sorted(per_symbol.keys()):
        v = per_symbol[sym]
        rows.append({
            **v,
            'formula_vol_20d': 'std(近20日涨跌幅%) × sqrt(252) / 100 → 年化波动率',
            'formula_ma20_slope': '(MA20_today - MA20_yesterday) / MA20_yesterday × 100',
            'formula_trend_dir': '多头(slope>0.5) | 空头(slope<-0.5) | 震荡(其他)',
            'formula_volume_ratio': '成交额MA20 / 成交额MA60',
            'formula_cta_friendly': '0.40×趋势占比 + 0.30×波动率分位 + 0.30×成交量比标准化 (×100)',
        })

    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    log("=" * 50)
    log("模块一：CTA整体环境（从CSV读取）")
    log("=" * 50)

    series = load_fut_csv()
    if not series:
        return

    log(f"  {len(series)} 个品种")

    summary, per_symbol = compute_env(series)

    write_output(summary, per_symbol)

    s = summary
    log(f"\n✅ 模块一完成")
    log(f"  日期: {s['date']}")
    log(f"  活跃品种: {s['n_active']}")
    log(f"  平均20日波动率: {s['avg_vol_20d']:.2%}")
    log(f"  趋势品种占比: {s['trend_pct']:.1%} ({s['trend_count']}/{s['n_active']})")
    log(f"  CTA友好度: {s['cta_friendly']}")
    log(f"  CSV: {OUT_CSV}")


if __name__ == '__main__':
    main()
