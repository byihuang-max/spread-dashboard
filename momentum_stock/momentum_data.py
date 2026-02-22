#!/usr/bin/env python3
"""
强势股情绪指标数据脚本（带缓存版）
从 Tushare limit_list_d 拉取涨跌停数据，本地缓存避免重复拉取
"""

import requests, json, time, os
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
OUTPUT_JSON = '/Users/apple/Desktop/fof_dashboard/momentum_stock/momentum_sentiment.json'
CACHE_DIR = '/Users/apple/Desktop/fof_dashboard/momentum_stock/_cache'
LOOKBACK_DAYS = 120

os.makedirs(CACHE_DIR, exist_ok=True)


def tushare_call(api_name, params, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': ''
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


def get_trade_dates(n_days=LOOKBACK_DAYS):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=n_days * 2)).strftime('%Y%m%d')
    data = tushare_call('trade_cal', {'exchange': 'SSE', 'start_date': start, 'end_date': end, 'is_open': '1'})
    if not data:
        return []
    return sorted([d['cal_date'] for d in data])[-n_days:]


def fetch_day_cached(trade_date):
    """拉取某日 U/D/Z 数据，有缓存直接读"""
    cache_file = os.path.join(CACHE_DIR, f'{trade_date}.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    ups = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'U'})
    time.sleep(0.2)
    downs = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'D'})
    time.sleep(0.2)
    zhas = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'Z'})
    time.sleep(0.2)

    result = {'U': ups, 'D': downs, 'Z': zhas}
    with open(cache_file, 'w') as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def compute_daily_metrics(trade_dates):
    daily = []
    prev_up_codes = set()
    prev_up_by_height = defaultdict(set)

    for i, td in enumerate(trade_dates):
        cached = os.path.exists(os.path.join(CACHE_DIR, f'{td}.json'))
        tag = '📦' if cached else '🌐'
        print(f"  [{i+1}/{len(trade_dates)}] {td} {tag}", end='', flush=True)

        data = fetch_day_cached(td)
        ups, downs, zhas = data['U'], data['D'], data['Z']

        up_count, down_count, zha_count = len(ups), len(downs), len(zhas)
        max_height = 0
        lianban_count = shouban_count = seal_zero_count = 0
        current_up_codes = set()
        current_up_by_height = defaultdict(set)

        for u in ups:
            ts_code = u.get('ts_code', '')
            lt = u.get('limit_times') or 1
            ot = u.get('open_times') or 0
            current_up_codes.add(ts_code)
            current_up_by_height[lt].add(ts_code)
            if lt > max_height: max_height = lt
            if lt > 1: lianban_count += 1
            else: shouban_count += 1
            if ot == 0: seal_zero_count += 1

        promotion_rate = 0
        if prev_up_codes:
            continued = current_up_codes & prev_up_codes
            promotion_rate = len(continued) / len(prev_up_codes) * 100

        rate_1to2 = 0
        if prev_up_by_height.get(1):
            prev_sb = prev_up_by_height[1]
            today_lb = {u['ts_code'] for u in ups if (u.get('limit_times') or 1) >= 2}
            promoted = prev_sb & today_lb
            rate_1to2 = len(promoted) / len(prev_sb) * 100 if prev_sb else 0

        zha_rate = zha_count / max(up_count + zha_count, 1) * 100
        ud_ratio = up_count / max(down_count, 1)
        seal_quality = seal_zero_count / max(up_count, 1) * 100

        daily.append({
            'date': td, 'up_count': up_count, 'down_count': down_count,
            'zha_count': zha_count, 'max_height': max_height,
            'lianban_count': lianban_count, 'shouban_count': shouban_count,
            'promotion_rate': round(promotion_rate, 2),
            'rate_1to2': round(rate_1to2, 2),
            'zha_rate': round(zha_rate, 2),
            'ud_ratio': round(ud_ratio, 2),
            'seal_quality': round(seal_quality, 2),
        })
        print(f" U={up_count} D={down_count} Z={zha_count} H={max_height}")

        prev_up_codes = current_up_codes
        prev_up_by_height = current_up_by_height

    return daily


def normalize_series(values, window=60):
    result = []
    for i, v in enumerate(values):
        w = values[max(0, i-window+1):i+1]
        mn, mx = min(w), max(w)
        result.append(round((v-mn)/(mx-mn)*100, 2) if mx != mn else 50.0)
    return result


def compute_sentiment_index(daily):
    h = normalize_series([d['max_height'] for d in daily])
    p = normalize_series([d['promotion_rate'] for d in daily])
    z = normalize_series([100 - d['zha_rate'] for d in daily])
    u = normalize_series([d['ud_ratio'] for d in daily])
    s = normalize_series([d['seal_quality'] for d in daily])
    sent = [round(0.25*h[i]+0.25*p[i]+0.20*z[i]+0.15*u[i]+0.15*s[i], 2) for i in range(len(daily))]
    return sent, h, p, z, u, s


def label_cycle(sentiment):
    labels = []
    for i, v in enumerate(sentiment):
        if i < 2:
            labels.append('—'); continue
        prev, prev2 = sentiment[i-1], sentiment[i-2]
        d, d2 = v - prev, prev - prev2
        if v < 20: labels.append('冰点')
        elif v < 35 and prev < 30 and d > 0: labels.append('回暖')
        elif v > 60 and d > 0: labels.append('加速')
        elif v > 50 and d < 0: labels.append('分歧')
        elif v < 40 and prev > 45 and d < 0 and d2 < 0: labels.append('退潮')
        elif d > 3: labels.append('回暖')
        elif d < -3: labels.append('退潮')
        else: labels.append('震荡')
    return labels


def main():
    print("🔥 强势股情绪指标数据生成（带缓存）")
    dates = get_trade_dates(LOOKBACK_DAYS)
    if not dates:
        print("❌ 无法获取交易日历"); return
    print(f"📅 {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    daily = compute_daily_metrics(dates)
    if not daily:
        print("❌ 无数据"); return

    sent, h, p, z, u, s = compute_sentiment_index(daily)
    labels = label_cycle(sent)

    output = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'date_range': f"{daily[0]['date']} ~ {daily[-1]['date']}",
            'count': len(daily),
            'weights': {'height':0.25,'promotion':0.25,'anti_zha':0.20,'ud_ratio':0.15,'seal_quality':0.15}
        },
        'daily': [{
            **d, 'sentiment': sent[i], 'h_norm': h[i], 'p_norm': p[i],
            'z_norm': z[i], 'u_norm': u[i], 's_norm': s[i], 'cycle_label': labels[i]
        } for i, d in enumerate(daily)]
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(daily)} 天 → {OUTPUT_JSON}")
    print(f"   最新: {daily[-1]['date']} 情绪={sent[-1]} 周期={labels[-1]}")


if __name__ == '__main__':
    main()
