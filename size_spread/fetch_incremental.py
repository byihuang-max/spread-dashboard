#!/usr/bin/env python3
"""增量拉取 style_spread 所需的全部原始日线数据。
存储：CSV 为真相源（append-only），JSON cache 为快速读取层。

CSV 文件：
- ss_index_daily.csv  （指数日线：trade_date, ts_code, close, pct_chg）
- ss_sw_daily.csv     （申万行业日线：trade_date, ts_code, pct_change, amount）

JSON 文件：
- style_spread_cache.json （保留，供 compute_spreads.py 快速读取）

首次运行：如果已有 JSON cache 但无 CSV，自动从 JSON 迁移到 CSV。
后续运行：每个代码各自从 CSV 中最后日期的下一天开始拉增量，同时写 CSV + JSON。
"""
import json, os, time, csv, requests
from datetime import datetime, timedelta
from collections import defaultdict

# === Tushare ===
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TS_URL = "https://api.tushare.pro"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "style_spread_cache.json")
IDX_CSV = os.path.join(BASE_DIR, "ss_index_daily.csv")
SW_CSV = os.path.join(BASE_DIR, "ss_sw_daily.csv")

IDX_HEADERS = ['trade_date', 'ts_code', 'close', 'pct_chg']
SW_HEADERS = ['trade_date', 'ts_code', 'pct_change', 'amount']

# 指数代码（index_daily 接口）
INDEX_CODES = {
    '000922.CSI': '中证红利', '000688.SH': '科创50',
    '399303.SZ': '微盘股', '000985.CSI': '中证全指',
    '932000.CSI': '中证2000', '000300.SH': '沪深300',
    '399006.SZ': '创业板指',
}

# 申万行业代码（sw_daily 接口）
SW_CODES = {
    '801010.SI': '农林牧渔', '801030.SI': '基础化工', '801040.SI': '钢铁',
    '801050.SI': '有色金属', '801080.SI': '电子', '801880.SI': '汽车',
    '801110.SI': '家用电器', '801120.SI': '食品饮料', '801130.SI': '纺织服饰',
    '801140.SI': '轻工制造', '801150.SI': '医药生物', '801160.SI': '公用事业',
    '801170.SI': '交通运输', '801180.SI': '房地产', '801200.SI': '商贸零售',
    '801210.SI': '社会服务', '801780.SI': '银行', '801790.SI': '非银金融',
    '801230.SI': '综合', '801710.SI': '建筑材料', '801720.SI': '建筑装饰',
    '801730.SI': '电力设备', '801890.SI': '机械设备', '801740.SI': '国防军工',
    '801750.SI': '计算机', '801760.SI': '传媒', '801770.SI': '通信',
    '801950.SI': '煤炭', '801960.SI': '石油石化', '801970.SI': '环保',
    '801980.SI': '美容护理',
}


# ── Tushare 请求 ──

def ts(api, params, fields=''):
    body = {"api_name": api, "token": TS_TOKEN, "params": params}
    if fields:
        body["fields"] = fields
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json=body, timeout=90, proxies={'http': None, 'https': None})
            if not r.text.strip():
                print(f"  空响应，重试 {attempt+1}/3...")
                time.sleep(2)
                continue
            d = r.json()
            if d.get("data") and d["data"].get("fields") and d["data"].get("items"):
                return [dict(zip(d["data"]["fields"], row)) for row in d["data"]["items"]]
            return []
        except Exception as e:
            print(f"  请求失败: {e}，重试 {attempt+1}/3...")
            time.sleep(2)
    return []


# ── CSV 读写 ──

def read_csv(path, headers):
    """读取 CSV，返回行列表 [{col: val, ...}, ...]"""
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(path, headers, rows):
    """全量写入 CSV"""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def append_csv(path, headers, rows):
    """追加写入 CSV（如果文件不存在则创建含表头）"""
    need_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if need_header:
            w.writeheader()
        w.writerows(rows)


def get_csv_last_dates(path, code_col='ts_code'):
    """从 CSV 获取每个代码的最后日期 {code: 'YYYYMMDD'}"""
    rows = read_csv(path, [])
    last = {}
    for r in rows:
        code = r.get(code_col, '')
        dt = r.get('trade_date', '')
        if code and dt:
            if code not in last or dt > last[code]:
                last[code] = dt
    return last


# ── JSON cache 读写 ──

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"last_updated": "", "index_daily": {}, "sw_daily": {}}


def save_cache(cache):
    cache["last_updated"] = datetime.today().strftime("%Y%m%d")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── 迁移：从已有 JSON cache → CSV ──

