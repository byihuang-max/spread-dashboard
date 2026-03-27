#!/usr/bin/env python3
"""耐心资本 - 计算模块
基线分离 → 买卖判定 → 滚动成本 → 输出 CSV + JSON
"""
import json, csv, sys
from pathlib import Path
from collections import defaultdict
from statistics import median

import requests

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / 'raw_15min'
CSV_OUT = BASE_DIR / 'patient_capital.csv'
JSON_OUT = BASE_DIR / 'patient_capital.json'

TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TS_API = 'http://api.tushare.pro'

INDEX_ETFS = {
    '沪深300':   ['510300.SH', '159919.SZ'],
    '上证50':    ['510050.SH'],
    '创业板指':   ['159915.SZ'],
    '科创50':    ['588080.SH'],
    '创业板50':   ['159949.SZ'],
    '中证1000':  ['512100.SH', '159845.SZ', '560010.SH'],
    '中证500':   ['510500.SH', '512500.SH'],
    '中证A500':  ['159338.SZ', '159352.SZ', '159353.SZ', '560530.SH',
                  '159339.SZ', '563800.SH', '512050.SH', '159361.SZ'],
}

BASELINE_WINDOW = 20
ABNORMAL_THRESHOLD = 1.5

INDEX_TS_CODE = {
    '沪深300':  '399300.SZ',
    '上证50':   '000016.SH',
    '创业板指':  '399006.SZ',
    '科创50':   '000688.SH',
    '创业板50':  '399673.SZ',
    '中证1000': '000852.SH',
    '中证500':  '000905.SH',
    '中证A500': '932000.CSI',
}

STYLE_BUCKET = {
    '沪深300': '大盘权重',
    '上证50': '大盘权重',
    '中证A500': '中枢宽基',
    '中证500': '中盘扩散',
    '中证1000': '小盘扩散',
    '创业板指': '成长',
    '创业板50': '成长',
    '科创50': '成长',
}


def fetch_index_daily(ts_code, start_date='20230701'):
    print(f"  拉取指数日线 {ts_code}...", end='', flush=True)
    resp = requests.post(TS_API, json={
        'api_name': 'index_daily',
        'token': TS_TOKEN,
        'params': {'ts_code': ts_code, 'start_date': start_date, 'fields': 'trade_date,close'},
    }, timeout=30, proxies={'http': None, 'https': None})
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    fields = data.get('data', {}).get('fields', [])
    if not items:
        print(" 无数据")
        return {}
    di = {f: i for i, f in enumerate(fields)}
    result = {}
    for row in items:
        result[row[di['trade_date']]] = row[di['close']]
    print(f" {len(result)}天")
    return result


def fetch_all_index_daily():
    all_idx = {}
    for name, ts_code in INDEX_TS_CODE.items():
        all_idx[name] = fetch_index_daily(ts_code)
    return all_idx


def load_all_cache():
    all_data = {}
    for f in sorted(CACHE_DIR.glob('*.json')):
        with open(f) as fh:
            all_data[f.stem] = json.load(fh)
    return all_data


def aggregate_index_bars(day_data, index_name, etf_codes):
    time_buckets = defaultdict(lambda: {'vol': 0.0, 'amount': 0.0, 'opens': [], 'closes': []})
    for code in etf_codes:
        bars = day_data.get(code, [])
        for bar in bars:
            t = bar['trade_time']
            b = time_buckets[t]
            b['vol'] += bar.get('vol', 0) or 0
            b['amount'] += bar.get('amount', 0) or 0
            if bar.get('open'):
                b['opens'].append(bar['open'])
            if bar.get('close'):
                b['closes'].append(bar['close'])

    result = []
    for t in sorted(time_buckets.keys()):
        b = time_buckets[t]
        if not b['opens'] or not b['closes']:
            continue
        result.append({
            'time': t,
            'open': sum(b['opens']) / len(b['opens']),
            'close': sum(b['closes']) / len(b['closes']),
            'vol': b['vol'],
            'amount': b['amount'],
        })
    return result


def extract_time_slot(trade_time):
    return trade_time.split(' ')[1][:5]


def rolling_mean(values, window):
    out = []
    for i in range(len(values)):
        left = max(0, i - window + 1)
        arr = values[left:i + 1]
        out.append(sum(arr) / len(arr) if arr else 0)
    return out


