#!/usr/bin/env python3
"""拉取 2025-01-01 ~ 2026-02-28 全A截面波动率，按月分段"""

import json, time, requests, numpy as np
from datetime import datetime
import os

TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cross_vol_history.json")

def ts_post(api_name, params, fields=""):
    s = requests.Session()
    s.trust_env = False
    for attempt in range(3):
        try:
            r = s.post(API, json={"api_name": api_name, "token": TOKEN, "params": params, "fields": fields}, timeout=30)
            d = r.json()
            if d.get("code") == 0:
                return d["data"]
            print(f"  API error: {d.get('msg')}")
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return None

# 按月生成区间
MONTHS = []
for y in [2025, 2026]:
    for m in range(1, 13):
        start = f"{y}{m:02d}01"
        if m == 12:
            end = f"{y+1}0101"
        else:
            end = f"{y}{m+1:02d}01"
        if start >= "20260301":
            break
        if end > "20260228":
            end = "20260228"
        MONTHS.append((start, end))

def main():
    # 1) 拿所有交易日
    all_trade_dates = []
    for start, end in MONTHS:
        print(f"Getting trade cal {start}-{end}...")
        data = ts_post("trade_cal", {"exchange": "SSE", "start_date": start, "end_date": end, "is_open": "1"})
        if not data:
            print(f"  Failed to get cal for {start}-{end}")
            continue
        idx = data["fields"].index("cal_date")
        dates = sorted([row[idx] for row in data["items"]])
        all_trade_dates.extend(dates)
        time.sleep(0.3)

    all_trade_dates = sorted(set(all_trade_dates))
    print(f"\nTotal trade dates: {len(all_trade_dates)}")
    print(f"Range: {all_trade_dates[0]} ~ {all_trade_dates[-1]}")

    # 2) 逐日拉行情算截面波动率
    results = []
    for i, d in enumerate(all_trade_dates):
        print(f"[{i+1}/{len(all_trade_dates)}] {d}...", end=" ")
        data = ts_post("daily", {"trade_date": d}, "ts_code,pct_chg")
        if not data or not data["items"]:
            print("NO DATA")
            continue
        idx = data["fields"].index("pct_chg")
        vals = [row[idx] for row in data["items"] if row[idx] is not None]
        arr = np.array(vals)
        cv = round(float(np.std(arr, ddof=1)), 4)
        results.append({"date": d, "cross_vol": cv, "stock_count": len(vals)})
        print(f"n={len(vals)} vol={cv}")
        time.sleep(0.3)

    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data": results
    }
    with open(OUT, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nDone! {len(results)} data points saved to {OUT}")
    print(f"Date range: {results[0]['date']} ~ {results[-1]['date']}")

if __name__ == "__main__":
    main()
