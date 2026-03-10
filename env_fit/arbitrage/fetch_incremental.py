#!/usr/bin/env python3
"""套利模块增量拉取：统一管理 mod1/mod2/mod3 的原始数据缓存。
存储：CSV 为真相源（append-only），JSON cache 为快速读取层。

CSV 文件：
- arb_mod1_fut.csv       股指期货日线（trade_date, prefix, close, vol, amount, oi）
- arb_mod1_spot.csv      现货指数日线（trade_date, prefix, close）
- arb_mod2_commodity.csv 商品期货日线（trade_date, symbol, close, vol, amount, oi）
- arb_mod3_opt.csv       期权聚合日线（trade_date, call_vol, put_vol, call_oi, put_oi, call_amount, put_amount, n_contracts）
- arb_mod3_hv.csv        HV指数日线（trade_date, close）

JSON 文件：
- arb_cache.json（保留，供 mod1/mod2/mod3 快速读取）

首次运行：如果已有 JSON cache 但无 CSV，自动迁移。
后续运行：增量拉取同时写 CSV + JSON。
--rebuild：从 CSV 重建 JSON cache。
"""
import json, os, time, csv, sys, requests
from datetime import datetime, timedelta
from collections import defaultdict

# === Tushare ===
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TS_URL = "https://api.tushare.pro"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "arb_cache.json")
CP_CACHE = os.path.join(BASE_DIR, "_opt_cp_map.json")

# CSV 路径
MOD1_FUT_CSV = os.path.join(BASE_DIR, "arb_mod1_fut.csv")
MOD1_SPOT_CSV = os.path.join(BASE_DIR, "arb_mod1_spot.csv")
MOD2_CSV = os.path.join(BASE_DIR, "arb_mod2_commodity.csv")
MOD3_OPT_CSV = os.path.join(BASE_DIR, "arb_mod3_opt.csv")
MOD3_HV_CSV = os.path.join(BASE_DIR, "arb_mod3_hv.csv")

# CSV 表头
MOD1_FUT_HEADERS = ['trade_date', 'prefix', 'close', 'vol', 'amount', 'oi']
MOD1_SPOT_HEADERS = ['trade_date', 'prefix', 'close']
MOD2_HEADERS = ['trade_date', 'symbol', 'close', 'vol', 'amount', 'oi']
MOD3_OPT_HEADERS = ['trade_date', 'call_vol', 'put_vol', 'call_oi', 'put_oi', 'call_amount', 'put_amount', 'n_contracts']
MOD3_HV_HEADERS = ['trade_date', 'close']

# commodity_cta 的期货数据
CTA_FUT_CSV = os.path.join(BASE_DIR, '..', 'commodity_cta', 'fut_daily.csv')

# 全量拉取天数（含 HV 额外天数）
FULL_DAYS = 80

# === mod1: 股指期货 + 现货指数 ===
INDEX_FUTURES = {
    'IF': {'fut_code': 'IF.CFX', 'spot_code': '000300.SH', 'name': '沪深300'},
    'IH': {'fut_code': 'IH.CFX', 'spot_code': '000016.SH', 'name': '上证50'},
    'IC': {'fut_code': 'IC.CFX', 'spot_code': '000905.SH', 'name': '中证500'},
    'IM': {'fut_code': 'IM.CFX', 'spot_code': '000852.SH', 'name': '中证1000'},
}

# === mod2: 商品期货品种 ===
COMMODITY_SYMBOLS = ['RB', 'I', 'Y', 'P', 'CU', 'AL', 'SC', 'FU']
EXCHANGE_MAP = {
    'RB': 'SHF', 'I': 'DCE', 'Y': 'DCE', 'P': 'DCE',
    'CU': 'SHF', 'AL': 'SHF', 'SC': 'INE', 'FU': 'SHF',
}

# === mod3: HV 指数 ===
HV_INDEX = '000300.SH'


# ============ Tushare API ============
_last_call = 0