def rolling_std(values, window):
    out = []
    for i in range(len(values)):
        left = max(0, i - window + 1)
        arr = values[left:i + 1]
        if not arr:
            out.append(0)
            continue
        mean = sum(arr) / len(arr)
        var = sum((x - mean) ** 2 for x in arr) / len(arr)
        out.append(var ** 0.5)
    return out


def calc_streak(results, key='net'):
    streak = 0
    for r in reversed(results):
        v = r.get(key, 0)
        if v > 0:
            streak = streak + 1 if streak >= 0 else 1
        elif v < 0:
            streak = streak - 1 if streak <= 0 else -1
        else:
            break
    return streak


def classify_intent(latest, results):
    net = latest.get('net', 0)
    pnl = latest.get('pnl', 0)
    z = latest.get('net_zscore', 0)
    buy_streak = calc_streak(results)

    if net > 0 and z >= 1.5 and buy_streak <= 1:
        return '脉冲托底'
    if buy_streak >= 3 and latest.get('net_5d', 0) > 0:
        if pnl > 10:
            return '高位承接'
        return '连续建仓'
    if buy_streak <= -3 and pnl > 8:
        return '有序退出'
    if abs(net) < 0.5:
        return '观望'
    return '中性换手'


def classify_pnl_behavior(latest):
    pnl = latest.get('pnl', 0)
    net = latest.get('net', 0)
    if pnl < -5 and net > 0:
        return '深度浮亏下继续托底'
    if pnl < 0 and net > 0:
        return '浮亏承接'
    if pnl > 10 and net > 0:
        return '盈利扩张仍在加仓'
    if pnl > 15 and net < 0:
        return '高浮盈兑现'
    if pnl < 0 and net < 0:
        return '浮亏下退守'
    return '盈亏与行为中性'


def classify_breadth(latest_snapshot):
    pos = latest_snapshot['positive_count']
    neg = latest_snapshot['negative_count']
    buckets = latest_snapshot['breadth_buckets']
    if pos >= 5:
        return '全面托底'
    if buckets.get('大盘权重', 0) >= 2 and pos >= 2 and buckets.get('小盘扩散', 0) == 0:
        return '权重维稳'
    if buckets.get('成长', 0) >= 2:
        return '成长定向支持'
    if buckets.get('小盘扩散', 0) >= 1 or buckets.get('中盘扩散', 0) >= 1:
        return '小盘扩散'
    if pos > 0 and neg > 0:
        return '分化操作'
    return '低活跃'


def build_market_strength(latest_snapshot):
    ratios = [v['latest'].get('net_to_turnover_pct', 0) for v in latest_snapshot['indices'].values() if v.get('latest')]
    if not ratios:
        return {'avg_ratio': 0, 'label': '无数据'}
    avg_ratio = sum(ratios) / len(ratios)
    if avg_ratio >= 12:
        label = '重手干预'
    elif avg_ratio >= 6:
        label = '中等强度'
    elif avg_ratio >= 2:
        label = '轻度参与'
    else:
        label = '低强度'
    return {'avg_ratio': round(avg_ratio, 2), 'label': label}


def build_concentration(latest_snapshot):
    items = []
    total = 0
    for name, info in latest_snapshot['indices'].items():
        latest = info.get('latest') or {}
        cum = latest.get('cum', 0) or 0
        total += max(cum, 0)
        items.append((name, max(cum, 0), STYLE_BUCKET.get(name, '其他')))
    items.sort(key=lambda x: x[1], reverse=True)
    top = []
    for name, cum, bucket in items:
        share = (cum / total * 100) if total > 0 else 0
        top.append({'name': name, 'cum': round(cum, 2), 'share_pct': round(share, 1), 'bucket': bucket})
    return {'total_cum': round(total, 2), 'top': top[:5]}


