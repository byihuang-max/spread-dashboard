"""
mod4_iv_percentile_v2.py
从 opt_daily 的 ts_code 直接解析行权价和到期月，不依赖 opt_basic
计算过去1年 ATM IV 的历史分位数
"""
import re, json, datetime, requests
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

def parse_opt_code(ts_code):
    """AU2605C1000.SHF → (AU, 2026-05, C, 1000)"""
    m = re.match(r'([A-Z]+\d?)(\d{4})([CP])(\d+)\.(\w+)', ts_code)
    if not m:
        return None
    sym, yymm, cp, strike, _ = m.groups()
    expire_date = f"20{yymm[:2]}{yymm[2:]}15"  # 假设每月15日到期
    return sym, expire_date, cp, int(strike)

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
]

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=365)

# 拉交易日历
cal, _ = ts_api("trade_cal", exchange="SHFE",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"), is_open="1")
trade_days = sorted([c["cal_date"] for c in cal]) if cal else []
sample_days = trade_days[::10]  # 每10个交易日采样

print(f"交易日: {len(trade_days)}, 采样: {len(sample_days)}")

results = []

for exchange, prefix, cn_name in SYMBOLS:
    print(f"\n{prefix}({cn_name})...")
    iv_series = []
    
    for td in sample_days:
        daily, err = ts_api("opt_daily", exchange=exchange, trade_date=td,
                           fields="ts_code,close,vol")
        if err or not daily:
            continue
        
        # 过滤该品种的 call
        opts = []
        for d in daily:
            parsed = parse_opt_code(d["ts_code"])
            if parsed and parsed[0] == prefix and parsed[2] == 'C':
                opts.append({**d, "strike": parsed[3], "expire": parsed[1]})
        
        if not opts:
            continue
        
        # 拉期货价格
        fut, _ = ts_api("fut_daily", ts_code=f"{prefix}888.{exchange}",
                       trade_date=td, fields="close")
        if not fut or not fut[0].get("close"):
            continue
        
        F = float(fut[0]["close"])
        
        # 找 ATM call
        best = min(opts, key=lambda x: abs(x["strike"] - F))
        if not best.get("close") or float(best["close"]) <= 0:
            continue
        
        K = best["strike"]
        opt_price = float(best["close"])
        expire_date = datetime.datetime.strptime(best["expire"], "%Y%m%d").date()
        T_days = (expire_date - datetime.datetime.strptime(td, "%Y%m%d").date()).days
        T = T_days / 365.0
        
        if T <= 0:
            continue
        
        iv = black76_iv(opt_price, F, K, T, opt_type='C')
        if iv and 0.01 < iv < 2.0:
            iv_series.append(iv)
    
    if len(iv_series) < 5:
        print(f"  样本不足: {len(iv_series)}")
        continue
    
    current_iv = iv_series[-1]
    pct = (np.array(iv_series) <= current_iv).mean() * 100
    
    results.append({
        "symbol": prefix,
        "cn_name": cn_name,
        "current_iv": round(current_iv, 4),
        "iv_1y_mean": round(np.mean(iv_series), 4),
        "iv_percentile": round(pct, 1),
        "samples": len(iv_series),
    })
    
    print(f"  ✅ IV={current_iv:.4f}, 分位={pct:.1f}%, 样本={len(iv_series)}")

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "symbols": results,
}

with open(BASE / "iv_percentile.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(results)} 品种")
