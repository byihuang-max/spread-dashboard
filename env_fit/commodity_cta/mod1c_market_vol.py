#!/usr/bin/env python3
"""mod1c: 全市场平均波动率时序

从 fut_daily.csv 计算：
- 每个活跃品种的20日滚动波动率（年化）
- 全市场等权平均波动率
- 波动率的历史分位数（120日窗口）
- 波动率变化率（Δvol）

输出 mod1c_market_vol.json
"""

import csv, json, os, math
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(DIR, 'fut_daily.csv')
OUT_PATH = os.path.join(DIR, 'mod1c_market_vol.json')

VOL_WINDOW = 20
QUANTILE_WINDOW = 120


def read_csv():
    """读取fut_daily.csv，返回 {symbol: [(date, close, volume), ...]}"""
    data = defaultdict(list)
    with open(CSV_PATH, 'r', encoding='gb18030') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get('ts_code', '')
            date = row.get('trade_date', '')
            close = row.get('close', '')
            vol = row.get('vol', '0')
            if sym and date and close:
                try:
                    data[sym].append((date, float(close), float(vol or 0)))
                except ValueError:
                    pass
    # sort by date
    for sym in data:
        data[sym].sort(key=lambda x: x[0])
    return data


def calc_vol(prices, window=VOL_WINDOW):
    """计算滚动波动率（年化），返回 [(date, vol), ...]"""
    if len(prices) < window + 1:
        return []
    # daily returns
    rets = []
    for i in range(1, len(prices)):
        if prices[i-1][1] > 0:
            rets.append((prices[i][0], prices[i][1] / prices[i-1][1] - 1))

    result = []
    for i in range(window - 1, len(rets)):
        window_rets = [r[1] for r in rets[i - window + 1:i + 1]]
        mean = sum(window_rets) / len(window_rets)
        var = sum((r - mean) ** 2 for r in window_rets) / (len(window_rets) - 1)
        vol = math.sqrt(var) * math.sqrt(252) * 100  # 年化%
        result.append((rets[i][0], round(vol, 2)))
    return result


def main():
    print("=" * 60)
    print("mod1c: 全市场平均波动率")
    print("=" * 60)

    data = read_csv()
    print(f"  品种数: {len(data)}")

    # 每品种波动率
    all_vols = defaultdict(list)  # date -> [vol1, vol2, ...]
    for sym, prices in data.items():
        vols = calc_vol(prices, VOL_WINDOW)
        for date, vol in vols:
            all_vols[date].append(vol)

    # 全市场等权平均
    dates = sorted(all_vols.keys())
    print(f"  日期范围: {dates[0]} ~ {dates[-1]} ({len(dates)}天)")

    series = []
    for d in dates:
        vols = all_vols[d]
        avg = sum(vols) / len(vols)
        med = sorted(vols)[len(vols) // 2]
        series.append({
            'date': d,
            'avg_vol': round(avg, 2),
            'median_vol': round(med, 2),
            'n_symbols': len(vols),
            'max_vol': round(max(vols), 2),
            'min_vol': round(min(vols), 2),
        })

    # 历史分位数
    for i, s in enumerate(series):
        start = max(0, i - QUANTILE_WINDOW + 1)
        history = [series[j]['avg_vol'] for j in range(start, i + 1)]
        rank = sum(1 for v in history if v <= s['avg_vol'])
        s['vol_quantile'] = round(rank / len(history) * 100, 1)

    # Δvol
    for i, s in enumerate(series):
        if i > 0:
            s['delta_vol'] = round(s['avg_vol'] - series[i-1]['avg_vol'], 2)
        else:
            s['delta_vol'] = 0.0

    # 波动率regime分类
    for s in series:
        q = s['vol_quantile']
        if q >= 80:
            s['vol_regime'] = '高波动'
        elif q >= 50:
            s['vol_regime'] = '中高波动'
        elif q >= 20:
            s['vol_regime'] = '中低波动'
        else:
            s['vol_regime'] = '低波动'

    latest = series[-1]
    print(f"  最新: avg_vol={latest['avg_vol']}% | 分位={latest['vol_quantile']}% | {latest['vol_regime']}")

    out = {
        'updated': series[-1]['date'],
        'vol_window': VOL_WINDOW,
        'quantile_window': QUANTILE_WINDOW,
        'series': series,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  输出: {OUT_PATH} ({len(series)}天)")
    print("✅ 完成")


if __name__ == '__main__':
    main()
