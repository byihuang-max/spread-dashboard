"""
mod4_iv_percentile.py - 轻量版
用 opt_daily 的 settle 价格批量拉历史，反推 IV，计算分位数
"""
import json, datetime, requests
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm
from scipy.optimize import brentq

BASE = Path(__file__).parent
CACHE = BASE / "_cache"
CACHE.mkdir(exist_ok=True)

TS_URL = "https://api.tushare.pro"
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"

def ts_api(api_name, **kwargs):
    r = requests.post(TS_URL, json={"api_name": api_name, "token": TS_TOKEN, 
                                    "params": kwargs, "fields": ""}, timeout=20)
    d = r.json()
    if d.get("code") != 0:
        return None, d.get("msg")
    cols = d["data"]["fields"]
    items = d["data"]["items"]
    return [dict(zip(cols, row)) for row in items], None

def black76_iv(opt_price, F, K, T, opt_type='C'):
    if T <= 0 or opt_price <= 0 or F <= 0 or K <= 0:
        return None
    def price(sigma):
        d1 = (np.log(F/K) + 0.5*sigma**2*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        if opt_type == 'C':
            return np.exp(-0.02*T) * (F*norm.cdf(d1) - K*norm.cdf(d2))
        else:
            return np.exp(-0.02*T) * (K*norm.cdf(-d2) - F*norm.cdf(-d1))
    try:
        return brentq(lambda s: price(s) - opt_price, 0.001, 3.0)
    except:
        return None

# 核心品种
SYMBOLS = [
    ("SHFE", "AU", "黄金"),
    ("SHFE", "CU", "铜"),
    ("SHFE", "AG", "白银"),
    ("INE", "SC", "原油"),
    ("CFFEX", "IO", "沪深300"),
    ("CFFEX", "MO", "中证1000"),
]

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=365)

results = []

for exchange, prefix, cn_name in SYMBOLS:
    print(f"\n{prefix}({cn_name})...")
    
    # 拉最近1年的 opt_daily（分批）
    all_opts = []
    for offset in range(0, 365, 30):
        td = (end_date - datetime.timedelta(days=offset)).strftime("%Y%m%d")
        data, err = ts_api("opt_daily", exchange=exchange, trade_date=td,
                          fields="ts_code,trade_date,close,exercise_price")
        if data:
            all_opts.extend([d for d in data if d["ts_code"].startswith(prefix)])
    
    if len(all_opts) < 10:
        print(f"  数据不足: {len(all_opts)}")
        continue
    
    # 按日期分组，每天算一个 ATM IV
    df = pd.DataFrame(all_opts)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["exercise_price"] = pd.to_numeric(df["exercise_price"], errors="coerce")
    df = df.dropna(subset=["close", "exercise_price"])
    
    daily_iv = []
    for td, grp in df.groupby("trade_date"):
        # 拉期货价格
        td_str = td.strftime("%Y%m%d")
        fut_data, _ = ts_api("fut_daily", ts_code=f"{prefix}888.{exchange}",
                            trade_date=td_str, fields="close")
        if not fut_data or not fut_data[0].get("close"):
            continue
        F = float(fut_data[0]["close"])
        
        # 找 ATM
        atm = grp.iloc[(grp["exercise_price"] - F).abs().argmin()]
        opt_price = atm["close"]
        K = atm["exercise_price"]
        T = 30 / 365.0  # 简化：假设30天到期
        
        iv = black76_iv(opt_price, F, K, T, opt_type='C')
        if iv:
            daily_iv.append(iv)
    
    if len(daily_iv) < 10:
        print(f"  IV样本不足: {len(daily_iv)}")
        continue
    
    # 当前 IV（最后一个）
    current_iv = daily_iv[-1]
    pct = (np.array(daily_iv) <= current_iv).mean() * 100
    
    results.append({
        "symbol": prefix,
        "cn_name": cn_name,
        "exchange": exchange,
        "current_iv": round(current_iv, 4),
        "iv_1y_mean": round(np.mean(daily_iv), 4),
        "iv_percentile": round(pct, 1),
        "samples": len(daily_iv),
    })
    
    print(f"  ✅ IV={current_iv:.4f}, 分位={pct:.1f}%, 样本={len(daily_iv)}")

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "symbols": results,
}

with open(BASE / "iv_percentile.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(results)} 品种")
