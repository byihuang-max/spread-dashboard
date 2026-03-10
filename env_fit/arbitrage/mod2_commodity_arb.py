#!/usr/bin/env python3
"""
模块二：商品套利（跨品种比价 + 跨期价差）
从 Tushare 拉取主要商品期货连续合约数据，计算：

A. 跨品种比价（4组经典套利对）：
   - 螺纹/铁矿比值（钢厂利润代理）
   - 豆油/棕榈油比值（油脂替代）
   - 铜/铝比值（有色强弱）
   - 原油/燃油比值（裂解价差代理）

B. 跨期价差（近月-远月）：
   - 从 commodity_cta/fut_daily.csv 复用连续合约数据
   - 用连续合约 close 与 pre_close 的关系推算 contango/backwardation 状态

输出：mod2_commodity_arb.json + mod2_commodity_arb.csv（近30个交易日）
"""

import requests, json, time, os, sys, csv, math
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 配置 ============
TS_URL = 'https://api.tushare.pro'
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, 'mod2_commodity_arb.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod2_commodity_arb.csv')

# commodity_cta 的期货数据
CTA_FUT_CSV = os.path.join(BASE_DIR, '..', 'commodity_cta', 'fut_daily.csv')

LOOKBACK_DAYS = 30

# 跨品种套利对：(名称, 分子品种, 分母品种, 说明)
SPREAD_PAIRS = [
    ('螺纹/铁矿', 'RB', 'I', '钢厂利润代理：螺纹钢价格÷铁矿石价格'),
    ('豆油/棕榈油', 'Y', 'P', '油脂替代：豆油÷棕榈油，高位时棕榈油相对便宜'),
    ('铜/铝', 'CU', 'AL', '有色强弱：铜÷铝，反映经济预期分化'),
    ('原油/燃油', 'SC', 'FU', '裂解价差代理：原油÷燃油，反映炼化利润'),
]


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


# ============ 数据加载 ============

def load_cta_fut_csv():
    """从 commodity_cta/fut_daily.csv 加载期货数据"""
    path = os.path.realpath(CTA_FUT_CSV)
    if not os.path.exists(path):
        log(f'  ⚠️ {path} 不存在，将从 API 拉取')
        return {}

    series = defaultdict(dict)  # {symbol: {date: {close, vol, amount, oi}}}
    with open(path, 'r', newline='', encoding='gb18030') as f:
        for row in csv.DictReader(f):
            sym = row.get('symbol', '')
            dt = row.get('trade_date', '')
            close = row.get('close', '')
            if not sym or not dt or not close:
                continue
            series[sym][dt] = {
                'close': float(close),
                'vol': float(row.get('vol', 0) or 0),
                'amount': float(row.get('amount', 0) or 0),
                'oi': float(row.get('oi', 0) or 0),
            }
    log(f'  从 commodity_cta/fut_daily.csv 加载: {len(series)} 品种')
    return dict(series)


def fetch_fut_from_api(symbol, start_date, end_date):
    """从 API 拉取单品种连续合约"""
    # 确定交易所后缀
    exchange_map = {
        'RB': 'SHF', 'HC': 'SHF', 'I': 'DCE', 'J': 'DCE', 'JM': 'DCE',
        'CU': 'SHF', 'AL': 'SHF', 'ZN': 'SHF', 'NI': 'SHF', 'SN': 'SHF',
        'AU': 'SHF', 'AG': 'SHF',
        'SC': 'INE', 'FU': 'SHF', 'LU': 'INE', 'BU': 'SHF',
        'MA': 'ZCE', 'TA': 'ZCE', 'SA': 'ZCE', 'FG': 'ZCE',
        'PP': 'DCE', 'L': 'DCE', 'V': 'DCE', 'EB': 'DCE', 'EG': 'DCE',
        'Y': 'DCE', 'P': 'DCE', 'M': 'DCE', 'A': 'DCE',
        'CF': 'ZCE', 'SR': 'ZCE', 'OI': 'ZCE', 'RM': 'ZCE',
        'C': 'DCE', 'CS': 'DCE', 'JD': 'DCE', 'LH': 'DCE',
        'RU': 'SHF', 'NR': 'INE', 'SP': 'SHF', 'SS': 'SHF',
        'PG': 'DCE', 'PF': 'DCE', 'PX': 'ZCE',
    }
    exch = exchange_map.get(symbol, 'SHF')
    ts_code = f'{symbol}.{exch}'

    rows = ts_api('fut_daily', {
        'ts_code': ts_code,
        'start_date': start_date,
        'end_date': end_date,
    }, fields='ts_code,trade_date,close,vol,amount,oi')

    result = {}
    for r in (rows or []):
        result[r['trade_date']] = {
            'close': r.get('close'),
            'vol': r.get('vol', 0),
            'amount': r.get('amount', 0),
            'oi': r.get('oi', 0),
        }
    return result


# ============ 计算 ============

def compute_spread_ratio(dates, series_a, series_b):
    """计算比价序列：A/B"""
    results = []
    ratios = []
    for d in dates:
        a = series_a.get(d)
        b = series_b.get(d)
        if not a or not b:
            continue
        ca = a.get('close')
        cb = b.get('close')
        if not ca or not cb or cb == 0:
            continue
        ratio = ca / cb
        ratios.append(ratio)
        results.append({
            'date': d,
            'close_a': round(ca, 2),
            'close_b': round(cb, 2),
            'ratio': round(ratio, 4),
        })

    # 加上分位数（基于当前窗口）
    if ratios:
        sorted_r = sorted(ratios)
        for row in results:
            r = row['ratio']
            pctile = sum(1 for x in sorted_r if x <= r) / len(sorted_r)
            row['pctile'] = round(pctile, 4)

        # 20日均值和标准差
        recent = ratios[-20:] if len(ratios) >= 20 else ratios
        mean = sum(recent) / len(recent)
        std = math.sqrt(sum((x - mean)**2 for x in recent) / len(recent)) if len(recent) > 1 else 0
        for row in results:
            row['z_score'] = round((row['ratio'] - mean) / std, 4) if std > 0 else 0

    return results


