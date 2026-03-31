"""
mod4_iv_snapshot.py
用当前所有活跃合约的 IV 分布，判断 ATM IV 是否在高位
不回溯历史，只看当前横截面
"""
import json, datetime, requests
import numpy as np
from pathlib import Path
from scipy.stats import norm
from scipy.optimize import brentq

BASE = Path(__file__).parent

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
        return np.exp(-0.02*T) * (K*norm.cdf(-d2) - F*norm.cdf(-d1))
    try:
        return brentq(lambda s: price(s) - opt_price, 0.001, 3.0)
    except:
        return None

SYMBOLS = [
    ("SHFE", "AU", "黄金"),
    ("SHFE", "CU", "铜"),
    ("SHFE", "AG", "白银"),
    ("INE", "SC", "原油"),
    ("CFFEX", "IO", "沪深300"),
    ("CFFEX", "MO", "中证1000"),
]

today = datetime.date.today().strftime("%Y%m%d")
results = []

for exchange, prefix, cn_name in SYMBOLS:
    print(f"{prefix}({cn_name})...", end=" ")
    
    # 1. 拉当前活跃合约基本信息
    basic, err = ts_api("opt_basic", exchange=exchange, fields="ts_code,call_put,exercise_price,delist_date")
    if err or not basic:
        print(f"opt_basic失败")
        continue
    
    active = [b for b in basic if b["ts_code"].startswith(prefix) and b.get("delist_date","") >= today]
    if not active:
        print(f"无活跃合约")
        continue
    
    # 2. 拉当日行情
    daily, err = ts_api("opt_daily", exchange=exchange, trade_date=today,
                       fields="ts_code,close,vol,oi")
    if err or not daily:
        print(f"opt_daily失败")
        continue
    
    daily_map = {d["ts_code"]: d for d in daily}
    
    # 3. 拉期货价格
    fut_data, _ = ts_api("fut_daily", ts_code=f"{prefix}888.{exchange}",
                        trade_date=today, fields="close")
    if not fut_data or not fut_data[0].get("close"):
        print(f"期货价格失败")
        continue
    
    F = float(fut_data[0]["close"])
    
    # 4. 计算所有合约的 IV
    all_iv = []
    atm_iv = None
    atm_vol = 0
    
    for opt in active:
        code = opt["ts_code"]
        if code not in daily_map:
            continue
        price = daily_map[code].get("close")
        if not price or float(price) <= 0:
            continue
        
        K = float(opt["exercise_price"])
        T_days = (datetime.datetime.strptime(opt["delist_date"], "%Y%m%d").date() - datetime.date.today()).days
        T = T_days / 365.0
        
        if T <= 0:
            continue
        
        opt_type = 'C' if opt["call_put"] == 'C' else 'P'
        iv = black76_iv(float(price), F, K, T, opt_type)
        
        if iv:
            all_iv.append(iv)
            # 判断是否 ATM
            if abs(K - F) / F < 0.05:  # 5%以内算ATM
                vol = float(daily_map[code].get("vol", 0))
                if vol > atm_vol:
                    atm_iv = iv
                    atm_vol = vol
    
    if not all_iv or not atm_iv:
        print(f"IV计算失败")
        continue
    
    # ATM IV 在所有 IV 中的分位数
    pct = (np.array(all_iv) <= atm_iv).mean() * 100
    
    results.append({
        "symbol": prefix,
        "cn_name": cn_name,
        "exchange": exchange,
        "current_atm_iv": round(atm_iv, 4),
        "all_iv_mean": round(np.mean(all_iv), 4),
        "atm_iv_percentile": round(pct, 1),
        "contracts_count": len(all_iv),
    })
    
    print(f"ATM_IV={atm_iv:.4f}, 分位={pct:.1f}%, 合约数={len(all_iv)}")

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "symbols": results,
}

with open(BASE / "iv_snapshot.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(results)} 品种")
