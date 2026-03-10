#!/usr/bin/env python3
"""
商品CTA策略环境 — 数据层（CSV增量模式）
从 Tushare fut_daily 拉取全市场期货连续合约数据

增量策略：
- fut_daily.csv 存基础行情（每日每品种连续合约）
- 每次只拉 CSV 中没有的新日期
- 首次从 _cache/ 迁移已有数据
- mod1/2/3 从 CSV 读数据计算（不再各自拉API）
"""

import requests, json, time, os, sys, csv, re, glob
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, '_cache')
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
LOOKBACK_DAYS = 150

os.makedirs(CACHE_DIR, exist_ok=True)

CONT_RE = re.compile(r'^([A-Z]+)\.([A-Z]+)$')

ALL_SYMBOLS = set([
    'RB','HC','I','J','JM','SF','SM','SS',
    'CU','AL','ZN','PB','NI','SN','BC','AO','SI',
    'AU','AG',
    'SC','FU','LU','BU','MA','EG','EB','TA','PP','L','V','PF','SA','FG','UR','PX','SP','RU','NR','BR','PG',
    'A','B','M','Y','P','OI','RM','CF','CY','SR','C','CS','JD','LH','AP','CJ','PK','WH','RI','RR',
])

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

CSV_HEADERS = ['trade_date','symbol','sector','ts_code','open','high','low','close','pre_close','vol','amount','oi']

def log(msg):
    print(msg, flush=True)


# ═══ Tushare API ═══

def tushare_call(api_name, params, fields='', retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': fields
            }, timeout=30, proxies={'http': None, 'https': None})
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
    data = tushare_call('trade_cal', {
        'exchange': 'SSE', 'start_date': start,
        'end_date': end, 'is_open': '1'
    })
    if not data:
        return []
    return sorted([d['cal_date'] for d in data])[-n_days:]


# ═══ CSV 工具 ═══

def read_csv_dates(path):
    if not os.path.exists(path):
        return set()
    with open(path, 'r', newline='', encoding='gb18030') as f:
        reader = csv.DictReader(f)
        return set(row['trade_date'] for row in reader)

def write_csv(path, headers, rows):
    with open(path, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

def append_csv(path, headers, rows):
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, 'a', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)

def read_full_csv():
    """读取完整CSV，返回行列表"""
    if not os.path.exists(FUT_CSV):
        return []
    with open(FUT_CSV, 'r', newline='', encoding='gb18030') as f:
        return list(csv.DictReader(f))


# ═══ 从 _cache 迁移 ═══

def migrate_from_cache():
    """从 _cache/ 目录迁移已有数据到 CSV"""
    if os.path.exists(FUT_CSV) and os.path.getsize(FUT_CSV) > 100:
        return True

    log("  从 _cache/ 迁移到 CSV...")
    all_rows = []

    # old format: {date}_all.json
    for f in sorted(glob.glob(os.path.join(CACHE_DIR, '*_all.json'))):
        dt = os.path.basename(f).replace('_all.json', '')
        with open(f) as fh:
            data = json.load(fh)
        for r in data:
            m = CONT_RE.match(r.get('ts_code', ''))
            if not m:
                continue
            sym = m.group(1)
            if sym not in ALL_SYMBOLS:
                continue
            if not r.get('close'):
                continue
            all_rows.append({
                'trade_date': dt,
                'symbol': sym,
                'sector': SYMBOL_SECTOR.get(sym, '其他'),
                'ts_code': r.get('ts_code', ''),
                'open': r.get('open', ''),
                'high': r.get('high', ''),
                'low': r.get('low', ''),
                'close': r.get('close', ''),
                'pre_close': r.get('pre_close', ''),
                'vol': r.get('vol', ''),
                'amount': r.get('amount', ''),
                'oi': r.get('oi', ''),
            })

    # new format: fut_daily_{date}.json
    existing_dates = set(r['trade_date'] for r in all_rows)
    for f in sorted(glob.glob(os.path.join(CACHE_DIR, 'fut_daily_*.json'))):
        dt = os.path.basename(f).replace('fut_daily_', '').replace('.json', '')
        if dt in existing_dates:
            continue
        with open(f) as fh:
            data = json.load(fh)
        for r in data:
            sym = r.get('symbol', '')
            if not sym:
                m = CONT_RE.match(r.get('ts_code', ''))
                if m:
                    sym = m.group(1)
            if sym not in ALL_SYMBOLS or not r.get('close'):
                continue
            all_rows.append({
                'trade_date': dt,
                'symbol': sym,
                'sector': r.get('sector', SYMBOL_SECTOR.get(sym, '其他')),
                'ts_code': r.get('ts_code', ''),
                'open': r.get('open', ''),
                'high': r.get('high', ''),
                'low': r.get('low', ''),
                'close': r.get('close', ''),
                'pre_close': r.get('pre_close', ''),
                'vol': r.get('vol', ''),
                'amount': r.get('amount', ''),
                'oi': r.get('oi', ''),
            })

    if all_rows:
        all_rows.sort(key=lambda x: (x['trade_date'], x['symbol']))
        write_csv(FUT_CSV, CSV_HEADERS, all_rows)
        dates = set(r['trade_date'] for r in all_rows)
        syms = set(r['symbol'] for r in all_rows)
        log(f"    fut_daily.csv: {len(all_rows)} 行, {len(dates)} 天, {len(syms)} 品种")
        return True

    return False