# ============ 输出 ============

def write_output(spread_data, dates):
    """输出 JSON + CSV"""

    # === JSON ===
    json_out = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'date_range': f'{dates[0]} ~ {dates[-1]}' if dates else '',
        'n_days': len(dates),
        'spreads': {},
        'summary': {},
    }

    for name, sym_a, sym_b, desc in SPREAD_PAIRS:
        key = f'{sym_a}_{sym_b}'
        series = spread_data.get(key, [])
        json_out['spreads'][key] = {
            'name': name,
            'symbol_a': sym_a,
            'symbol_b': sym_b,
            'description': desc,
            'series': series,
        }

        if series:
            latest = series[-1]
            all_ratios = [s['ratio'] for s in series]
            json_out['summary'][key] = {
                'name': name,
                'latest_date': latest['date'],
                'latest_ratio': latest['ratio'],
                'latest_z_score': latest.get('z_score', 0),
                'latest_pctile': latest.get('pctile', 0),
                'avg_ratio': round(sum(all_ratios) / len(all_ratios), 4),
                'max_ratio': round(max(all_ratios), 4),
                'min_ratio': round(min(all_ratios), 4),
                'close_a': latest['close_a'],
                'close_b': latest['close_b'],
            }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)

    # === CSV ===
    csv_headers = [
        'date', 'pair', 'name', 'symbol_a', 'symbol_b',
        'close_a', 'close_b', 'ratio', 'pctile', 'z_score',
    ]
    csv_rows = []
    for name, sym_a, sym_b, desc in SPREAD_PAIRS:
        key = f'{sym_a}_{sym_b}'
        for row in spread_data.get(key, []):
            csv_rows.append({
                'date': row['date'],
                'pair': key,
                'name': name,
                'symbol_a': sym_a,
                'symbol_b': sym_b,
                'close_a': row['close_a'],
                'close_b': row['close_b'],
                'ratio': row['ratio'],
                'pctile': row.get('pctile', ''),
                'z_score': row.get('z_score', ''),
            })

    csv_rows.sort(key=lambda x: (x['date'], x['pair']))

    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(csv_rows)


# ============ 主流程 ============

def main():
    log('=' * 50)
    log('模块二：商品套利（跨品种比价）')
    log('=' * 50)

    # 1. 交易日
    log('\n[1] 获取交易日...')
    dates = get_trade_dates(LOOKBACK_DAYS)
    if not dates:
        log('  ⚠️ 无法获取交易日')
        return
    start_date = dates[0]
    end_date = dates[-1]
    log(f'  {len(dates)} 个交易日: {start_date} ~ {end_date}')

    # 2. 加载已有数据
    log('\n[2] 加载数据...')
    cta_data = load_cta_fut_csv()

    # 收集需要的品种
    needed_symbols = set()
    for _, sym_a, sym_b, _ in SPREAD_PAIRS:
        needed_symbols.add(sym_a)
        needed_symbols.add(sym_b)

    # 检查哪些品种在 cta_data 中有足够数据
    symbol_data = {}
    for sym in needed_symbols:
        if sym in cta_data:
            # 检查日期覆盖
            available = sum(1 for d in dates if d in cta_data[sym])
            if available >= len(dates) * 0.8:
                symbol_data[sym] = cta_data[sym]
                log(f'  {sym}: 从 CSV 复用 ({available}/{len(dates)} 天)')
                continue

        # 从 API 拉
        log(f'  {sym}: 从 API 拉取...')
        symbol_data[sym] = fetch_fut_from_api(sym, start_date, end_date)
        log(f'    {len(symbol_data[sym])} 天')

    # 3. 计算比价
    log('\n[3] 计算跨品种比价...')
    spread_data = {}
    for name, sym_a, sym_b, desc in SPREAD_PAIRS:
        key = f'{sym_a}_{sym_b}'
        series_a = symbol_data.get(sym_a, {})
        series_b = symbol_data.get(sym_b, {})
        series = compute_spread_ratio(dates, series_a, series_b)
        spread_data[key] = series
        log(f'  {name}: {len(series)} 天')

    # 4. 输出
    log('\n[4] 输出...')
    write_output(spread_data, dates)

    log(f'\n✅ 模块二完成')
    log(f'  JSON: {OUT_JSON}')
    log(f'  CSV:  {OUT_CSV}')

    # 打印汇总
    log(f'\n{"─"*55}')
    log(f'📊 商品套利比价汇总 ({end_date})')
    log(f'{"─"*55}')
    for name, sym_a, sym_b, desc in SPREAD_PAIRS:
        key = f'{sym_a}_{sym_b}'
        series = spread_data.get(key, [])
        if series:
            latest = series[-1]
            all_ratios = [s['ratio'] for s in series]
            avg = sum(all_ratios) / len(all_ratios)
            log(f'  {name:>8s}: '
                f'比值={latest["ratio"]:.4f}  '
                f'Z={latest.get("z_score", 0):>+6.2f}  '
                f'分位={latest.get("pctile", 0):.0%}  '
                f'30日均值={avg:.4f}')


if __name__ == '__main__':
    main()
