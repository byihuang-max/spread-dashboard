#!/usr/bin/env python3
"""
模块一：股指套利（基差监控）
支持两种模式：
  --incremental  从 arb_cache.json 读取缓存数据（快速，推荐）
  无参数          全量从 API 拉取（兼容旧用法）
"""

import requests, json, time, os, sys, csv
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 配置 ============
TS_URL = 'https://api.tushare.pro'
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, 'mod1_index_arb.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod1_index_arb.csv')
CACHE_PATH = os.path.join(BASE_DIR, 'arb_cache.json')

LOOKBACK_DAYS = 30

CONTRACTS = {
    'IF': {'fut_code': 'IF.CFX', 'spot_code': '000300.SH', 'name': '沪深300'},
    'IH': {'fut_code': 'IH.CFX', 'spot_code': '000016.SH', 'name': '上证50'},
    'IC': {'fut_code': 'IC.CFX', 'spot_code': '000905.SH', 'name': '中证500'},
    'IM': {'fut_code': 'IM.CFX', 'spot_code': '000852.SH', 'name': '中证1000'},
}


def log(msg):
    print(msg, flush=True)


# ============ Tushare API ============
_last_call = 0

def ts_api(api_name, params, fields=None):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)

    body = {'api_name': api_name, 'token': TS_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields

    for attempt in range(3):
        try:
            _last_call = time.time()
            r = requests.post(TS_URL, json=body, timeout=60, proxies={'http': None, 'https': None})
            if not r.text:
                log(f'    [空响应, retry {attempt+1}]')
                time.sleep(3)
                continue
            data = r.json()
            if data.get('code') == 0 and data.get('data', {}).get('items'):
                cols = data['data']['fields']
                rows = data['data']['items']
                return [dict(zip(cols, row)) for row in rows]
            elif data.get('code') == -2001:
                log(f'    [限流, 等10s...]')
                time.sleep(10)
                continue
            else:
                msg = data.get('msg', '')
                if msg:
                    log(f'    [API: {msg}]')
                return []
        except Exception as e:
            log(f'    [异常: {e}, retry {attempt+1}]')
            time.sleep(3)
    return []


def get_trade_dates(n_days):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=n_days * 3)).strftime('%Y%m%d')
    rows = ts_api('trade_cal', {
        'exchange': 'SSE', 'start_date': start,
        'end_date': end, 'is_open': '1'
    }, fields='cal_date')
    if not rows:
        return []
    return sorted([r['cal_date'] for r in rows])[-n_days:]


# ============ 计算 ============

def compute_basis(dates, fut_map, spot_map):
    results = []
    for d in dates:
        fut = fut_map.get(d)
        spot = spot_map.get(d)
        if not fut or not spot:
            continue
        fc = fut.get('close')
        sc = spot.get('close')
        if not fc or not sc or sc == 0:
            continue

        basis = fc - sc
        basis_pct = basis / sc * 100
        annual_pct = basis_pct * 12

        results.append({
            'date': d,
            'fut_close': round(fc, 2),
            'spot_close': round(sc, 2),
            'basis': round(basis, 2),
            'basis_pct': round(basis_pct, 4),
            'annual_basis_pct': round(annual_pct, 2),
            'fut_vol': fut.get('vol', 0),
            'fut_amount': fut.get('amount', 0),
            'fut_oi': fut.get('oi', 0),
        })
    return results


# ============ 输出 ============

def write_output(all_data, dates):
    json_out = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'date_range': f'{dates[0]} ~ {dates[-1]}' if dates else '',
        'n_days': len(dates),
        'contracts': {},
        'summary': {},
    }

    for prefix, info in CONTRACTS.items():
        series = all_data.get(prefix, [])
        json_out['contracts'][prefix] = {
            'name': info['name'],
            'fut_code': info['fut_code'],
            'spot_code': info['spot_code'],
            'series': series,
        }

        if series:
            latest = series[-1]
            basis_pcts = [s['basis_pct'] for s in series]
            json_out['summary'][prefix] = {
                'name': info['name'],
                'latest_date': latest['date'],
                'latest_basis': latest['basis'],
                'latest_basis_pct': latest['basis_pct'],
                'latest_annual_pct': latest['annual_basis_pct'],
                'avg_basis_pct': round(sum(basis_pcts) / len(basis_pcts), 4),
                'max_basis_pct': round(max(basis_pcts), 4),
                'min_basis_pct': round(min(basis_pcts), 4),
                'fut_close': latest['fut_close'],
                'spot_close': latest['spot_close'],
            }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)

    csv_headers = [
        'date', 'contract', 'name', 'fut_close', 'spot_close',
        'basis', 'basis_pct', 'annual_basis_pct',
        'fut_vol', 'fut_amount', 'fut_oi',
    ]
    csv_rows = []
    for prefix, info in CONTRACTS.items():
        for row in all_data.get(prefix, []):
            csv_rows.append({
                'date': row['date'],
                'contract': prefix,
                'name': info['name'],
                'fut_close': row['fut_close'],
                'spot_close': row['spot_close'],
                'basis': row['basis'],
                'basis_pct': row['basis_pct'],
                'annual_basis_pct': row['annual_basis_pct'],
                'fut_vol': row.get('fut_vol', ''),
                'fut_amount': row.get('fut_amount', ''),
                'fut_oi': row.get('fut_oi', ''),
            })

    csv_rows.sort(key=lambda x: (x['date'], x['contract']))

    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(csv_rows)