def migrate_json_to_csv(cache):
    """首次迁移：把 JSON cache 中的数据导出到 CSV"""
    migrated = False

    # 指数
    if not os.path.exists(IDX_CSV) and cache.get("index_daily"):
        print("  📦 从 JSON cache 迁移指数数据到 ss_index_daily.csv...")
        rows = []
        for code, entry in cache["index_daily"].items():
            for dt, vals in sorted(entry.get("data", {}).items()):
                rows.append({
                    'trade_date': dt,
                    'ts_code': code,
                    'close': vals.get('close', ''),
                    'pct_chg': vals.get('pct_chg', ''),
                })
        write_csv(IDX_CSV, IDX_HEADERS, rows)
        print(f"    ss_index_daily.csv: {len(rows)} 行")
        migrated = True

    # 申万行业
    if not os.path.exists(SW_CSV) and cache.get("sw_daily"):
        print("  📦 从 JSON cache 迁移申万行业数据到 ss_sw_daily.csv...")
        rows = []
        for code, entry in cache["sw_daily"].items():
            for dt, vals in sorted(entry.get("data", {}).items()):
                rows.append({
                    'trade_date': dt,
                    'ts_code': code,
                    'pct_change': vals.get('pct_change', ''),
                    'amount': vals.get('amount', ''),
                })
        write_csv(SW_CSV, SW_HEADERS, rows)
        print(f"    ss_sw_daily.csv: {len(rows)} 行")
        migrated = True

    return migrated


# ── 工具函数 ──

def next_day(date_str):
    d = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
    return d.strftime("%Y%m%d")


def full_start():
    return (datetime.today() - timedelta(days=400)).strftime("%Y%m%d")


# ── 主流程 ──

def fetch_incremental():
    cache = load_cache()
    today = datetime.today().strftime("%Y%m%d")

    # 首次迁移
    migrate_json_to_csv(cache)

    # 从 CSV 获取每个代码的最后日期
    idx_last = get_csv_last_dates(IDX_CSV)
    sw_last = get_csv_last_dates(SW_CSV)

    stats = {"index_new": 0, "index_skip": 0, "sw_new": 0, "sw_skip": 0}

    # --- 指数 ---
    print("=" * 50)
    print("拉取指数数据（index_daily）")
    print("=" * 50)
    for code, name in INDEX_CODES.items():
        last = idx_last.get(code)
        if last and last >= today:
            print(f"  {name}({code}): 已是最新 ({last})，跳过")
            stats["index_skip"] += 1
            continue

        start = next_day(last) if last else full_start()
        print(f"  {name}({code}): 从 {start} 拉取...", end='', flush=True)

        data = ts('index_daily', {'ts_code': code, 'start_date': start, 'end_date': today},
                   fields='trade_date,close,pct_chg')

        # 写入 JSON cache
        if code not in cache.setdefault("index_daily", {}):
            cache["index_daily"][code] = {"name": name, "data": {}}

        csv_rows = []
        count = 0
        for item in (data or []):
            dt = item['trade_date']
            close = item.get('close')
            pct_chg = item.get('pct_chg')

            # JSON cache
            cache["index_daily"][code]["data"][dt] = {
                "close": close,
                "pct_chg": pct_chg,
            }
            # CSV row
            csv_rows.append({
                'trade_date': dt,
                'ts_code': code,
                'close': close if close is not None else '',
                'pct_chg': pct_chg if pct_chg is not None else '',
            })
            count += 1

        # 追加 CSV
        if csv_rows:
            append_csv(IDX_CSV, IDX_HEADERS, csv_rows)

        total = len(cache["index_daily"][code]["data"])
        print(f" +{count}条 (总{total}条)")
        stats["index_new"] += count

    # --- 申万行业 ---
    print()
    print("=" * 50)
    print("拉取申万行业数据（sw_daily）")
    print("=" * 50)
    for code, name in SW_CODES.items():
        last = sw_last.get(code)
        # 修复：只有当 last 日期是今天或未来才跳过（避免周末后首个交易日被跳过）
        if last and last >= today:
            print(f"  {name}({code}): 已是最新 ({last})，跳过")
            stats["sw_skip"] += 1
            continue

        # 如果有历史数据，从最后日期的下一天开始拉；否则全量拉
        start = next_day(last) if last else full_start()
        print(f"  {name}({code}): 从 {start} 拉取...", end='', flush=True)

        data = ts('sw_daily', {'ts_code': code, 'start_date': start, 'end_date': today},
                   fields='trade_date,pct_change,amount')

        # 写入 JSON cache
        if code not in cache.setdefault("sw_daily", {}):
            cache["sw_daily"][code] = {"name": name, "data": {}}

        csv_rows = []
        count = 0
        for item in (data or []):
            dt = item['trade_date']
            pct_change = item.get('pct_change')
            amount = item.get('amount')

            # JSON cache
            cache["sw_daily"][code]["data"][dt] = {
                "pct_change": pct_change,
                "amount": amount,
            }
            # CSV row
            csv_rows.append({
                'trade_date': dt,
                'ts_code': code,
                'pct_change': pct_change if pct_change is not None else '',
                'amount': amount if amount is not None else '',
            })
            count += 1

        # 追加 CSV
        if csv_rows:
            append_csv(SW_CSV, SW_HEADERS, csv_rows)

        total = len(cache["sw_daily"][code]["data"])
        print(f" +{count}条 (总{total}条)")
        stats["sw_new"] += count

    # --- 保存 JSON cache ---
    save_cache(cache)

    # --- 统计 ---
    cache_kb = os.path.getsize(CACHE_PATH) / 1024
    idx_csv_kb = os.path.getsize(IDX_CSV) / 1024 if os.path.exists(IDX_CSV) else 0
    sw_csv_kb = os.path.getsize(SW_CSV) / 1024 if os.path.exists(SW_CSV) else 0

    print()
    print("=" * 50)
    print("统计摘要")
    print("=" * 50)
    print(f"  指数: 新增 {stats['index_new']} 条, 跳过 {stats['index_skip']} 个")
    print(f"  行业: 新增 {stats['sw_new']} 条, 跳过 {stats['sw_skip']} 个")
    print(f"  文件大小:")
    print(f"    JSON cache: {cache_kb:.1f} KB")
    print(f"    ss_index_daily.csv: {idx_csv_kb:.1f} KB")
    print(f"    ss_sw_daily.csv: {sw_csv_kb:.1f} KB")

    # 各代码条数
    print()
    print("各代码数据条数:")
    for code in INDEX_CODES:
        entry = cache["index_daily"].get(code, {})
        n = len(entry.get("data", {}))
        print(f"  {INDEX_CODES[code]:8s} ({code}): {n}条")
    for code in SW_CODES:
        entry = cache["sw_daily"].get(code, {})
        n = len(entry.get("data", {}))
        print(f"  {SW_CODES[code]:8s} ({code}): {n}条")

    print(f"\n✅ 完成（CSV + JSON 双写）")


