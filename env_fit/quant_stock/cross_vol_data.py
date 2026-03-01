#!/usr/bin/env python3
"""计算全A个股截面波动率（cross-sectional volatility）"""

import json, time, requests, numpy as np
from datetime import datetime

TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"
OUT = __file__.replace("cross_vol_data.py", "cross_vol.json")

def ts_post(api_name, params, fields=""):
    s = requests.Session()
    s.trust_env = False
    for attempt in range(3):
        try:
            r = s.post(API, json={"api_name": api_name, "token": TOKEN, "params": params, "fields": fields}, timeout=30)
            d = r.json()
            if d.get("code") == 0:
                return d["data"]
            print(f"API error: {d.get('msg')}")
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return None

def get_recent_trade_dates(n=5):
    today = datetime.now().strftime("%Y%m%d")
    data = ts_post("trade_cal", {"exchange": "SSE", "start_date": "20260201", "end_date": today, "is_open": "1"})
    if not data:
        return []
    dates = sorted(data["items"], key=lambda x: x[data["fields"].index("cal_date")], reverse=True)
    idx = data["fields"].index("cal_date")
    return [row[idx] for row in dates[:n]][::-1]

def main():
    print("Getting trade dates...")
    dates = get_recent_trade_dates(5)
    print(f"Trade dates: {dates}")

    results = []
    for d in dates:
        print(f"Fetching {d}...")
        data = ts_post("daily", {"trade_date": d}, "ts_code,trade_date,pct_chg")
        if not data or not data["items"]:
            print(f"  No data for {d}")
            continue
        idx = data["fields"].index("pct_chg")
        vals = [row[idx] for row in data["items"] if row[idx] is not None]
        arr = np.array(vals)
        results.append({
            "date": d,
            "cross_vol": round(float(np.std(arr, ddof=1)), 4),
            "stock_count": len(vals),
            "mean_return": round(float(np.mean(arr)), 4)
        })
        print(f"  stocks={len(vals)}, vol={results[-1]['cross_vol']}, mean={results[-1]['mean_return']}")
        time.sleep(0.5)

    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data": results
    }
    with open(OUT, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUT}")
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
