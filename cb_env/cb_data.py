#!/usr/bin/env python3
"""
转债指增策略环境 — 数据拉取脚本（带缓存）
从 Tushare 拉取转债日行情、转债基本信息、正股行情、指数行情

策略：正股数据按 ts_code 逐只拉（每只~1s），不拉全市场 daily（每天~5s+超时风险）
"""

import requests, json, time, os, sys
from datetime import datetime, timedelta

TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/cb_env'
OUTPUT_JSON = os.path.join(BASE_DIR, 'cb_data.json')
CACHE_DIR = os.path.join(BASE_DIR, '_cache')
LOOKBACK_DAYS = 90  # 多拉一些确保60日窗口够

os.makedirs(CACHE_DIR, exist_ok=True)

def log(msg):
    print(msg, flush=True)

# ═══ Tushare API ═══

def ts_api(api_name, params=None, fields='', retries=3):
    if params is None:
        params = {}
    body = {"api_name": api_name, "token": TUSHARE_TOKEN, "params": params}
    if fields:
        body["fields"] = fields
    for attempt in range(retries):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=60)
            d = r.json()
            if d.get("code") != 0:
                log(f"  API error ({api_name}): {d.get('msg','')}")
                return [], []
            return d["data"]["fields"], d["data"]["items"]
        except Exception as e:
            log(f"  Retry {attempt+1}/{retries} ({api_name}): {e}")
            time.sleep(2)
    return [], []


def get_trade_dates(n_days):
    end = datetime.now()
    start = end - timedelta(days=n_days)
    fields, items = ts_api("trade_cal", {
        "exchange": "SSE",
        "start_date": start.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "is_open": "1"
    }, fields="cal_date")
    if not items:
        return []
    return sorted([it[0] for it in items])


# ═══ 缓存 ═══

def cache_path(prefix, key):
    return os.path.join(CACHE_DIR, f"{prefix}_{key}.json")

def load_cache(prefix, key):
    p = cache_path(prefix, key)
    if os.path.exists(p):
        with open(p, 'r') as f:
            return json.load(f)
    return None

def save_cache(prefix, key, data):
    with open(cache_path(prefix, key), 'w') as f:
        json.dump(data, f, ensure_ascii=False)


# ═══ 数据拉取 ═══

def fetch_cb_daily(dates):
    """转债日行情（按天缓存）"""
    all_data = {}
    for i, dt in enumerate(dates):
        cached = load_cache("cb_daily", dt)
        if cached is not None:
            all_data[dt] = cached
            continue
        log(f"  [{i+1}/{len(dates)}] cb_daily {dt}...")
        fields, items = ts_api("cb_daily", {"trade_date": dt})
        if not fields:
            continue
        records = [dict(zip(fields, it)) for it in items]
        active = [r for r in records if r.get("vol", 0) > 0]
        all_data[dt] = active
        save_cache("cb_daily", dt, active)
        time.sleep(0.3)
    return all_data


def fetch_cb_basic():
    """转债基本信息（缓存1天）"""
    today = datetime.now().strftime("%Y%m%d")
    cached = load_cache("cb_basic", today)
    if cached is not None:
        return cached
    log("  拉取 cb_basic...")
    fields, items = ts_api("cb_basic", {})
    if not fields:
        return []
    records = [dict(zip(fields, it)) for it in items]
    save_cache("cb_basic", today, records)
    return records


def fetch_stock_by_code(stk_codes, start_date, end_date):
    """按正股代码逐只拉行情（按 ts_code 缓存整段）"""
    cache_key_suffix = f"{start_date}_{end_date}"
    all_data = {}  # stk_code → {date → {close, pct_chg}}
    
    codes = sorted(stk_codes)
    cached_count = 0
    
    for i, code in enumerate(codes):
        ck = f"stk_{code.replace('.','_')}_{cache_key_suffix}"
        cached = load_cache("stk_range", ck)
        if cached is not None:
            all_data[code] = cached
            cached_count += 1
            continue
        
        if cached_count == 0 or (i % 50 == 0):
            log(f"  [{i+1}/{len(codes)}] stock {code}...")
        
        fields, items = ts_api("daily", {
            "ts_code": code,
            "start_date": start_date,
            "end_date": end_date
        }, fields="ts_code,trade_date,close,pct_chg")
        
        if not fields:
            time.sleep(0.3)
            continue
        
        date_map = {}
        for it in items:
            rec = dict(zip(fields, it))
            date_map[rec["trade_date"]] = {
                "close": rec["close"],
                "pct_chg": rec["pct_chg"]
            }
        all_data[code] = date_map
        save_cache("stk_range", ck, date_map)
        time.sleep(0.2)
    
    log(f"  完成: {len(all_data)} 只正股 ({cached_count} cached)")
    return all_data


