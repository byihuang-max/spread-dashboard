#!/usr/bin/env python3
"""强势股绝对收益拆解：beta贡献 + 情绪环境贡献 + 管理人alpha

Beta基准：中证1000（000852.SH）— 小盘股指数，更贴合强势股策略的实际持仓市值区间。
旧版用上证指数（大权重是银行石油，和打板策略不搭）。
"""

import json
import csv
import os
import requests
import time
from datetime import datetime
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
NAV_PATH = os.path.join(os.path.dirname(DIR), '..', 'size_spread', 'fund_nav', 'fund_nav_momentum-stock.json')
SENT_PATH = os.path.join(DIR, 'momentum_sentiment.json')
BENCHMARK_CACHE = os.path.join(DIR, '_cache', 'csi1000_daily.json')
OUT_CSV = os.path.join(DIR, 'momentum_return_decomp.csv')
OUT_JSON = os.path.join(DIR, 'momentum_return_decomp.json')

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
WINDOW = 60  # rolling OLS window


def tushare_call(api_name, params, fields='', retries=5):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': fields
            }, timeout=20)
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return [dict(zip(cols, row)) for row in data['data']['items']]
            return []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return []


def fetch_csi1000(start_date, end_date):
    """拉取中证1000日线，带缓存"""
    # 检查缓存
    if os.path.exists(BENCHMARK_CACHE):
        with open(BENCHMARK_CACHE) as f:
            cache = json.load(f)
        cached_dates = {r['trade_date'] for r in cache}
        # 如果缓存覆盖了需要的范围，直接用
        if start_date in cached_dates or all(
            d in cached_dates for d in [start_date, end_date]
        ):
            return {r['trade_date']: r['close'] for r in cache}

    print(f"  拉取中证1000日线 {start_date}~{end_date}...")
    data = tushare_call('index_daily', {
        'ts_code': '000852.SH',
        'start_date': start_date,
        'end_date': end_date
    }, fields='trade_date,close')

    if data:
        os.makedirs(os.path.dirname(BENCHMARK_CACHE), exist_ok=True)
        with open(BENCHMARK_CACHE, 'w') as f:
            json.dump(data, f)
        return {r['trade_date']: r['close'] for r in data}
    return {}


def ols_beta(y, x):
    """Hand-written OLS: y = a + b*x, return (a, b)"""
    n = len(y)
    if n < 2:
        return 0.0, 1.0
    sx = sum(x)
    sy = sum(y)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    sxx = sum(xi * xi for xi in x)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.0, 1.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a, b


