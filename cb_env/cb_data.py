#!/usr/bin/env python3
"""
转债指增策略环境 — 数据拉取脚本（CSV增量模式）
从 Tushare 拉取转债日行情、转债基本信息、正股行情、指数行情

增量策略：
- 4个CSV文件作为持久化存储
- 每次运行只拉CSV中没有的新日期
- 最后从CSV生成 cb_data.json（格式不变，供 cb_calc.py 使用）
- 首次运行时从已有 cb_data.json 导入CSV（如果存在）
"""

import requests, json, time, os, sys, csv
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/cb_env'
OUTPUT_JSON = os.path.join(BASE_DIR, 'cb_data.json')
LOOKBACK_DAYS = 90

# CSV 文件路径
CB_DAILY_CSV = os.path.join(BASE_DIR, 'cb_daily.csv')
STK_DAILY_CSV = os.path.join(BASE_DIR, 'stk_daily.csv')
IDX_DAILY_CSV = os.path.join(BASE_DIR, 'idx_daily.csv')
CB_BASIC_CSV = os.path.join(BASE_DIR, 'cb_basic.csv')

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


# ═══ CSV 读写工具 ═══

def read_csv(path):
    """读取CSV，返回 (headers, rows)"""
    if not os.path.exists(path):
        return [], []
    with open(path, 'r', newline='', encoding='gb18030') as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        rows = list(reader)
    return headers, rows

def write_csv(path, headers, rows):
    """写入CSV（覆盖）"""
    with open(path, 'w', newline='', encoding='gb18030') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

def append_csv(path, headers, rows):
    """追加到CSV（如果文件不存在则创建含表头）"""
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, 'a', newline='', encoding='gb18030') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(headers)
        writer.writerows(rows)

def get_csv_dates(path, date_col='trade_date'):
    """获取CSV中已有的日期集合"""
    headers, rows = read_csv(path)
    if not headers:
        return set()
    try:
        idx = headers.index(date_col)
    except ValueError:
        return set()
    return set(row[idx] for row in rows)


# ═══ 从已有 JSON 导入 CSV（首次迁移）═══

def migrate_from_json():
    """从已有的 cb_data.json 导入到 CSV 文件（一次性迁移）"""
    if not os.path.exists(OUTPUT_JSON):
        return False
    
    # 如果 CSV 已经有数据，跳过迁移
    if os.path.exists(CB_DAILY_CSV) and os.path.getsize(CB_DAILY_CSV) > 100:
        return True
    
    log("  从 cb_data.json 迁移到 CSV...")
    with open(OUTPUT_JSON) as f:
        data = json.load(f)
    
    # 1. cb_daily.csv
    cb_headers = ['trade_date', 'ts_code', 'close', 'vol', 'amount', 'pct_chg',
                  'pre_close', 'open', 'high', 'low']
    cb_rows = []
    for dt, recs in data.get("cb_daily", {}).items():
        for r in recs:
            cb_rows.append([
                dt, r.get('ts_code',''), r.get('close',''), r.get('vol',''),
                r.get('amount',''), r.get('pct_chg',''), r.get('pre_close',''),
                r.get('open',''), r.get('high',''), r.get('low','')
            ])
    write_csv(CB_DAILY_CSV, cb_headers, cb_rows)
    log(f"    cb_daily.csv: {len(cb_rows)} 行")
    
    # 2. stk_daily.csv
    stk_headers = ['ts_code', 'trade_date', 'close', 'pct_chg']
    stk_rows = []
    for stk_code, date_map in data.get("stk_daily", {}).items():
        for dt, vals in date_map.items():
            stk_rows.append([stk_code, dt, vals.get('close',''), vals.get('pct_chg','')])
    write_csv(STK_DAILY_CSV, stk_headers, stk_rows)
    log(f"    stk_daily.csv: {len(stk_rows)} 行")
    
    # 3. idx_daily.csv
    idx_headers = ['ts_code', 'trade_date', 'close', 'pct_chg', 'amount']
    idx_rows = []
    for idx_code, date_map in data.get("idx_daily", {}).items():
        for dt, vals in date_map.items():
            idx_rows.append([
                idx_code, dt, vals.get('close',''), vals.get('pct_chg',''),
                vals.get('amount','')
            ])
    write_csv(IDX_DAILY_CSV, idx_headers, idx_rows)
    log(f"    idx_daily.csv: {len(idx_rows)} 行")
    
    # 4. cb_basic.csv
    cb_map = data.get("cb_map", {})
    basic_headers = ['ts_code', 'stk_code', 'conv_price', 'maturity_date',
                     'list_date', 'bond_short_name', 'par']
    basic_rows = []
    for ts_code, info in cb_map.items():
        basic_rows.append([
            ts_code, info.get('stk_code',''), info.get('conv_price',''),
            info.get('maturity_date',''), info.get('list_date',''),
            info.get('bond_short_name',''), info.get('par', 100)
        ])
    write_csv(CB_BASIC_CSV, basic_headers, basic_rows)
    log(f"    cb_basic.csv: {len(basic_rows)} 行")
    
    log("  ✅ 迁移完成")
    return True