def build_daily_status(all_results):
    date_map = defaultdict(dict)
    for idx_name, results in all_results.items():
        for r in results:
            date_map[r['date']][idx_name] = r

    global_daily = {}
    for date, items in sorted(date_map.items()):
        positive_count = sum(1 for r in items.values() if r.get('net', 0) > 0)
        negative_count = sum(1 for r in items.values() if r.get('net', 0) < 0)
        breadth_buckets = defaultdict(int)
        for name, r in items.items():
            if r.get('net', 0) > 0:
                breadth_buckets[STYLE_BUCKET.get(name, '其他')] += 1

        total_net = round(sum(r.get('net', 0) for r in items.values()), 4)
        total_cum = round(sum(max(r.get('cum', 0), 0) for r in items.values()), 2)
        global_daily[date] = {
            'date': date,
            'indices': items,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'breadth_buckets': dict(breadth_buckets),
            'total_net': total_net,
            'total_cum': total_cum,
        }

    ordered_dates = sorted(global_daily.keys())
    snapshots = [global_daily[d] for d in ordered_dates]
    for i, snap in enumerate(snapshots):
        history = snapshots[:i + 1]
        total_net_hist = [x['total_net'] for x in history]
        mean = sum(total_net_hist[-20:]) / min(len(total_net_hist), 20)
        arr = total_net_hist[-20:]
        var = sum((x - mean) ** 2 for x in arr) / len(arr) if arr else 0
        std = var ** 0.5
        snap['intent'] = classify_intent(
            {'net': snap['total_net'], 'pnl': 0, 'net_zscore': ((snap['total_net'] - mean) / std) if std > 1e-8 else 0, 'net_5d': sum(total_net_hist[-5:])},
            [{'net': x['total_net']} for x in history]
        )
        snap['breadth_label'] = classify_breadth(snap)

    latest = snapshots[-1] if snapshots else None
    latest_state = {
        'intent': latest.get('intent') if latest else '无数据',
        'breadth': latest.get('breadth_label') if latest else '无数据',
        'market_strength': build_market_strength(latest) if latest else {'avg_ratio': 0, 'label': '无数据'},
        'concentration': build_concentration(latest) if latest else {'total_cum': 0, 'top': []},
    }
    return global_daily, latest_state


def enrich_results(index_name, results):
    if not results:
        return results
    turnover_series = [abs(r['buy']) + abs(r['sell']) for r in results]
    net_series = [r['net'] for r in results]
    buy_series = [r['buy'] for r in results]
    sell_series = [r['sell'] for r in results]

    net_ma5 = rolling_mean(net_series, 5)
    net_abs_ma20 = rolling_mean([abs(x) for x in net_series], 20)
    net_std20 = rolling_std(net_series, 20)

    for i, r in enumerate(results):
        turnover = turnover_series[i]
        net = net_series[i]
        net_z = (net - net_ma5[i]) / net_std20[i] if net_std20[i] > 1e-8 else 0
        r['turnover_proxy'] = round(turnover, 4)
        r['net_to_turnover_pct'] = round((abs(net) / turnover * 100) if turnover > 0 else 0, 2)
        r['net_ma5'] = round(net_ma5[i], 4)
        r['net_5d'] = round(sum(net_series[max(0, i - 4):i + 1]), 4)
        r['buy_5d'] = round(sum(buy_series[max(0, i - 4):i + 1]), 4)
        r['sell_5d'] = round(sum(sell_series[max(0, i - 4):i + 1]), 4)
        r['net_abs_ma20'] = round(net_abs_ma20[i], 4)
        r['net_zscore'] = round(net_z, 2)

    for i, r in enumerate(results):
        hist = results[:i + 1]
        r['intent'] = classify_intent(r, hist)
        r['pnl_behavior'] = classify_pnl_behavior(r)
        if r['net_zscore'] >= 1.5 and r['net'] > 0:
            r['flow_tag'] = '重手净买'
        elif r['net_zscore'] >= 1.5 and r['net'] < 0:
            r['flow_tag'] = '重手净卖'
        elif abs(r['net']) < 0.5:
            r['flow_tag'] = '低活跃'
        else:
            r['flow_tag'] = '常规'
    return results