def fetch_index_daily(index_codes, start_date, end_date):
    """指数日行情"""
    all_data = {}
    for idx_code in index_codes:
        ck = f"{idx_code.replace('.','_')}_{start_date}_{end_date}"
        cached = load_cache("idx", ck)
        if cached is not None:
            all_data[idx_code] = cached
            continue
        log(f"  拉取 index {idx_code}...")
        fields, items = ts_api("index_daily", {
            "ts_code": idx_code,
            "start_date": start_date,
            "end_date": end_date
        }, fields="ts_code,trade_date,close,pct_chg,amount")
        if not fields:
            continue
        records = {}
        for it in items:
            rec = dict(zip(fields, it))
            records[rec["trade_date"]] = rec
        all_data[idx_code] = records
        save_cache("idx", ck, records)
        time.sleep(0.3)
    return all_data


# ═══ 主流程 ═══

def main():
    log("=" * 50)
    log("转债指增策略环境 — 数据拉取")
    log("=" * 50)

    # 1. 交易日
    log("\n[1/5] 获取交易日...")
    dates = get_trade_dates(LOOKBACK_DAYS)
    if not dates:
        log("ERROR: 无法获取交易日")
        sys.exit(1)
    log(f"  {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    # 2. 转债基本信息
    log("\n[2/5] 转债基本信息...")
    cb_basic = fetch_cb_basic()
    cb_map = {}
    for cb in cb_basic:
        ts_code = cb.get("ts_code")
        if not ts_code:
            continue
        list_date = cb.get("list_date")
        delist_date = cb.get("delist_date")
        if not list_date:
            continue
        if delist_date and delist_date <= dates[0]:
            continue
        cb_map[ts_code] = {
            "stk_code": cb.get("stk_code"),
            "conv_price": cb.get("conv_price"),
            "maturity_date": cb.get("maturity_date"),
            "list_date": list_date,
            "bond_short_name": cb.get("bond_short_name"),
            "par": cb.get("par", 100),
        }
    log(f"  存续转债: {len(cb_map)} 只")

    # 3. 转债日行情
    log("\n[3/5] 转债日行情...")
    cb_daily = fetch_cb_daily(dates)
    log(f"  {len(cb_daily)} 天")

    # 4. 正股行情（按 ts_code 逐只拉）
    log("\n[4/5] 正股行情（逐只拉取）...")
    stk_codes = set(v["stk_code"] for v in cb_map.values() if v.get("stk_code"))
    log(f"  需要 {len(stk_codes)} 只正股")
    stk_daily = fetch_stock_by_code(stk_codes, dates[0], dates[-1])

    # 5. 指数行情
    log("\n[5/5] 指数行情...")
    index_codes = ["000852.SH", "932000.CSI"]
    idx_daily = fetch_index_daily(index_codes, dates[0], dates[-1])
    log(f"  {len(idx_daily)} 个指数")

    # ═══ 输出 ═══
    output = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dates": dates,
            "n_dates": len(dates),
            "n_cb": len(cb_map),
        },
        "cb_map": cb_map,
        "cb_daily": cb_daily,
        "stk_daily": stk_daily,
        "idx_daily": idx_daily,
    }

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    
    fsize = os.path.getsize(OUTPUT_JSON) / 1024 / 1024
    log(f"\n✅ 完成: {OUTPUT_JSON} ({fsize:.1f} MB)")
    log(f"   {dates[0]} ~ {dates[-1]} ({len(dates)}天)")
    log(f"   转债: {len(cb_map)} 只 | 正股: {len(stk_daily)} 只")


if __name__ == "__main__":
    main()