def main():
    # 1. Load data
    with open(NAV_PATH) as f:
        nav_data = json.load(f)
    chart = nav_data['fund']['chart']
    dates_nav = chart['dates']  # '2025-03-21' format
    fund_nav = chart['fund_nav']

    # 拉取中证1000作为beta基准（替代上证指数）
    start_compact = dates_nav[0].replace('-', '')
    end_compact = dates_nav[-1].replace('-', '')
    csi1000 = fetch_csi1000(start_compact, end_compact)
    if not csi1000:
        print("警告: 无法获取中证1000数据，回退使用上证指数")
        index_source = {dates_nav[i].replace('-', ''): chart['index_nav'][i] for i in range(len(dates_nav))}
        benchmark_name = '上证指数'
    else:
        index_source = csi1000
        benchmark_name = '中证1000'
    print(f"  Beta基准: {benchmark_name} ({len(index_source)}天)")

    with open(SENT_PATH) as f:
        sent_data = json.load(f)
    sent_map = {}
    for d in sent_data['daily']:
        sent_map[d['date']] = {'sentiment': d['sentiment'], 'cycle_label': d['cycle_label']}

    # 2. Build daily returns — 只取基准和产品都有数据的日期
    records = []
    prev_fund = None
    prev_idx = None
    for i in range(len(dates_nav)):
        date_compact = dates_nav[i].replace('-', '')
        idx_close = index_source.get(date_compact)
        if idx_close is None:
            continue

        if prev_fund is not None and prev_idx is not None:
            fund_ret = (fund_nav[i] - prev_fund) / prev_fund
            idx_ret = (idx_close - prev_idx) / prev_idx
            s = sent_map.get(date_compact, {})
            records.append({
                'date': date_compact,
                'fund_return': fund_ret,
                'index_return': idx_ret,
                'sentiment': s.get('sentiment', None),
                'cycle_label': s.get('cycle_label', '—'),
            })

        prev_fund = fund_nav[i]
        prev_idx = idx_close

    # 3. Rolling OLS beta
    fund_rets = [r['fund_return'] for r in records]
    idx_rets = [r['index_return'] for r in records]
    for i, r in enumerate(records):
        start = max(0, i - WINDOW + 1)
        _, beta = ols_beta(fund_rets[start:i + 1], idx_rets[start:i + 1])
        r['beta'] = round(beta, 6)
        r['beta_contribution'] = round(beta * r['index_return'], 8)

    # 4. Excess over beta
    for r in records:
        r['excess_over_beta'] = r['fund_return'] - r['beta_contribution']

    # 5. Sentiment avg by cycle_label (保留供前端展示)
    cycle_excess = defaultdict(list)
    for r in records:
        if r['cycle_label'] and r['cycle_label'] != '—':
            cycle_excess[r['cycle_label']].append(r['excess_over_beta'])
    cycle_avg = {k: sum(v) / len(v) for k, v in cycle_excess.items()}

    # 6. 连续回归归因：excess = α + β1*(sentiment-50) + β2*Δsentiment
    # 计算 Δsentiment（日变化）
    for i, r in enumerate(records):
        if i > 0 and records[i-1].get('sentiment') is not None and r.get('sentiment') is not None:
            r['delta_sentiment'] = r['sentiment'] - records[i-1]['sentiment']
        else:
            r['delta_sentiment'] = 0.0

    valid = [(r['excess_over_beta'], r['sentiment'] - 50, r['delta_sentiment'])
             for r in records if r.get('sentiment') is not None]

    if len(valid) >= 10:
        n = len(valid)
        y = [v[0] for v in valid]
        x1 = [v[1] for v in valid]   # sentiment - 50
        x2 = [v[2] for v in valid]   # delta_sentiment
        # 两步OLS: Step1 excess ~ (sentiment-50), Step2 residual ~ delta_sentiment
        _, beta_sent = ols_beta(y, x1)
        resid1 = [y[i] - beta_sent * x1[i] for i in range(n)]
        _, beta_delta = ols_beta(resid1, x2)
        intercept = sum(resid1[i] - beta_delta * x2[i] for i in range(n)) / n
    else:
        beta_sent = 0.0
        beta_delta = 0.0
        intercept = 0.0

    # 每天情绪贡献 = β1*(sentiment-50) + β2*Δsentiment
    for r in records:
        if r.get('sentiment') is not None:
            s_centered = r['sentiment'] - 50
            ds = r.get('delta_sentiment', 0)
            r['sentiment_contribution'] = round(beta_sent * s_centered + beta_delta * ds, 8)
        else:
            r['sentiment_contribution'] = 0.0
        r['manager_alpha'] = round(r['fund_return'] - r['beta_contribution'] - r['sentiment_contribution'], 8)

    # 7. Cumulative returns (compounding)
    cum_fund = 0.0
    cum_beta = 0.0
    cum_sent = 0.0
    cum_alpha = 0.0
    for r in records:
        cum_fund += r['fund_return']
        cum_beta += r['beta_contribution']
        cum_sent += r['sentiment_contribution']
        cum_alpha += r['manager_alpha']
        r['cum_fund'] = round(cum_fund * 100, 4)
        r['cum_beta'] = round(cum_beta * 100, 4)
        r['cum_sentiment'] = round(cum_sent * 100, 4)
        r['cum_alpha'] = round(cum_alpha * 100, 4)

    # 8. Write CSV
    fields = ['date', 'fund_return', 'index_return', 'beta', 'beta_contribution',
              'cycle_label', 'sentiment', 'sentiment_contribution', 'manager_alpha',
              'cum_fund', 'cum_beta', 'cum_sentiment', 'cum_alpha']
    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in records:
            row = {k: r.get(k, '') for k in fields}
            # Round floats for CSV
            for k in ['fund_return', 'index_return']:
                if isinstance(row[k], float):
                    row[k] = round(row[k], 8)
            w.writerow(row)
    print(f"CSV written: {OUT_CSV} ({len(records)} rows)")

    # 9. Write JSON
    today = datetime.now().strftime('%Y-%m-%d')
    date_range = f"{records[0]['date']} ~ {records[-1]['date']}"
    total_ret = round(cum_fund * 100, 2)
    beta_total = round(cum_beta * 100, 2)
    sent_total = round(cum_sent * 100, 2)
    alpha_total = round(cum_alpha * 100, 2)
    avg_beta = round(sum(r['beta'] for r in records) / len(records), 4)
    cycle_avg_pct = {k: round(v * 100, 4) for k, v in cycle_avg.items()}

    daily_json = []
    for r in records:
        daily_json.append({
            'date': r['date'],
            'fund_return': round(r['fund_return'], 6),
            'index_return': round(r['index_return'], 6),
            'beta': r['beta'],
            'beta_contribution': round(r['beta_contribution'], 6),
            'cycle_label': r['cycle_label'],
            'sentiment': r['sentiment'],
            'sentiment_contribution': round(r['sentiment_contribution'], 6),
            'manager_alpha': round(r['manager_alpha'], 6),
            'cum_fund': r['cum_fund'],
            'cum_beta': r['cum_beta'],
            'cum_sentiment': r['cum_sentiment'],
            'cum_alpha': r['cum_alpha'],
        })

    out = {
        'updated': today,
        'date_range': date_range,
        'benchmark': benchmark_name,
        'summary': {
            'total_return': total_ret,
            'beta_total': beta_total,
            'sentiment_total': sent_total,
            'alpha_total': alpha_total,
            'avg_beta': avg_beta,
            'sentiment_beta': round(beta_sent, 6),
            'sentiment_delta_beta': round(beta_delta, 6),
            'cycle_avg_returns': cycle_avg_pct,
        },
        'daily': daily_json,
    }
    with open(OUT_JSON, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"JSON written: {OUT_JSON}")
    print(f"\nSummary:")
    print(f"  Total return: {total_ret}%")
    print(f"  Beta contribution: {beta_total}%")
    print(f"  Sentiment contribution: {sent_total}%")
    print(f"  Manager alpha: {alpha_total}%")
    print(f"  Avg beta: {avg_beta}")
    print(f"  Cycle avg returns: {cycle_avg_pct}")
    print(f"  Sentiment beta: {round(beta_sent, 6)}, Delta beta: {round(beta_delta, 6)}")


if __name__ == '__main__':
    main()