# ═══ 增量拉取 ═══

def fetch_cb_daily_incremental(new_dates):
    """只拉新日期的转债日行情，追加到CSV"""
    if not new_dates:
        return
    cb_headers = ['trade_date', 'ts_code', 'close', 'vol', 'amount', 'pct_chg',
                  'pre_close', 'open', 'high', 'low']
    new_rows = []
    for i, dt in enumerate(sorted(new_dates)):
        log(f"  [{i+1}/{len(new_dates)}] cb_daily {dt}...")
        fields, items = ts_api("cb_daily", {"trade_date": dt})
        if not fields:
            continue
        records = [dict(zip(fields, it)) for it in items]
        active = [r for r in records if r.get("vol", 0) > 0]
        for r in active:
            new_rows.append([
                dt, r.get('ts_code',''), r.get('close',''), r.get('vol',''),
                r.get('amount',''), r.get('pct_chg',''), r.get('pre_close',''),
                r.get('open',''), r.get('high',''), r.get('low','')
            ])
        time.sleep(0.3)
    if new_rows:
        append_csv(CB_DAILY_CSV, cb_headers, new_rows)
    log(f"  新增 {len(new_rows)} 行转债行情")


def fetch_cb_basic_fresh():
    """转债基本信息（每次全量更新覆盖）"""
    log("  拉取 cb_basic...")
    fields, items = ts_api("cb_basic", {})
    if not fields:
        log("  ⚠️ cb_basic 拉取失败，使用已有CSV")
        return
    records = [dict(zip(fields, it)) for it in items]
    basic_headers = ['ts_code', 'stk_code', 'conv_price', 'maturity_date',
                     'list_date', 'bond_short_name', 'par']
    basic_rows = []
    for cb in records:
        ts_code = cb.get("ts_code")
        if not ts_code or not cb.get("list_date"):
            continue
        basic_rows.append([
            ts_code, cb.get('stk_code',''), cb.get('conv_price',''),
            cb.get('maturity_date',''), cb.get('list_date',''),
            cb.get('bond_short_name',''), cb.get('par', 100)
        ])
    write_csv(CB_BASIC_CSV, basic_headers, basic_rows)
    log(f"  cb_basic.csv: {len(basic_rows)} 只转债")