# ============ 增量模式 ============

def run_incremental():
    """从 arb_cache.json 读取数据，直接计算输出"""
    log('=' * 50)
    log('模块一：股指套利（基差监控）[增量模式]')
    log('=' * 50)

    if not os.path.exists(CACHE_PATH):
        log('  ⚠️ arb_cache.json 不存在，请先运行 fetch_incremental.py')
        return

    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    trade_dates = cache.get('trade_dates', [])
    if not trade_dates:
        log('  ⚠️ 缓存中无交易日数据')
        return

    dates = trade_dates[-LOOKBACK_DAYS:]
    log(f'  分析区间: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)')

    all_data = {}
    for prefix, info in CONTRACTS.items():
        fut_map = cache.get('mod1_fut', {}).get(prefix, {})
        spot_map = cache.get('mod1_spot', {}).get(prefix, {})
        series = compute_basis(dates, fut_map, spot_map)
        all_data[prefix] = series
        log(f'  {prefix}({info["name"]}): {len(series)} 天')

    write_output(all_data, dates)

    log(f'\n✅ 模块一完成（增量模式）')
    log(f'  JSON: {OUT_JSON}')
    log(f'  CSV:  {OUT_CSV}')

    # 打印汇总
    end_date = dates[-1]
    log(f'\n{"─"*50}')
    log(f'📊 股指套利基差汇总 ({end_date})')
    log(f'{"─"*50}')
    for prefix, info in CONTRACTS.items():
        series = all_data.get(prefix, [])
        if series:
            latest = series[-1]
            basis_pcts = [s['basis_pct'] for s in series]
            avg = sum(basis_pcts) / len(basis_pcts)
            log(f'  {prefix}({info["name"]:>5s}): '
                f'基差={latest["basis"]:>+8.2f}  '
                f'基差率={latest["basis_pct"]:>+7.4f}%  '
                f'年化={latest["annual_basis_pct"]:>+7.2f}%  '
                f'30日均值={avg:>+7.4f}%')


# ============ 全量模式 ============

def run_full():
    """原始全量拉取模式"""
    log('=' * 50)
    log('模块一：股指套利（基差监控）[全量模式]')
    log('=' * 50)

    log('\n[1] 获取交易日...')
    dates = get_trade_dates(LOOKBACK_DAYS)
    if not dates:
        log('  ⚠️ 无法获取交易日')
        return
    start_date = dates[0]
    end_date = dates[-1]
    log(f'  {len(dates)} 个交易日: {start_date} ~ {end_date}')

    all_data = {}

    for prefix, info in CONTRACTS.items():
        log(f'\n[2] 拉取 {prefix} ({info["name"]})...')

        log(f'  期货 {info["fut_code"]}...')
        fut_rows = ts_api('fut_daily', {
            'ts_code': info['fut_code'],
            'start_date': start_date, 'end_date': end_date,
        }, fields='ts_code,trade_date,open,high,low,close,vol,amount,oi')
        fut_map = {}
        for r in (fut_rows or []):
            fut_map[r['trade_date']] = {
                'close': r.get('close'),
                'vol': r.get('vol', 0),
                'amount': r.get('amount', 0),
                'oi': r.get('oi', 0),
            }
        log(f'    {len(fut_map)} 天')

        log(f'  现货 {info["spot_code"]}...')
        spot_rows = ts_api('index_daily', {
            'ts_code': info['spot_code'],
            'start_date': start_date, 'end_date': end_date,
        }, fields='ts_code,trade_date,close')
        spot_map = {}
        for r in (spot_rows or []):
            spot_map[r['trade_date']] = {'close': r.get('close')}
        log(f'    {len(spot_map)} 天')

        series = compute_basis(dates, fut_map, spot_map)
        all_data[prefix] = series
        log(f'  基差序列: {len(series)} 天')

        if series:
            latest = series[-1]
            log(f'  最新: 期货={latest["fut_close"]} 现货={latest["spot_close"]} '
                f'基差={latest["basis"]} 基差率={latest["basis_pct"]:.4f}% '
                f'年化={latest["annual_basis_pct"]:.2f}%')

    log('\n[3] 输出...')
    write_output(all_data, dates)

    log(f'\n✅ 模块一完成（全量模式）')
    log(f'  JSON: {OUT_JSON}')
    log(f'  CSV:  {OUT_CSV}')

    end_date = dates[-1]
    log(f'\n{"─"*50}')
    log(f'📊 股指套利基差汇总 ({end_date})')
    log(f'{"─"*50}')
    for prefix, info in CONTRACTS.items():
        series = all_data.get(prefix, [])
        if series:
            latest = series[-1]
            basis_pcts = [s['basis_pct'] for s in series]
            avg = sum(basis_pcts) / len(basis_pcts)
            log(f'  {prefix}({info["name"]:>5s}): '
                f'基差={latest["basis"]:>+8.2f}  '
                f'基差率={latest["basis_pct"]:>+7.4f}%  '
                f'年化={latest["annual_basis_pct"]:>+7.2f}%  '
                f'30日均值={avg:>+7.4f}%')


# ============ 入口 ============

def main():
    if '--incremental' in sys.argv or '-i' in sys.argv:
        run_incremental()
    else:
        run_full()


if __name__ == '__main__':
    main()
