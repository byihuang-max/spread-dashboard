#!/usr/bin/env python3
"""
backfill_history.py
回补期权历史数据（2年）

目标：
- 拉 2024-04-01 至今的全市场期权日线数据
- 按品种汇总：每天每个品种的 vol/amount/oi/ATM价格
- 存入 _cache/history_breadth.json
"""
import re, json, datetime, requests, time
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent
CACHE_DIR = BASE / "_cache"
CACHE_DIR.mkdir(exist_ok=True)

TS_URL = "https://api.tushare.pro"
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "CFFEX"]
SUFFIX = {"SHFE": "SHF", "DCE": "DCE", "CZCE": "ZCE", "INE": "INE", "CFFEX": "CFX"}

OPT_TO_FUT = {
    "IO": "IF", "MO": "IM", "HO": "IH",
    "I2": "I", "M2": "M", "A2": "A", "B2": "B", "C2": "C", "Y2": "Y", "P2": "P",
    "L2": "L", "V2": "V", "PP2": "PP", "JM2": "JM", "JD2": "JD", "EG2": "EG",
    "EB2": "EB", "PG2": "PG", "CS2": "CS", "LH2": "LH", "LG2": "LG", "BZ2": "BZ",
    "AG2": "AG", "AU2": "AU", "CU2": "CU", "AL2": "AL", "ZN2": "ZN", "NI2": "NI",
    "SN2": "SN", "RB2": "RB", "RU2": "RU", "BU2": "BU", "SP2": "SP", "FU2": "FU",
    "PB2": "PB", "BR2": "BR", "SC2": "SC",
}

def ts_api(api_name, **kwargs):
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json={"api_name": api_name, "token": TS_TOKEN,
                                            "params": kwargs, "fields": ""}, timeout=30)
            d = r.json()
            if d.get("code") != 0: return None, d.get("msg")
            return [dict(zip(d["data"]["fields"], row)) for row in d["data"]["items"]], None
        except Exception as e:
            if attempt < 2: time.sleep(1)
            else: return None, str(e)

def parse_opt_prefix(ts_code):
    code = ts_code.split(".")[0]
    for pat in [r'([A-Z]+\d?)(\d{4})-([CP])', r'([A-Z]+\d?)(\d{4})([CP])', r'([A-Z]+)(\d{3})([CP])']:
        m = re.match(pat, code)
        if m: return m.group(1), m.group(3)
    return None, None

def get_fut_prefix(opt_prefix):
    return OPT_TO_FUT.get(opt_prefix, opt_prefix)

def parse_fut_prefix(ts_code):
    code = ts_code.split(".")[0]
    m = re.match(r'([A-Z]+)', code)
    return m.group(1) if m else None

print("=" * 60)
print("回补期权历史数据（2年）")
print("=" * 60)

# 拉交易日历
start_date = datetime.date(2024, 4, 1)
end_date = datetime.date.today()
cal, _ = ts_api("trade_cal", exchange="SSE",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"), is_open="1")
trade_days = sorted([c["cal_date"] for c in cal]) if cal else []
print(f"交易日: {len(trade_days)} 天 ({start_date} ~ {end_date})")

# 读已有缓存
history_file = CACHE_DIR / "history_breadth.json"
if history_file.exists():
    with open(history_file, encoding="utf-8") as f:
        history = json.load(f)
    existing_dates = {r["date"] for r in history.get("records", [])}
    print(f"已有缓存: {len(existing_dates)} 天")
else:
    history = {"records": []}
    existing_dates = set()

# 需要补的日期
todo = [td for td in trade_days if td not in existing_dates]
print(f"需要补: {len(todo)} 天")

if not todo:
    print("无需补充，退出")
    raise SystemExit(0)

print(f"\n开始回补...")
for i, td in enumerate(todo, 1):
    print(f"[{i}/{len(todo)}] {td}...", end=" ", flush=True)
    
    # 拉期权数据
    opt_all = {}
    for ex in EXCHANGES:
        data, err = ts_api("opt_daily", exchange=ex, trade_date=td,
                          fields="ts_code,close,vol,amount,oi")
        if not data: continue
        for d in data:
            opt_prefix, cp = parse_opt_prefix(d["ts_code"])
            if not opt_prefix: continue
            fp = get_fut_prefix(opt_prefix)
            if fp not in opt_all:
                opt_all[fp] = {"vol": 0, "amount": 0, "oi": 0, "call_prices": [], "call_vols": []}
            row = opt_all[fp]
            row["vol"] += float(d.get("vol", 0) or 0)
            row["amount"] += float(d.get("amount", 0) or 0)
            row["oi"] += float(d.get("oi", 0) or 0)
            if cp == "C":
                p = float(d.get("close", 0) or 0)
                if p > 0:
                    row["call_prices"].append(p)
                    row["call_vols"].append(float(d.get("vol", 0) or 0))
        time.sleep(0.15)
    
    # 拉期货价格
    fut_prices = {}
    for ex in EXCHANGES:
        data, err = ts_api("fut_daily", trade_date=td, exchange=ex, fields="ts_code,close,vol")
        if not data: continue
        by_prefix = {}
        for d in data:
            fp = parse_fut_prefix(d["ts_code"])
            if not fp: continue
            v = float(d.get("vol", 0) or 0)
            c = float(d.get("close", 0) or 0)
            if c > 0 and (fp not in by_prefix or v > by_prefix[fp][1]):
                by_prefix[fp] = (c, v)
        for fp, (c, _) in by_prefix.items():
            fut_prices[fp] = c
        time.sleep(0.15)
    
    # 汇总
    symbols = []
    for fp, info in opt_all.items():
        if fp not in fut_prices: continue
        if info["vol"] < 50 and info["amount"] < 50 and info["oi"] < 100: continue
        if not info["call_prices"]: continue
        F = fut_prices[fp]
        prices = np.array(info["call_prices"])
        vols = np.array(info["call_vols"])
        atm_price = float(np.average(prices, weights=vols)) if vols.sum() > 0 else float(np.median(prices))
        iv_proxy = atm_price / F if F > 0 else 0
        symbols.append({
            "symbol": fp,
            "fut_price": round(F, 2),
            "atm_price": round(atm_price, 2),
            "iv_proxy": round(iv_proxy, 6),
            "vol": round(info["vol"], 2),
            "amount": round(info["amount"], 2),
            "oi": round(info["oi"], 2),
        })
    
    history["records"].append({"date": td, "symbols": symbols})
    print(f"{len(symbols)} 品种")
    
    # 每10天保存一次
    if i % 10 == 0:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"  已保存 {i}/{len(todo)}")

# 最终保存
history["records"] = sorted(history["records"], key=lambda x: x["date"])
with open(history_file, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {len(history['records'])} 天")