def fetch_stk_daily_incremental(stk_codes, new_dates):
    """只拉转债对应正股行情（并发按个股拉取，不再拉全市场）"""
    if not new_dates or not stk_codes:
        return
    from concurrent.futures import ThreadPoolExecutor, as_completed
    stk_headers = ['ts_code', 'trade_date', 'close', 'pct_chg']
    start_date = min(new_dates)
    end_date = max(new_dates)
    date_set = set(new_dates)
    stk_list = sorted(stk_codes)

    def fetch_one(ts_code):
        fields, items = ts_api("daily", {
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
        }, fields="ts_code,trade_date,close,pct_chg", retries=2)
        rows = []
        if fields:
            for it in items:
                rec = dict(zip(fields, it))
                if rec.get("trade_date") in date_set:
                    rows.append([rec["ts_code"], rec["trade_date"],
                                 rec["close"], rec["pct_chg"]])
        return rows

    new_rows = []
    done = 0
    WORKERS = 8
    log(f"  并发拉取 {len(stk_list)} 只正股（{WORKERS} 线程）...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_one, code): code for code in stk_list}
        for fut in as_completed(futures):
            done += 1
            try:
                new_rows.extend(fut.result())
            except Exception as e:
                log(f"  ⚠️ {futures[fut]}: {e}")
            if done % 100 == 0:
                log(f"  ... {done}/{len(stk_list)}")
    if new_rows:
        append_csv(STK_DAILY_CSV, stk_headers, new_rows)
    log(f"  新增 {len(new_rows)} 行正股行情（{len(stk_list)}只个股并发拉取）")


def fetch_idx_daily_incremental(index_codes, new_dates):
    """只拉新日期的指数行情，追加到CSV"""
    if not new_dates or not index_codes:
        return
    idx_headers = ['ts_code', 'trade_date', 'close', 'pct_chg', 'amount']
    start_date = min(new_dates)
    end_date = max(new_dates)
    new_rows = []
    for idx_code in index_codes:
        log(f"  拉取 index {idx_code} ({start_date}~{end_date})...")
        fields, items = ts_api("index_daily", {
            "ts_code": idx_code,
            "start_date": start_date,
            "end_date": end_date
        }, fields="ts_code,trade_date,close,pct_chg,amount")
        if not fields:
            continue
        for it in items:
            rec = dict(zip(fields, it))
            if rec["trade_date"] in new_dates:
                new_rows.append([rec["ts_code"], rec["trade_date"],
                                rec["close"], rec["pct_chg"], rec["amount"]])
        time.sleep(0.3)
    if new_rows:
        append_csv(IDX_DAILY_CSV, idx_headers, new_rows)
    log(f"  新增 {len(new_rows)} 行指数行情")


# ═══ 从 CSV 重建 JSON ═══

def build_json_from_csv(dates):
    """从CSV文件重建 cb_data.json（格式与原版完全一致）"""
    
    # 1. cb_map（从 cb_basic.csv）
    headers, rows = read_csv(CB_BASIC_CSV)
    cb_map = {}
    if headers:
        for row in rows:
            rec = dict(zip(headers, row))
            ts_code = rec.get('ts_code')
            if not ts_code:
                continue
            list_date = rec.get('list_date', '')
            delist_date = rec.get('delist_date', '')
            if not list_date:
                continue
            if delist_date and dates and delist_date <= dates[0]:
                continue
            conv_price = rec.get('conv_price', '')
            cb_map[ts_code] = {
                "stk_code": rec.get('stk_code') or None,
                "conv_price": float(conv_price) if conv_price else None,
                "maturity_date": rec.get('maturity_date') or None,
                "list_date": list_date,
                "bond_short_name": rec.get('bond_short_name') or None,
                "par": float(rec.get('par', 100)) if rec.get('par') else 100,
            }
    
    # 2. cb_daily（从 cb_daily.csv）
    headers, rows = read_csv(CB_DAILY_CSV)
    cb_daily = defaultdict(list)
    date_set = set(dates) if dates else None
    if headers:
        for row in rows:
            rec = dict(zip(headers, row))
            dt = rec.get('trade_date', '')
            if date_set and dt not in date_set:
                continue
            entry = {"ts_code": rec.get('ts_code', '')}
            for key in ['close', 'vol', 'amount', 'pct_chg', 'pre_close', 'open', 'high', 'low']:
                val = rec.get(key, '')
                if val != '' and val is not None:
                    try:
                        entry[key] = float(val)
                    except (ValueError, TypeError):
                        entry[key] = None
                else:
                    entry[key] = None
            cb_daily[dt].append(entry)
    
    # 3. stk_daily（从 stk_daily.csv）
    headers, rows = read_csv(STK_DAILY_CSV)
    stk_daily = defaultdict(dict)
    if headers:
        for row in rows:
            rec = dict(zip(headers, row))
            stk_code = rec.get('ts_code', '')
            dt = rec.get('trade_date', '')
            if date_set and dt not in date_set:
                continue
            close_val = rec.get('close', '')
            pct_val = rec.get('pct_chg', '')
            stk_daily[stk_code][dt] = {
                "close": float(close_val) if close_val else None,
                "pct_chg": float(pct_val) if pct_val else None,
            }
    
    # 4. idx_daily（从 idx_daily.csv）
    headers, rows = read_csv(IDX_DAILY_CSV)
    idx_daily = defaultdict(dict)
    if headers:
        for row in rows:
            rec = dict(zip(headers, row))
            idx_code = rec.get('ts_code', '')
            dt = rec.get('trade_date', '')
            if date_set and dt not in date_set:
                continue
            entry = {"ts_code": idx_code, "trade_date": dt}
            for key in ['close', 'pct_chg', 'amount']:
                val = rec.get(key, '')
                if val != '' and val is not None:
                    try:
                        entry[key] = float(val)
                    except (ValueError, TypeError):
                        entry[key] = None
                else:
                    entry[key] = None
            idx_daily[idx_code][dt] = entry
    
    output = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dates": dates,
            "n_dates": len(dates),
            "n_cb": len(cb_map),
        },
        "cb_map": dict(cb_map),
        "cb_daily": dict(cb_daily),
        "stk_daily": dict(stk_daily),
        "idx_daily": dict(idx_daily),
    }
    
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    
    fsize = os.path.getsize(OUTPUT_JSON) / 1024 / 1024
    log(f"\n✅ 输出: {OUTPUT_JSON} ({fsize:.1f} MB)")
    return output


