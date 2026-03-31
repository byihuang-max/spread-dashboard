"""
mod5_liquidity_percentile.py
计算各品种期权的流动性历史分位数（成交量+持仓量）
输出：liquidity_percentile.json
"""
import re, json, datetime, requests, time
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent
TS_URL = "https://api.tushare.pro"
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
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
    code = ts_code.split(".")[0]
    m = re.match(r'([A-Z]+\d?)(\d{4})-([CP])-(\d+)', code)
    if m:
        return m.group(1), m.group(3)
    m = re.match(r'([A-Z]+\d?)(\d{4})([CP])(\d+)', code)
    if m:
        return m.group(1), m.group(3)
    m = re.match(r'([A-Z]+)(\d{3})([CP])(\d+)', code)
    if m:
        return m.group(1), m.group(3)
    return None, None

SYMBOLS = [
    ("SHFE", "AU", "黄金"),
    ("SHFE", "CU", "铜"),
    ("SHFE", "AG", "白银"),
    ("SHFE", "AL", "铝"),
    ("SHFE", "RU", "橡胶"),
    ("INE",  "SC", "原油"),
    ("CZCE", "SR", "白糖"),
    ("CZCE", "CF", "棉花"),
    ("CFFEX","IO", "沪深300"),
    ("CFFEX","MO", "中证1000"),
    ("CFFEX","HO", "上证50"),
]

end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=365)

cal, _ = ts_api("trade_cal", exchange="SSE",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"), is_open="1")
trade_days = sorted([c["cal_date"] for c in cal]) if cal else []
sample_days = trade_days[::10]
print(f"交易日: {len(trade_days)}, 采样: {len(sample_days)}")

results = []

for exchange, opt_prefix, cn_name in SYMBOLS:
    print(f"\n{opt_prefix}({cn_name})...", flush=True)
    
    vol_series = []
    oi_series = []
    vol_dates = []
    
    for td in sample_days:
        daily, err = ts_api("opt_daily", exchange=exchange, trade_date=td,
                           fields="ts_code,vol,oi")
        if err or not daily:
            continue
        
        # 汇总该品种所有合约的成交量和持仓量
        total_vol = 0
        total_oi = 0
        count = 0
        for d in daily:
            sym, _ = parse_opt_code(d["ts_code"])
            if sym == opt_prefix:
                v = float(d.get("vol", 0) or 0)
                o = float(d.get("oi", 0) or 0)
                total_vol += v
                total_oi += o
                count += 1
        
        if count > 0 and total_vol > 0:
            vol_series.append(total_vol)
            oi_series.append(total_oi)
            vol_dates.append(td)
    
    if len(vol_series) < 5:
        print(f"  样本不足: {len(vol_series)}")
        continue
    
    current_vol = vol_series[-1]
    current_oi = oi_series[-1]
    vol_pct = (np.array(vol_series) <= current_vol).mean() * 100
    oi_pct = (np.array(oi_series) <= current_oi).mean() * 100
    # 综合流动性分位 = 成交量分位 60% + 持仓量分位 40%
    liq_pct = vol_pct * 0.6 + oi_pct * 0.4
    
    results.append({
        "symbol": opt_prefix,
        "cn_name": cn_name,
        "exchange": exchange,
        "current_vol": int(current_vol),
        "current_oi": int(current_oi),
        "vol_1y_mean": int(np.mean(vol_series)),
        "oi_1y_mean": int(np.mean(oi_series)),
        "vol_percentile": round(vol_pct, 1),
        "oi_percentile": round(oi_pct, 1),
        "liquidity_percentile": round(liq_pct, 1),
        "samples": len(vol_series),
        "vol_history": [{"date": d, "vol": int(v), "oi": int(o)} 
                       for d, v, o in zip(vol_dates, vol_series, oi_series)],
    })
    
    print(f"  ✅ vol_pct={vol_pct:.1f}%, oi_pct={oi_pct:.1f}%, liq={liq_pct:.1f}%")

if results:
    weighted_liq = np.mean([r["liquidity_percentile"] for r in results])
else:
    weighted_liq = 0

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_liquidity_percentile": round(weighted_liq, 1),
    "symbols": results,
}

with open(BASE / "liquidity_percentile.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(results)} 品种, 全市场流动性分位={weighted_liq:.1f}%")
