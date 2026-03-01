#!/usr/bin/env python3
"""扩展截面波动率历史到120个交易日"""

import json, time, sys, requests, numpy as np
from datetime import datetime

# Force unbuffered output
print = lambda *a, **k: (sys.stdout.write(' '.join(map(str, a)) + k.get('end', '\n')), sys.stdout.flush())


TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"
OUT = __file__.replace("cross_vol_extend.py", "cross_vol.json")

def ts_post(api_name, params, fields="", retries=5):
    s = requests.Session()
    s.trust_env = False  # 直连不走代理
    for attempt in range(retries):
        try:
            r = s.post(API, json={"api_name": api_name, "token": TOKEN, "params": params, "fields": fields}, timeout=30)
            d = r.json()
            if d.get("code") == 0:
                return d["data"]
            print(f"  API error: {d.get('msg')}")
        except Exception as e:
            print(f"  Attempt {attempt+1}/{retries} failed: {e}")
        time.sleep(3 * (attempt + 1))
    return None

def get_trade_dates(n=120):
    """获取最近n个交易日，分段拉取"""
    today = datetime.now().strftime("%Y%m%d")
    # 120个交易日大约需要回溯170天，取200天余量
    data = ts_post("trade_cal", {"exchange": "SSE", "start_date": "20250701", "end_date": today, "is_open": "1"})
    if not data:
        return []
    idx = data["fields"].index("cal_date")
    dates = sorted([row[idx] for row in data["items"]], reverse=True)
    return dates[:n][::-1]

def load_existing():
    try:
        with open(OUT) as f:
            d = json.load(f)
        return {item["date"]: item for item in d.get("data", [])}
    except:
        return {}

def main():
    print("Getting 120 trade dates...")
    dates = get_trade_dates(120)
    print(f"Got {len(dates)} dates: {dates[0]} ~ {dates[-1]}")

    existing = load_existing()
    print(f"Existing records: {len(existing)}")

    results = dict(existing)
    todo = [d for d in dates if d not in results]
    print(f"Need to fetch: {len(todo)} dates")

    for i, d in enumerate(todo):
        print(f"[{i+1}/{len(todo)}] Fetching {d}...")
        data = ts_post("daily", {"trade_date": d}, "ts_code,trade_date,pct_chg")
        if not data or not data["items"]:
            print(f"  No data for {d}, skipping")
            continue
        idx = data["fields"].index("pct_chg")
        vals = [row[idx] for row in data["items"] if row[idx] is not None]
        arr = np.array(vals)
        results[d] = {
            "date": d,
            "cross_vol": round(float(np.std(arr, ddof=1)), 4),
            "stock_count": len(vals),
            "mean_return": round(float(np.mean(arr)), 4)
        }
        print(f"  stocks={len(vals)}, vol={results[d]['cross_vol']}")

        # 每10条保存一次，防止中断丢失
        if (i + 1) % 10 == 0:
            save(results, dates)
            print(f"  [checkpoint saved, {len(results)} records]")

        time.sleep(0.8)

    save(results, dates)
    print(f"\nDone! Total {len([d for d in dates if d in results])} records saved to {OUT}")

def save(results, dates):
    ordered = [results[d] for d in sorted(results.keys()) if d in results]
    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_days": len(ordered),
        "data": ordered
    }
    with open(OUT, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