# ── rebuild: 从 CSV 重建 JSON cache ──

def rebuild_cache_from_csv():
    """从 CSV 重建 JSON cache（灾难恢复用）"""
    print("🔄 从 CSV 重建 JSON cache...")
    cache = {"last_updated": datetime.today().strftime("%Y%m%d"), "index_daily": {}, "sw_daily": {}}

    # 指数
    idx_rows = read_csv(IDX_CSV, IDX_HEADERS)
    for r in idx_rows:
        code = r['ts_code']
        if code not in cache["index_daily"]:
            cache["index_daily"][code] = {"name": INDEX_CODES.get(code, code), "data": {}}
        close = r.get('close', '')
        pct_chg = r.get('pct_chg', '')
        cache["index_daily"][code]["data"][r['trade_date']] = {
            "close": float(close) if close else None,
            "pct_chg": float(pct_chg) if pct_chg else None,
        }
    print(f"  指数: {len(idx_rows)} 行")

    # 申万
    sw_rows = read_csv(SW_CSV, SW_HEADERS)
    for r in sw_rows:
        code = r['ts_code']
        if code not in cache["sw_daily"]:
            cache["sw_daily"][code] = {"name": SW_CODES.get(code, code), "data": {}}
        pct_change = r.get('pct_change', '')
        amount = r.get('amount', '')
        cache["sw_daily"][code]["data"][r['trade_date']] = {
            "pct_change": float(pct_change) if pct_change else None,
            "amount": float(amount) if amount else None,
        }
    print(f"  行业: {len(sw_rows)} 行")

    save_cache(cache)
    print(f"  ✅ JSON cache 已重建 ({os.path.getsize(CACHE_PATH)/1024:.1f} KB)")


if __name__ == "__main__":
    import sys
    t0 = time.time()

    if '--rebuild' in sys.argv:
        rebuild_cache_from_csv()
    else:
        fetch_incremental()

    print(f"耗时: {time.time()-t0:.1f}秒")
