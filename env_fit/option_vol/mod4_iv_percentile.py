"""
mod4_iv_percentile.py
计算各品种 ATM IV 的历史分位数（过去1年，每10个交易日采样）
输出：iv_percentile.json
"""
import re, json, datetime, requests, time
import numpy as np
from pathlib import Path
from scipy.stats import norm
from scipy.optimize import brentq

BASE = Path(__file__).parent
TS_URL = "https://api.tushare.pro"
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"

# 交易所 → 期货/期权后缀
SUFFIX = {"SHFE": "SHF", "DCE": "DCE", "CZCE": "ZCE", "INE": "INE", "CFFEX": "CFX"}

def ts_api(api_name, **kwargs):
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json={"api_name": api_name, "token": TS_TOKEN,
                                            "params": kwargs, "fields": ""}, timeout=20)
            d = r.json()
            if d.get("code") != 0:
                return None, d.get("msg")
            return [dict(zip(d["data"]["fields"], row)) for row in d["data"]["items"]], None
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return None, str(e)

def parse_opt_code(ts_code):
    """AU2605C1000.SHF → (AU, 20260515, C, 1000)"""
    m = re.match(r'([A-Z]+\d?)(\d{4})([CP])(\d+)\.(\w+)', ts_code)
    if not m:
        return None
    sym, yymm, cp, strike, _ = m.groups()
    return sym, f"20{yymm[:2]}{yymm[2:]}15", cp, int(strike)

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

# 品种配置：(交易所API名, 品种前缀, 中文名, 期货主力代码)
SYMBOLS = [
    ("SHFE", "AU", "黄金"),
    ("SHFE", "CU", "铜"),
    ("SHFE", "AG", "白银"),
    ("SHFE", "AL", "铝"),
    ("SHFE", "RU", "橡胶"),
    ("INE",  "SC", "原油"),
    ("DCE",  "I",  "铁矿"),
    ("DCE",  "M",  "豆粕"),
    ("CZCE", "SR", "白糖"),
    ("CZCE", "CF", "棉花"),
    ("CFFEX","IO", "沪深300"),
    ("CFFEX","MO", "中证1000"),
    ("CFFEX","HO", "上证50"),
]

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=365)

# 拉交易日历（用 SSE，通用）
cal, _ = ts_api("trade_cal", exchange="SSE",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"), is_open="1")
trade_days = sorted([c["cal_date"] for c in cal]) if cal else []
sample_days = trade_days[::10]
print(f"交易日: {len(trade_days)}, 采样: {len(sample_days)}")

results = []

for exchange, prefix, cn_name in SYMBOLS:
    sfx = SUFFIX[exchange]
    fut_code = f"{prefix}.{sfx}"
    print(f"\n{prefix}({cn_name})...", flush=True)
    
    iv_series = []
    iv_dates = []
    
    for td in sample_days:
        # 拉期权行情
        daily, err = ts_api("opt_daily", exchange=exchange, trade_date=td,
                           fields="ts_code,close,vol")
        if err or not daily:
            continue
        
        # 过滤该品种的 call
        calls = []
        for d in daily:
            parsed = parse_opt_code(d["ts_code"])
            if not parsed:
                continue
            sym = parsed[0]
            # 匹配前缀（注意 I 和 I2 的区别：DCE 铁矿期权是 I2xxx）
            if sym == prefix or (prefix == "I" and sym == "I2") or (prefix == "M" and sym == "M2"):
                if parsed[2] == 'C':
                    calls.append({**d, "strike": parsed[3], "expire": parsed[1]})
        
        if not calls:
            continue
        
        # 拉期货价格
        fut, _ = ts_api("fut_daily", ts_code=fut_code, trade_date=td, fields="close")
        if not fut or not fut[0].get("close"):
            # 试 prefix + 888
            continue
        
        F = float(fut[0]["close"])
        
        # 找 ATM call（行权价最接近期货价格，且有成交）
        valid = [c for c in calls if c.get("close") and float(c["close"]) > 0]
        if not valid:
            continue
        
        best = min(valid, key=lambda x: abs(x["strike"] - F))
        K = best["strike"]
        opt_price = float(best["close"])
        
        expire_date = datetime.datetime.strptime(best["expire"], "%Y%m%d").date()
        trade_date_d = datetime.datetime.strptime(td, "%Y%m%d").date()
        T_days = (expire_date - trade_date_d).days
        T = T_days / 365.0
        
        if T <= 0.01:
            continue
        
        iv = black76_iv(opt_price, F, K, T, opt_type='C')
        if iv and 0.01 < iv < 2.0:
            iv_series.append(iv)
            iv_dates.append(td)
    
    if len(iv_series) < 5:
        print(f"  样本不足: {len(iv_series)}")
        continue
    
    current_iv = iv_series[-1]
    pct = (np.array(iv_series) <= current_iv).mean() * 100
    
    results.append({
        "symbol": prefix,
        "cn_name": cn_name,
        "exchange": exchange,
        "current_iv": round(current_iv, 4),
        "iv_1y_mean": round(float(np.mean(iv_series)), 4),
        "iv_1y_max": round(float(max(iv_series)), 4),
        "iv_1y_min": round(float(min(iv_series)), 4),
        "iv_percentile": round(pct, 1),
        "samples": len(iv_series),
        "iv_history": [{"date": d, "iv": round(v, 4)} for d, v in zip(iv_dates, iv_series)],
    })
    
    print(f"  ✅ IV={current_iv:.4f}, 分位={pct:.1f}%, 样本={len(iv_series)}")

# 加权汇总
if results:
    weighted_pct = np.mean([r["iv_percentile"] for r in results])
else:
    weighted_pct = 0

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_iv_percentile": round(weighted_pct, 1),
    "symbols": results,
}

with open(BASE / "iv_percentile.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(results)} 品种, 全市场IV分位={weighted_pct:.1f}%")