def ts(api, params, fields=''):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)

    body = {"api_name": api, "token": TS_TOKEN, "params": params}
    if fields:
        body["fields"] = fields

    for attempt in range(3):
        try:
            _last_call = time.time()
            r = requests.post(TS_URL, json=body, timeout=90, proxies={'http': None, 'https': None})
            if not r.text.strip():
                print(f"  空响应，重试 {attempt+1}/3...")
                time.sleep(3)
                continue
            d = r.json()
            if d.get("code") == -2001:
                print(f"  限流，等10s...")
                time.sleep(10)
                continue
            if d.get("data") and d["data"].get("fields") and d["data"].get("items"):
                return [dict(zip(d["data"]["fields"], row)) for row in d["data"]["items"]]
            return []
        except Exception as e:
            print(f"  请求失败: {e}，重试 {attempt+1}/3...")
            time.sleep(3)
    return []


# ============ CSV 读写 ============

def read_csv_file(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv_file(path, headers, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def append_csv_file(path, headers, rows):
    need_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if need_header:
            w.writeheader()
        w.writerows(rows)


def get_csv_last_dates(path, code_col):
    """从 CSV 获取每个代码的最后日期 {code: 'YYYYMMDD'}"""
    rows = read_csv_file(path)
    last = {}
    for r in rows:
        code = r.get(code_col, '')
        dt = r.get('trade_date', '')
        if code and dt:
            if code not in last or dt > last[code]:
                last[code] = dt
    return last


def get_csv_last_date(path):
    """从 CSV 获取全局最后日期"""
    rows = read_csv_file(path)
    if not rows:
        return None
    return max(r.get('trade_date', '') for r in rows)


# ============ JSON Cache ============

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_updated": "",
        "trade_dates": [],
        "mod1_fut": {},
        "mod1_spot": {},
        "mod2_commodity": {},
        "mod3_opt_daily": {},
        "mod3_hv_index": {},
    }


def save_cache(cache):
    cache["last_updated"] = datetime.today().strftime("%Y%m%d")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_last_date(section):
    if section:
        return max(section.keys())
    return None


def next_day(date_str):
    d = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
    return d.strftime("%Y%m%d")


def full_start():
    return (datetime.today() - timedelta(days=FULL_DAYS * 2)).strftime("%Y%m%d")


# ============ 迁移：JSON → CSV ============

def migrate_json_to_csv(cache):
    migrated = False

    # mod1_fut
    if not os.path.exists(MOD1_FUT_CSV) and cache.get("mod1_fut"):
        print("  📦 迁移 mod1_fut → arb_mod1_fut.csv...")
        rows = []
        for prefix, section in cache["mod1_fut"].items():
            for dt, vals in sorted(section.items()):
                rows.append({
                    'trade_date': dt, 'prefix': prefix,
                    'close': vals.get('close', ''),
                    'vol': vals.get('vol', ''),
                    'amount': vals.get('amount', ''),
                    'oi': vals.get('oi', ''),
                })
        write_csv_file(MOD1_FUT_CSV, MOD1_FUT_HEADERS, rows)
        print(f"    {len(rows)} 行")
        migrated = True

    # mod1_spot
    if not os.path.exists(MOD1_SPOT_CSV) and cache.get("mod1_spot"):
        print("  📦 迁移 mod1_spot → arb_mod1_spot.csv...")
        rows = []
        for prefix, section in cache["mod1_spot"].items():
            for dt, vals in sorted(section.items()):
                rows.append({
                    'trade_date': dt, 'prefix': prefix,
                    'close': vals.get('close', ''),
                })
        write_csv_file(MOD1_SPOT_CSV, MOD1_SPOT_HEADERS, rows)
        print(f"    {len(rows)} 行")
        migrated = True

    # mod2_commodity
    if not os.path.exists(MOD2_CSV) and cache.get("mod2_commodity"):
        print("  📦 迁移 mod2_commodity → arb_mod2_commodity.csv...")
        rows = []
        for sym, section in cache["mod2_commodity"].items():
            for dt, vals in sorted(section.items()):
                rows.append({
                    'trade_date': dt, 'symbol': sym,
                    'close': vals.get('close', ''),
                    'vol': vals.get('vol', ''),
                    'amount': vals.get('amount', ''),
                    'oi': vals.get('oi', ''),
                })
        write_csv_file(MOD2_CSV, MOD2_HEADERS, rows)
        print(f"    {len(rows)} 行")
        migrated = True

    # mod3_opt_daily
    if not os.path.exists(MOD3_OPT_CSV) and cache.get("mod3_opt_daily"):
        print("  📦 迁移 mod3_opt_daily → arb_mod3_opt.csv...")
        rows = []
        for dt, vals in sorted(cache["mod3_opt_daily"].items()):
            rows.append({
                'trade_date': dt,
                'call_vol': vals.get('call_vol', ''),
                'put_vol': vals.get('put_vol', ''),
                'call_oi': vals.get('call_oi', ''),
                'put_oi': vals.get('put_oi', ''),
                'call_amount': vals.get('call_amount', ''),
                'put_amount': vals.get('put_amount', ''),
                'n_contracts': vals.get('n_contracts', ''),
            })
        write_csv_file(MOD3_OPT_CSV, MOD3_OPT_HEADERS, rows)
        print(f"    {len(rows)} 行")
        migrated = True

    # mod3_hv_index
    if not os.path.exists(MOD3_HV_CSV) and cache.get("mod3_hv_index"):
        print("  📦 迁移 mod3_hv_index → arb_mod3_hv.csv...")
        rows = []
        for dt, vals in sorted(cache["mod3_hv_index"].items()):
            rows.append({'trade_date': dt, 'close': vals.get('close', '')})
        write_csv_file(MOD3_HV_CSV, MOD3_HV_HEADERS, rows)
        print(f"    {len(rows)} 行")
        migrated = True

    return migrated


# ============ C/P 映射 ============

def load_cp_map():
    if os.path.exists(CP_CACHE):
        age_hours = (time.time() - os.path.getmtime(CP_CACHE)) / 3600
        if age_hours < 24 * 7:
            with open(CP_CACHE) as f:
                cp_map = json.load(f)
            print(f'  从缓存加载 C/P 映射: {len(cp_map)} 合约')
            return cp_map

    print('  从 API 构建 C/P 映射...')
    cp_map = {}
    for cp in ['C', 'P']:
        rows = ts('opt_basic', {'exchange': 'SSE', 'call_put': cp},
                   fields='ts_code,call_put')
        if rows:
            for r in rows:
                cp_map[r['ts_code']] = r['call_put']
            print(f'    {cp}: {len(rows)} 合约')
        time.sleep(2)

    if cp_map:
        with open(CP_CACHE, 'w') as f:
            json.dump(cp_map, f)
        print(f'  映射已缓存: {len(cp_map)} 合约')
    return cp_map


# ============ CTA CSV 复用 ============

def load_cta_fut_csv():
    path = os.path.realpath(CTA_FUT_CSV)
    if not os.path.exists(path):
        return {}
    series = defaultdict(dict)
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
    print(f'  从 commodity_cta/fut_daily.csv 加载: {len(series)} 品种')
    return dict(series)


# ============ 主流程 ============

def fetch_incremental():
    cache = load_cache()
    today = datetime.today().strftime("%Y%m%d")
    stats = {"mod1_new": 0, "mod2_new": 0, "mod3_new": 0, "skip": 0}

    # 首次迁移
    migrate_json_to_csv(cache)

    # 从 CSV 获取各代码最后日期
    fut_last = get_csv_last_dates(MOD1_FUT_CSV, 'prefix')
    spot_last = get_csv_last_dates(MOD1_SPOT_CSV, 'prefix')
    comm_last = get_csv_last_dates(MOD2_CSV, 'symbol')
    opt_last_date = get_csv_last_date(MOD3_OPT_CSV)
    hv_last_date = get_csv_last_date(MOD3_HV_CSV)

    # === 0. 交易日历 ===
    print("=" * 55)
    print("套利模块增量拉取（CSV + JSON 双写）")
    print("=" * 55)

    print("\n[0] 更新交易日历...")
    existing_dates = set(cache.get("trade_dates", []))
    start = full_start()
    rows = ts('trade_cal', {'exchange': 'SSE', 'start_date': start, 'end_date': today, 'is_open': '1'},
              fields='cal_date')
    if rows:
        new_dates = set(r['cal_date'] for r in rows)
        merged = sorted(existing_dates | new_dates)
        cache["trade_dates"] = merged
        print(f"  交易日: {len(merged)} 天 ({merged[0]} ~ {merged[-1]})")
    else:
        print("  ⚠️ 无法获取交易日历（API 不可用）")
        if not cache.get("trade_dates"):
            # fallback: 生成最近 FULL_DAYS 的工作日作为近似交易日历
            from datetime import date
            fallback = []
            d = date.today()
            for _ in range(FULL_DAYS * 2):
                if d.weekday() < 5:  # 周一到周五
                    fallback.append(d.strftime("%Y%m%d"))
                d -= timedelta(days=1)
            cache["trade_dates"] = sorted(fallback)
            print(f"  使用 fallback 交易日历: {len(cache['trade_dates'])} 天")

    # === 1. mod1: 股指期货 + 现货指数 ===
    print("\n" + "=" * 55)
    print("[1] 股指套利数据（mod1）")
    print("=" * 55)

    for prefix, info in INDEX_FUTURES.items():
        # ── 期货 ──
        section = cache.setdefault("mod1_fut", {}).setdefault(prefix, {})
        last = fut_last.get(prefix)
        if last and last >= today:
            print(f"  {prefix} 期货: 已是最新 ({last})，跳过")
            stats["skip"] += 1
        else:
            start = next_day(last) if last else full_start()
            print(f"  {prefix} 期货 ({info['fut_code']}): 从 {start} 拉取...", end='', flush=True)
            rows = ts('fut_daily', {
                'ts_code': info['fut_code'],
                'start_date': start, 'end_date': today,
            }, fields='ts_code,trade_date,close,vol,amount,oi')

            csv_rows = []
            count = 0
            for r in (rows or []):
                dt = r['trade_date']
                vals = {
                    'close': r.get('close'),
                    'vol': r.get('vol', 0),
                    'amount': r.get('amount', 0),
                    'oi': r.get('oi', 0),
                }
                section[dt] = vals
                csv_rows.append({
                    'trade_date': dt, 'prefix': prefix,
                    'close': vals['close'] if vals['close'] is not None else '',
                    'vol': vals['vol'], 'amount': vals['amount'], 'oi': vals['oi'],
                })
                count += 1

            if csv_rows:
                append_csv_file(MOD1_FUT_CSV, MOD1_FUT_HEADERS, csv_rows)
            print(f" +{count}条 (总{len(section)}条)")
            stats["mod1_new"] += count

        # ── 现货 ──
        section = cache.setdefault("mod1_spot", {}).setdefault(prefix, {})
        last = spot_last.get(prefix)
        if last and last >= today:
            print(f"  {prefix} 现货: 已是最新 ({last})，跳过")
            stats["skip"] += 1
        else:
            start = next_day(last) if last else full_start()
            print(f"  {prefix} 现货 ({info['spot_code']}): 从 {start} 拉取...", end='', flush=True)
            rows = ts('index_daily', {
                'ts_code': info['spot_code'],
                'start_date': start, 'end_date': today,
            }, fields='ts_code,trade_date,close')

            csv_rows = []
            count = 0
            for r in (rows or []):
                dt = r['trade_date']
                close = r.get('close')
                section[dt] = {'close': close}
                csv_rows.append({
                    'trade_date': dt, 'prefix': prefix,
                    'close': close if close is not None else '',
                })
                count += 1

            if csv_rows:
                append_csv_file(MOD1_SPOT_CSV, MOD1_SPOT_HEADERS, csv_rows)
            print(f" +{count}条 (总{len(section)}条)")
            stats["mod1_new"] += count

    # === 2. mod2: 商品期货 ===
    print("\n" + "=" * 55)
    print("[2] 商品套利数据（mod2）")
    print("=" * 55)

    cta_data = load_cta_fut_csv()

    for sym in COMMODITY_SYMBOLS:
        section = cache.setdefault("mod2_commodity", {}).setdefault(sym, {})
        last = comm_last.get(sym)

        if last and last >= today:
            print(f"  {sym}: 已是最新 ({last})，跳过")
            stats["skip"] += 1
            continue

        # 先从 CTA CSV 补充
        csv_new_rows = []
        if sym in cta_data:
            cta_sym = cta_data[sym]
            new_from_csv = 0
            for dt, val in sorted(cta_sym.items()):
                if dt not in section and (not last or dt > last):
                    section[dt] = val
                    csv_new_rows.append({
                        'trade_date': dt, 'symbol': sym,
                        'close': val['close'], 'vol': val['vol'],
                        'amount': val['amount'], 'oi': val['oi'],
                    })
                    new_from_csv += 1
            if new_from_csv > 0:
                append_csv_file(MOD2_CSV, MOD2_HEADERS, csv_new_rows)
                print(f"  {sym}: 从 CTA CSV 补充 +{new_from_csv}条 (总{len(section)}条)")
                stats["mod2_new"] += new_from_csv
                new_last = get_last_date(section)
                if new_last and new_last >= today:
                    continue

        # 从 API 拉增量
        current_last = get_last_date(section)
        start = next_day(current_last) if current_last else full_start()
        exch = EXCHANGE_MAP.get(sym, 'SHF')
        ts_code = f'{sym}.{exch}'
        print(f"  {sym} ({ts_code}): 从 {start} 拉取...", end='', flush=True)
        rows = ts('fut_daily', {
            'ts_code': ts_code,
            'start_date': start, 'end_date': today,
        }, fields='ts_code,trade_date,close,vol,amount,oi')

        csv_rows = []
        count = 0
        for r in (rows or []):
            dt = r['trade_date']
            vals = {
                'close': r.get('close'),
                'vol': r.get('vol', 0),
                'amount': r.get('amount', 0),
                'oi': r.get('oi', 0),
            }
            section[dt] = vals
            csv_rows.append({
                'trade_date': dt, 'symbol': sym,
                'close': vals['close'] if vals['close'] is not None else '',
                'vol': vals['vol'], 'amount': vals['amount'], 'oi': vals['oi'],
            })
            count += 1

        if csv_rows:
            append_csv_file(MOD2_CSV, MOD2_HEADERS, csv_rows)
        print(f" +{count}条 (总{len(section)}条)")
        stats["mod2_new"] += count

    # === 3. mod3: 期权日线 + HV 指数 ===
    print("\n" + "=" * 55)
    print("[3] 期权套利数据（mod3）")
    print("=" * 55)

    cp_map = load_cp_map()

    # ── HV 指数 ──
    hv_section = cache.setdefault("mod3_hv_index", {})
    last = hv_last_date
    if last and last >= today:
        print(f"  HV指数 ({HV_INDEX}): 已是最新 ({last})，跳过")
        stats["skip"] += 1
    else:
        start = next_day(last) if last else full_start()
        print(f"  HV指数 ({HV_INDEX}): 从 {start} 拉取...", end='', flush=True)
        rows = ts('index_daily', {
            'ts_code': HV_INDEX,
            'start_date': start, 'end_date': today,
        }, fields='ts_code,trade_date,close')

        csv_rows = []
        count = 0
        for r in (rows or []):
            dt = r['trade_date']
            close = r.get('close')
            hv_section[dt] = {'close': close}
            csv_rows.append({
                'trade_date': dt,
                'close': close if close is not None else '',
            })
            count += 1

        if csv_rows:
            append_csv_file(MOD3_HV_CSV, MOD3_HV_HEADERS, csv_rows)
        print(f" +{count}条 (总{len(hv_section)}条)")
        stats["mod3_new"] += count

    # ── 期权日线（逐日聚合）──
    opt_section = cache.setdefault("mod3_opt_daily", {})
    last = opt_last_date

    trade_dates = cache.get("trade_dates", [])
    if last:
        dates_to_fetch = [d for d in trade_dates if d > last and d <= today]
    else:
        dates_to_fetch = trade_dates[-FULL_DAYS:]

    if not dates_to_fetch:
        print(f"  期权日线: 已是最新，跳过")
        stats["skip"] += 1
    else:
        print(f"  期权日线: 需拉取 {len(dates_to_fetch)} 天 ({dates_to_fetch[0]} ~ {dates_to_fetch[-1]})")
        for i, d in enumerate(dates_to_fetch):
            rows = ts('opt_daily', {
                'exchange': 'SSE', 'trade_date': d
            }, fields='ts_code,trade_date,close,vol,amount,oi')

            if not rows:
                if i < 2 or i >= len(dates_to_fetch) - 2:
                    print(f"    {d}: 无数据")
                continue

            call_vol = put_vol = call_oi = put_oi = 0
            call_amount = put_amount = 0

            for r in rows:
                code = r.get('ts_code', '')
                cp = cp_map.get(code)
                vol = r.get('vol', 0) or 0
                oi = r.get('oi', 0) or 0
                amount = r.get('amount', 0) or 0

                if cp == 'C':
                    call_vol += vol; call_oi += oi; call_amount += amount
                elif cp == 'P':
                    put_vol += vol; put_oi += oi; put_amount += amount

            vals = {
                'call_vol': int(call_vol),
                'put_vol': int(put_vol),
                'call_oi': int(call_oi),
                'put_oi': int(put_oi),
                'call_amount': round(call_amount, 2),
                'put_amount': round(put_amount, 2),
                'n_contracts': len(rows),
            }
            opt_section[d] = vals

            # CSV append
            append_csv_file(MOD3_OPT_CSV, MOD3_OPT_HEADERS, [{
                'trade_date': d, **vals
            }])

            stats["mod3_new"] += 1

            if i == 0 or i == len(dates_to_fetch) - 1 or (i + 1) % 10 == 0:
                print(f"    {d}: {len(rows)} 合约 ✓")

    # === 保存 JSON cache ===
    save_cache(cache)

    # === 统计 ===
    cache_kb = os.path.getsize(CACHE_PATH) / 1024
    csv_sizes = {}
    for name, path in [('mod1_fut', MOD1_FUT_CSV), ('mod1_spot', MOD1_SPOT_CSV),
                        ('mod2', MOD2_CSV), ('mod3_opt', MOD3_OPT_CSV), ('mod3_hv', MOD3_HV_CSV)]:
        csv_sizes[name] = os.path.getsize(path) / 1024 if os.path.exists(path) else 0

    print("\n" + "=" * 55)
    print("统计摘要")
    print("=" * 55)
    print(f"  mod1(股指): 新增 {stats['mod1_new']} 条")
    print(f"  mod2(商品): 新增 {stats['mod2_new']} 条")
    print(f"  mod3(期权): 新增 {stats['mod3_new']} 条")
    print(f"  跳过: {stats['skip']} 项")
    print(f"  文件大小:")
    print(f"    JSON cache: {cache_kb:.1f} KB")
    for name, kb in csv_sizes.items():
        print(f"    {name}.csv: {kb:.1f} KB")

    # 各数据源条数
    print("\n数据条数:")
    for prefix in INDEX_FUTURES:
        nf = len(cache.get("mod1_fut", {}).get(prefix, {}))
        ns = len(cache.get("mod1_spot", {}).get(prefix, {}))
        print(f"  {prefix} 期货: {nf}条, 现货: {ns}条")
    for sym in COMMODITY_SYMBOLS:
        n = len(cache.get("mod2_commodity", {}).get(sym, {}))
        print(f"  {sym}: {n}条")
    print(f"  期权日线: {len(cache.get('mod3_opt_daily', {}))}天")
    print(f"  HV指数: {len(cache.get('mod3_hv_index', {}))}条")

    print(f"\n✅ 增量拉取完成（CSV + JSON 双写）")


# ============ rebuild: 从 CSV 重建 JSON cache ============

def rebuild_cache_from_csv():
    print("🔄 从 CSV 重建 JSON cache...")
    cache = {
        "last_updated": datetime.today().strftime("%Y%m%d"),
        "trade_dates": [],
        "mod1_fut": {},
        "mod1_spot": {},
        "mod2_commodity": {},
        "mod3_opt_daily": {},
        "mod3_hv_index": {},
    }

    def to_float(v):
        try:
            return float(v) if v != '' else None
        except (ValueError, TypeError):
            return None

    def to_int(v):
        try:
            return int(float(v)) if v != '' else 0
        except (ValueError, TypeError):
            return 0

    # mod1_fut
    for r in read_csv_file(MOD1_FUT_CSV):
        prefix = r['prefix']
        cache.setdefault("mod1_fut", {}).setdefault(prefix, {})[r['trade_date']] = {
            'close': to_float(r.get('close')),
            'vol': to_float(r.get('vol', 0)),
            'amount': to_float(r.get('amount', 0)),
            'oi': to_float(r.get('oi', 0)),
        }
    print(f"  mod1_fut: {sum(len(v) for v in cache['mod1_fut'].values())} 行")

    # mod1_spot
    for r in read_csv_file(MOD1_SPOT_CSV):
        prefix = r['prefix']
        cache.setdefault("mod1_spot", {}).setdefault(prefix, {})[r['trade_date']] = {
            'close': to_float(r.get('close')),
        }
    print(f"  mod1_spot: {sum(len(v) for v in cache['mod1_spot'].values())} 行")

    # mod2_commodity
    for r in read_csv_file(MOD2_CSV):
        sym = r['symbol']
        cache.setdefault("mod2_commodity", {}).setdefault(sym, {})[r['trade_date']] = {
            'close': to_float(r.get('close')),
            'vol': to_float(r.get('vol', 0)),
            'amount': to_float(r.get('amount', 0)),
            'oi': to_float(r.get('oi', 0)),
        }
    print(f"  mod2_commodity: {sum(len(v) for v in cache['mod2_commodity'].values())} 行")

    # mod3_opt_daily
    for r in read_csv_file(MOD3_OPT_CSV):
        cache["mod3_opt_daily"][r['trade_date']] = {
            'call_vol': to_int(r.get('call_vol')),
            'put_vol': to_int(r.get('put_vol')),
            'call_oi': to_int(r.get('call_oi')),
            'put_oi': to_int(r.get('put_oi')),
            'call_amount': to_float(r.get('call_amount')) or 0,
            'put_amount': to_float(r.get('put_amount')) or 0,
            'n_contracts': to_int(r.get('n_contracts')),
        }
    print(f"  mod3_opt: {len(cache['mod3_opt_daily'])} 天")

    # mod3_hv_index
    for r in read_csv_file(MOD3_HV_CSV):
        cache["mod3_hv_index"][r['trade_date']] = {
            'close': to_float(r.get('close')),
        }
    print(f"  mod3_hv: {len(cache['mod3_hv_index'])} 行")

    # 重建交易日历
    all_dates = set()
    for section in [cache["mod1_fut"], cache["mod1_spot"], cache["mod2_commodity"]]:
        for sub in section.values():
            all_dates.update(sub.keys())
    all_dates.update(cache["mod3_opt_daily"].keys())
    all_dates.update(cache["mod3_hv_index"].keys())
    cache["trade_dates"] = sorted(all_dates)
    print(f"  交易日历: {len(cache['trade_dates'])} 天")

    save_cache(cache)
    print(f"  ✅ JSON cache 已重建 ({os.path.getsize(CACHE_PATH)/1024:.1f} KB)")


if __name__ == "__main__":
    t0 = time.time()

    if '--rebuild' in sys.argv:
        rebuild_cache_from_csv()
    else:
        fetch_incremental()

    print(f"耗时: {time.time()-t0:.1f}秒")
