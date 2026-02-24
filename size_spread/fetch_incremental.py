#!/usr/bin/env python3
"""增量拉取 style_spread 所需的全部原始日线数据，存入 cache JSON。
首次运行：全量拉 400 天。
后续运行：每个代码各自从 cache 中最后日期的下一天开始拉增量。
"""
import json, os, time, requests
from datetime import datetime, timedelta

# === Tushare ===
TS_TOKEN = "33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd"
TS_URL = "http://lianghua.nanyangqiankun.top"

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style_spread_cache.json")

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


def ts(api, params, fields=''):
    body = {"api_name": api, "token": TS_TOKEN, "params": params}
    if fields:
        body["fields"] = fields
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json=body, timeout=90)
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


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"last_updated": "", "index_daily": {}, "sw_daily": {}}


def save_cache(cache):
    cache["last_updated"] = datetime.today().strftime("%Y%m%d")
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_last_date(cache_section, code):
    """获取某个代码在 cache 中的最后日期，没有则返回 None"""
    entry = cache_section.get(code)
    if entry and entry.get("data"):
        return max(entry["data"].keys())
    return None


def next_day(date_str):
    """YYYYMMDD 格式日期 +1 天"""
    d = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
    return d.strftime("%Y%m%d")


def full_start():
    return (datetime.today() - timedelta(days=400)).strftime("%Y%m%d")


def fetch_incremental():
    cache = load_cache()
    today = datetime.today().strftime("%Y%m%d")
    stats = {"index_new": 0, "index_skip": 0, "sw_new": 0, "sw_skip": 0}

    # --- 指数 ---
    print("=" * 50)
    print("拉取指数数据（index_daily）")
    print("=" * 50)
    for code, name in INDEX_CODES.items():
        last = get_last_date(cache.get("index_daily", {}), code)
        if last and last >= today:
            print(f"  {name}({code}): 已是最新 ({last})，跳过")
            stats["index_skip"] += 1
            continue

        start = next_day(last) if last else full_start()
        print(f"  {name}({code}): 从 {start} 拉取...", end='', flush=True)

        data = ts('index_daily', {'ts_code': code, 'start_date': start, 'end_date': today},
                   fields='trade_date,close,pct_chg')

        if code not in cache.setdefault("index_daily", {}):
            cache["index_daily"][code] = {"name": name, "data": {}}

        count = 0
        for item in (data or []):
            dt = item['trade_date']
            cache["index_daily"][code]["data"][dt] = {
                "close": item.get('close'),
                "pct_chg": item.get('pct_chg'),
            }
            count += 1

        total = len(cache["index_daily"][code]["data"])
        print(f" +{count}条 (总{total}条)")
        stats["index_new"] += count

    # --- 申万行业 ---
    print()
    print("=" * 50)
    print("拉取申万行业数据（sw_daily）")
    print("=" * 50)
    for code, name in SW_CODES.items():
        last = get_last_date(cache.get("sw_daily", {}), code)
        if last and last >= today:
            print(f"  {name}({code}): 已是最新 ({last})，跳过")
            stats["sw_skip"] += 1
            continue

        start = next_day(last) if last else full_start()
        print(f"  {name}({code}): 从 {start} 拉取...", end='', flush=True)

        data = ts('sw_daily', {'ts_code': code, 'start_date': start, 'end_date': today},
                   fields='trade_date,pct_change,amount')

        if code not in cache.setdefault("sw_daily", {}):
            cache["sw_daily"][code] = {"name": name, "data": {}}

        count = 0
        for item in (data or []):
            dt = item['trade_date']
            cache["sw_daily"][code]["data"][dt] = {
                "pct_change": item.get('pct_change'),
                "amount": item.get('amount'),
            }
            count += 1

        total = len(cache["sw_daily"][code]["data"])
        print(f" +{count}条 (总{total}条)")
        stats["sw_new"] += count

    # --- 保存 ---
    save_cache(cache)
    size_kb = os.path.getsize(CACHE_PATH) / 1024

    # --- 统计 ---
    print()
    print("=" * 50)
    print("统计摘要")
    print("=" * 50)
    print(f"  指数: 新增 {stats['index_new']} 条, 跳过 {stats['index_skip']} 个")
    print(f"  行业: 新增 {stats['sw_new']} 条, 跳过 {stats['sw_skip']} 个")
    print(f"  Cache 文件: {CACHE_PATH}")
    print(f"  Cache 大小: {size_kb:.1f} KB")

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

    print(f"\n✅ 完成")


if __name__ == "__main__":
    t0 = time.time()
    fetch_incremental()
    print(f"耗时: {time.time()-t0:.1f}秒")