# ═══ 主流程 ═══

def main():
    log("=" * 50)
    log("转债指增策略环境 — 数据拉取（CSV增量模式）")
    log("=" * 50)

    # 0. 首次迁移：从已有 JSON 导入 CSV
    log("\n[0] 检查CSV / 迁移...")
    migrate_from_json()

    # 1. 获取交易日
    log("\n[1/5] 获取交易日...")
    dates = get_trade_dates(LOOKBACK_DAYS)
    
    if not dates:
        log("  ⚠️ Tushare 连不上，使用已有CSV数据")
        # 从 CSV 推断日期
        existing_dates = sorted(get_csv_dates(CB_DAILY_CSV))
        if not existing_dates:
            log("  ERROR: 无交易日且无CSV数据")
            sys.exit(1)
        dates = existing_dates
        log(f"  从CSV恢复: {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")
        # 直接从CSV生成JSON
        build_json_from_csv(dates)
        return
    
    log(f"  {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    # 2. 找出需要增量拉取的日期
    existing_cb_dates = get_csv_dates(CB_DAILY_CSV)
    new_dates = sorted(set(dates) - existing_cb_dates)
    
    if not new_dates:
        log(f"\n  所有 {len(dates)} 天数据已在CSV中，无需拉取")
    else:
        log(f"\n  需要增量拉取: {len(new_dates)} 天 ({new_dates[0]} ~ {new_dates[-1]})")
    
    # 3. 转债基本信息（增量模式下复用已有CSV，每周一或不存在时才全量更新）
    log("\n[2/5] 转债基本信息...")
    cb_basic_exists = os.path.exists(CB_BASIC_CSV) and os.path.getsize(CB_BASIC_CSV) > 1000
    is_monday = datetime.now().weekday() == 0
    if cb_basic_exists and not is_monday:
        log("  cb_basic.csv 已存在，跳过全量拉取（每周一自动更新）")
    else:
        fetch_cb_basic_fresh()
    
    # 读取 cb_map 用于确定正股代码
    headers, rows = read_csv(CB_BASIC_CSV)
    cb_map = {}
    for row in rows:
        rec = dict(zip(headers, row))
        ts_code = rec.get('ts_code')
        if ts_code and rec.get('list_date'):
            cb_map[ts_code] = rec
    log(f"  存续转债: {len(cb_map)} 只")

    # 4. 增量拉取
    if new_dates:
        new_dates_set = set(new_dates)
        
        log("\n[3/5] 转债日行情（增量）...")
        fetch_cb_daily_incremental(new_dates)
        
        log("\n[4/5] 正股行情（增量）...")
        stk_codes = set(v.get('stk_code') for v in cb_map.values() if v.get('stk_code'))
        log(f"  需要 {len(stk_codes)} 只正股")
        fetch_stk_daily_incremental(stk_codes, new_dates_set)
        
        log("\n[5/5] 指数行情（增量）...")
        index_codes = ["000852.SH", "932000.CSI"]
        fetch_idx_daily_incremental(index_codes, new_dates_set)
    else:
        log("\n[3-5] 跳过拉取（数据已完整）")

    # 5. 从CSV重建JSON
    log("\n[输出] 从CSV生成 cb_data.json...")
    build_json_from_csv(dates)
    
    log(f"   {dates[0]} ~ {dates[-1]} ({len(dates)}天)")
    log(f"   转债: {len(cb_map)} 只")


if __name__ == "__main__":
    main()
