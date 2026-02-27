#!/usr/bin/env python3
"""耐心资本 - 数据拉取模块（v2 批量版）
按月批量拉取ETF 15min K线，大幅减少API调用次数。
缓存按 日期.json 存储。
"""
import requests, json, time, os, sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# ═══ 配置 ═══
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TS_API = 'http://api.tushare.pro'
START_DATE = '2023-07-03'
CACHE_DIR = Path(__file__).parent / 'raw_15min'
CACHE_DIR.mkdir(exist_ok=True)

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

ALL_ETFS = []
for etfs in INDEX_ETFS.values():
    ALL_ETFS.extend(etfs)


def ts_query(api_name, params, fields='', retries=3):
    for attempt in range(retries):
        try:
            r = requests.post(TS_API, json={
                'api_name': api_name, 'token': TS_TOKEN,
                'params': params, 'fields': fields,
            }, timeout=60)
            d = r.json()
            if d.get('code') == 0:
                data = d.get('data', {})
                cols = data.get('fields', [])
                items = data.get('items', [])
                return [dict(zip(cols, row)) for row in items]
            elif '每分钟' in d.get('msg', '') or '每小时' in d.get('msg', ''):
                wait = 15 if '每分钟' in d.get('msg', '') else 60
                print(f"\n  [限频] {d.get('msg','')}, 等{wait}秒...", file=sys.stderr, end='', flush=True)
                time.sleep(wait)
            else:
                print(f"\n  [ERR] {api_name}: {d.get('msg','')}", file=sys.stderr)
                return []
        except Exception as e:
            print(f"\n  [ERR] attempt {attempt+1}: {e}", file=sys.stderr)
            time.sleep(5)
    return []


def get_trade_dates(start, end):
    rows = ts_query('trade_cal', {
        'exchange': 'SSE',
        'start_date': start.replace('-', ''),
        'end_date': end.replace('-', ''),
        'is_open': '1',
    }, fields='cal_date')
    return sorted([r['cal_date'] for r in rows]) if rows else []


def generate_month_ranges(start_date, end_date):
    """生成月份区间列表: [(start, end), ...]"""
    from datetime import date
    s = date(int(start_date[:4]), int(start_date[4:6]), int(start_date[6:8]))
    e = date(int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8]))
    ranges = []
    cur = s
    while cur <= e:
        month_end = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if month_end > e:
            month_end = e
        ranges.append((cur.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d')))
        cur = (month_end + timedelta(days=1))
    return ranges


def fetch_etf_month(ts_code, start, end):
    """拉取一只ETF一个月的15min数据（一次API调用）"""
    rows = ts_query('stk_mins', {
        'ts_code': ts_code,
        'freq': '15min',
        'start_date': f'{start} 09:00:00',
        'end_date': f'{end} 15:30:00',
    })
    return rows or []


def load_cache(date_str):
    f = CACHE_DIR / f"{date_str}.json"
    if f.exists():
        with open(f) as fh:
            return json.load(fh)
    return None


def save_cache(date_str, data):
    f = CACHE_DIR / f"{date_str}.json"
    with open(f, 'w') as fh:
        json.dump(data, fh, ensure_ascii=False)


def merge_into_daily(existing, new_bars):
    """将bar列表按日期分组，合并到existing dict中"""
    for bar in new_bars:
        # trade_time: "2023-07-03 09:45:00"
        date_str = bar['trade_time'][:10].replace('-', '')
        ts_code = bar['ts_code']
        if date_str not in existing:
            existing[date_str] = {}
        if ts_code not in existing[date_str]:
            existing[date_str][ts_code] = []
        existing[date_str][ts_code].append(bar)


def fetch_all(force_recent_days=3):
    today = datetime.now().strftime('%Y%m%d')
    start = START_DATE.replace('-', '')
    trade_dates = get_trade_dates(START_DATE, today)
    if not trade_dates:
        print("[ERR] 无法获取交易日列表", file=sys.stderr)
        return {}

    print(f"交易日范围: {trade_dates[0]} ~ {trade_dates[-1]}, 共 {len(trade_dates)} 天")

    # 检查哪些日期已有缓存
    cached_dates = set()
    for f in CACHE_DIR.glob('*.json'):
        cached_dates.add(f.stem)

    # 确定要拉的日期（排除已缓存的，但最近N天强制重拉）
    force_dates = set(trade_dates[-force_recent_days:]) if force_recent_days > 0 else set()
    missing_dates = set()
    for d in trade_dates:
        if d not in cached_dates or d in force_dates:
            missing_dates.add(d)

    if not missing_dates:
        print("所有数据已缓存，无需拉取")
        return _load_all_cached(trade_dates)

    print(f"需要拉取: {len(missing_dates)} 天（已缓存 {len(cached_dates)} 天）")

    # 按月批量拉取
    month_ranges = generate_month_ranges(trade_dates[0], trade_dates[-1])
    
    # 过滤：只拉包含missing_dates的月份
    months_needed = set()
    for d in missing_dates:
        months_needed.add(d[:6])

    collected = {}  # date -> {ts_code -> [bars]}

    total_calls = 0
    for ms, me in month_ranges:
        month_key = ms[:7].replace('-', '')[:6]
        if month_key not in months_needed:
            continue
        
        print(f"\n  月份 {ms[:7]}:", end='', flush=True)
        for i, ts_code in enumerate(ALL_ETFS):
            bars = fetch_etf_month(ts_code, ms, me)
            total_calls += 1
            if bars:
                merge_into_daily(collected, bars)
                print(f" {ts_code.split('.')[0]}({len(bars)})", end='', flush=True)
            time.sleep(0.18)  # 控制频率

    print(f"\n\nAPI调用总数: {total_calls}")

    # 保存到缓存
    saved = 0
    for date_str, day_data in collected.items():
        if date_str in missing_dates:
            # 合并：如果已有缓存且不是force，保留已有的
            existing = load_cache(date_str) if date_str not in force_dates else None
            if existing:
                existing.update(day_data)
                save_cache(date_str, existing)
            else:
                save_cache(date_str, day_data)
            saved += 1

    print(f"新增/更新缓存: {saved} 天")
    return _load_all_cached(trade_dates)


def _load_all_cached(trade_dates):
    """加载所有已缓存的交易日数据"""
    all_data = {}
    for d in trade_dates:
        cached = load_cache(d)
        if cached:
            all_data[d] = cached
    return all_data


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--force-recent', type=int, default=3,
                        help='强制重拉最近N天（默认3）')
    args = parser.parse_args()

    data = fetch_all(force_recent_days=args.force_recent)
    print(f"\n完成，缓存文件数: {len(list(CACHE_DIR.glob('*.json')))}")
