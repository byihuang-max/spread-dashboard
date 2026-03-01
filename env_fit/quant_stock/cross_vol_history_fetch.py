#!/usr/bin/env python3
"""拉取 2025-01-01 ~ 2026-02-28 全A截面波动率，增量保存"""

import json, time, requests, numpy as np
from datetime import datetime
import os, sys

TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"
DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "cross_vol_history.json")
PROGRESS = os.path.join(DIR, ".cross_vol_progress.json")

def ts_post(api_name, params, fields=""):
    s = requests.Session()
    s.trust_env = False
    for attempt in range(3):
        try:
            r = s.post(API, json={"api_name": api_name, "token": TOKEN, "params": params, "fields": fields}, timeout=30)
            d = r.json()
            if d.get("code") == 0:
                return d["data"]
            print(f"  API error: {d.get('msg')}", flush=True)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}", flush=True)
        time.sleep(2)
    return None

def get_all_trade_dates():
    MONTHS = []
    for y in [2025, 2026]:
        for m in range(1, 13):
            start = f"{y}{m:02d}01"
            end = f"{y}{m+1:02d}01" if m < 12 else f"{y+1}0101"
            if start >= "20260301": break
            if end > "20260228": end = "20260228"
            MONTHS.append((start, end))
    
    all_dates = []
    for start, end in MONTHS:
        data = ts_post("trade_cal", {"exchange": "SSE", "start_date": start, "end_date": end, "is_open": "1"})
        if data:
            idx = data["fields"].index("cal_date")
            all_dates.extend([row[idx] for row in data["items"]])
        time.sleep(0.3)
    return sorted(set(all_dates))

def main():
    # Load progress
    results = []
    done_dates = set()
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            results = json.load(f)
        done_dates = {r["date"] for r in results}
        print(f"Resuming: {len(results)} already done", flush=True)

    print("Getting trade dates...", flush=True)
    all_dates = get_all_trade_dates()
    remaining = [d for d in all_dates if d not in done_dates]
    print(f"Total: {len(all_dates)}, remaining: {len(remaining)}", flush=True)

    for i, d in enumerate(remaining):
        print(f"[{len(done_dates)+i+1}/{len(all_dates)}] {d}...", end=" ", flush=True)
        data = ts_post("daily", {"trade_date": d}, "ts_code,pct_chg")
        if not data or not data["items"]:
            print("NO DATA", flush=True)
            continue
        idx = data["fields"].index("pct_chg")
        vals = [row[idx] for row in data["items"] if row[idx] is not None]
        arr = np.array(vals)
        cv = round(float(np.std(arr, ddof=1)), 4)
        results.append({"date": d, "cross_vol": cv, "stock_count": len(vals)})
        print(f"n={len(vals)} vol={cv}", flush=True)
        
        # Save progress every 10 dates
        if (i + 1) % 10 == 0:
            with open(PROGRESS, "w") as f:
                json.dump(results, f)
        time.sleep(0.3)

    # Final save
    results.sort(key=lambda x: x["date"])
    with open(PROGRESS, "w") as f:
        json.dump(results, f)
    
    output = {"update_time": datetime.now().strftime("%Y-%m-%d %H:%M"), "data": results}
    with open(OUT, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    if os.path.exists(PROGRESS):
        os.remove(PROGRESS)
    
    print(f"\nDone! {len(results)} data points saved to {OUT}", flush=True)
    print(f"Date range: {results[0]['date']} ~ {results[-1]['date']}", flush=True)

if __name__ == "__main__":
    main()