# ═══ 增量拉取 ═══

def fetch_day(trade_date):
    """拉取某日全市场期货日线，返回连续合约行列表"""
    # 先检查 cache
    for pattern in [f'{trade_date}_all.json', f'fut_daily_{trade_date}.json']:
        cache_file = os.path.join(CACHE_DIR, pattern)
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                data = json.load(f)
            rows = []
            for r in data:
                sym = r.get('symbol', '')
                if not sym:
                    m = CONT_RE.match(r.get('ts_code', ''))
                    if m:
                        sym = m.group(1)
                if sym in ALL_SYMBOLS and r.get('close'):
                    rows.append({
                        'trade_date': trade_date,
                        'symbol': sym,
                        'sector': r.get('sector', SYMBOL_SECTOR.get(sym, '其他')),
                        'ts_code': r.get('ts_code', ''),
                        'open': r.get('open', ''),
                        'high': r.get('high', ''),
                        'low': r.get('low', ''),
                        'close': r.get('close', ''),
                        'pre_close': r.get('pre_close', ''),
                        'vol': r.get('vol', ''),
                        'amount': r.get('amount', ''),
                        'oi': r.get('oi', ''),
                    })
            return rows

    # 从 API 拉
    data = tushare_call('fut_daily', {'trade_date': trade_date},
                        fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount,oi')
    if not data:
        return []

    rows = []
    cache_rows = []
    for r in data:
        m = CONT_RE.match(r.get('ts_code', ''))
        if not m:
            continue
        sym = m.group(1)
        if sym not in ALL_SYMBOLS or not r.get('close'):
            continue
        r['symbol'] = sym
        r['sector'] = SYMBOL_SECTOR.get(sym, '其他')
        cache_rows.append(r)
        rows.append({
            'trade_date': trade_date,
            'symbol': sym,
            'sector': SYMBOL_SECTOR.get(sym, '其他'),
            'ts_code': r.get('ts_code', ''),
            'open': r.get('open', ''),
            'high': r.get('high', ''),
            'low': r.get('low', ''),
            'close': r.get('close', ''),
            'pre_close': r.get('pre_close', ''),
            'vol': r.get('vol', ''),
            'amount': r.get('amount', ''),
            'oi': r.get('oi', ''),
        })

    # 写 cache
    cache_file = os.path.join(CACHE_DIR, f'{trade_date}_all.json')
    with open(cache_file, 'w') as f:
        json.dump(cache_rows, f, ensure_ascii=False)

    return rows


# ═══ 主流程 ═══

def main():
    log("=" * 50)
    log("商品CTA — 数据层（CSV增量模式）")
    log("=" * 50)

    # 0. 迁移
    log("\n[0] 检查CSV / 迁移...")
    migrate_from_cache()

    # 1. 交易日
    log("\n[1] 获取交易日...")
    dates = get_trade_dates(LOOKBACK_DAYS)

    if not dates:
        log("  ⚠️ Tushare 连不上，使用已有CSV数据")
        existing = sorted(read_csv_dates(FUT_CSV))
        if not existing:
            log("  ERROR: 无交易日且无CSV数据")
            sys.exit(1)
        log(f"  从CSV恢复: {len(existing)} 天: {existing[0]} ~ {existing[-1]}")
        return

    log(f"  {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    # 2. 增量
    existing_dates = read_csv_dates(FUT_CSV)
    new_dates = sorted(set(dates) - existing_dates)

    if not new_dates:
        log(f"\n  所有数据已在CSV中，无需拉取")
    else:
        log(f"\n  需要增量拉取: {len(new_dates)} 天 ({new_dates[0]} ~ {new_dates[-1]})")
        all_new_rows = []
        for i, dt in enumerate(new_dates):
            cached = any(os.path.exists(os.path.join(CACHE_DIR, p))
                        for p in [f'{dt}_all.json', f'fut_daily_{dt}.json'])
            tag = '📦' if cached else '🌐'
            log(f"  [{i+1}/{len(new_dates)}] {dt} {tag}")
            rows = fetch_day(dt)
            all_new_rows.extend(rows)
            log(f"    {len(rows)} 品种")
            if not cached:
                time.sleep(0.3)

        if all_new_rows:
            append_csv(FUT_CSV, CSV_HEADERS, all_new_rows)
            log(f"  新增 {len(all_new_rows)} 行")

    # 3. 统计
    all_dates = sorted(read_csv_dates(FUT_CSV))
    log(f"\n✅ fut_daily.csv: {len(all_dates)} 天")
    if all_dates:
        log(f"   {all_dates[0]} ~ {all_dates[-1]}")


if __name__ == '__main__':
    main()