def compute_patient_capital(all_data, index_name, etf_codes, index_daily=None):
    dates = sorted(all_data.keys())
    daily_bars = {}
    for d in dates:
        bars = aggregate_index_bars(all_data[d], index_name, etf_codes)
        if bars:
            daily_bars[d] = bars
    if not daily_bars:
        return []

    sorted_dates = sorted(daily_bars.keys())
    slot_history = defaultdict(list)
    cum_buy_amount = 0.0
    cum_buy_shares = 0.0
    cum_sell_shares = 0.0
    cost_price = 0.0
    results = []

    for date in sorted_dates:
        bars = daily_bars[date]
        day_buy = 0.0
        day_sell = 0.0
        abnormal_count = 0
        for bar in bars:
            slot = extract_time_slot(bar['time'])
            amount = bar['amount']
            history = slot_history.get(slot, [])
            recent = [h[1] for h in history[-BASELINE_WINDOW:]]
            if len(recent) >= 5:
                baseline = median(recent)
                excess = amount - baseline * ABNORMAL_THRESHOLD
                if excess > 0:
                    abnormal_count += 1
                    avg_price = (bar['open'] + bar['close']) / 2
                    excess_shares = excess / avg_price if avg_price > 0 else 0
                    if bar['close'] >= bar['open']:
                        day_buy += excess
                        cum_buy_amount += excess
                        cum_buy_shares += excess_shares
                    else:
                        day_sell += excess
                        cum_sell_shares += excess_shares
            slot_history[slot].append((date, amount))

        net_shares = cum_buy_shares - cum_sell_shares
        if net_shares > 0 and cum_buy_shares > 0:
            cost_price = cum_buy_amount / cum_buy_shares
        elif net_shares <= 0:
            cost_price = 0
            net_shares = 0

        close_price = bars[-1]['close'] if bars else 0
        cum_position = net_shares * close_price
        pnl = ((close_price - cost_price) / cost_price * 100) if cost_price > 0 else 0
        day_net = day_buy - day_sell

        idx_close = None
        cost_idx = None
        if index_daily and date in index_daily and close_price > 0:
            idx_close = index_daily[date]
            ratio = idx_close / close_price
            if cost_price > 0:
                cost_idx = round(cost_price * ratio, 2)

        results.append({
            'date': date,
            'buy': round(day_buy / 1e8, 4),
            'sell': round(day_sell / 1e8, 4),
            'net': round(day_net / 1e8, 4),
            'cum': round(cum_position / 1e8, 2),
            'cost': round(cost_price, 4),
            'close': round(close_price, 4),
            'pnl': round(pnl, 2),
            'bars': abnormal_count,
            'idx_close': round(idx_close, 2) if idx_close else None,
            'cost_idx': cost_idx,
            'style_bucket': STYLE_BUCKET.get(index_name, '其他'),
        })

    return enrich_results(index_name, results)


def run():
    print('加载缓存数据...')
    all_data = load_all_cache()
    if not all_data:
        print('[ERR] 无缓存数据，请先运行 patient_data.py', file=sys.stderr)
        sys.exit(1)

    print(f'已加载 {len(all_data)} 个交易日')
    print('\n拉取指数日线（用于折算指数点位）...')
    all_index_daily = fetch_all_index_daily()

    all_results = {}
    for index_name, etf_codes in INDEX_ETFS.items():
        print(f'  计算 {index_name} ({len(etf_codes)} ETFs)...', end='', flush=True)
        idx_daily = all_index_daily.get(index_name, {})
        results = compute_patient_capital(all_data, index_name, etf_codes, idx_daily)
        if results:
            all_results[index_name] = results
            latest = results[-1]
            print(f" {len(results)} 天, 最新累计: {latest['cum']}亿, 浮盈: {latest['pnl']}%, 状态: {latest['intent']}")
        else:
            print(' 无数据')

    global_daily, latest_state = build_daily_status(all_results)

    print(f'\n写入 CSV: {CSV_OUT}')
    with open(CSV_OUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            'date', 'index_name', 'daily_buy_amt', 'daily_sell_amt', 'daily_net_amt',
            'cum_position', 'cost_price', 'close_price', 'pnl_pct', 'abnormal_bars',
            'idx_close', 'cost_idx', 'intent', 'pnl_behavior', 'net_to_turnover_pct', 'net_zscore'
        ])
        for index_name, results in all_results.items():
            for r in results:
                writer.writerow([
                    r['date'], index_name, r['buy'], r['sell'], r['net'], r['cum'],
                    r['cost'], r['close'], r['pnl'], r['bars'], r.get('idx_close', ''),
                    r.get('cost_idx', ''), r.get('intent', ''), r.get('pnl_behavior', ''),
                    r.get('net_to_turnover_pct', ''), r.get('net_zscore', '')
                ])

    print(f'写入 JSON: {JSON_OUT}')
    from datetime import datetime
    json_data = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'state_summary': latest_state,
        'global_daily': list(global_daily.values()),
        'indices': {}
    }
    for index_name, results in all_results.items():
        json_data['indices'][index_name] = {
            'etfs': INDEX_ETFS[index_name],
            'daily': results,
            'latest': results[-1] if results else None,
        }

    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print('完成！')


if __name__ == '__main__':
    run()
