#!/usr/bin/env python3
"""
mod7_market_breadth_v2.py
全品种期权卖权环境指数（成交额环境 + 卖波环境）

优化：用批量拉取（按交易所），不逐品种请求，避免超时。
"""
import re, json, datetime, requests, time
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent
CACHE_DIR = BASE / "_cache"
CACHE_DIR.mkdir(exist_ok=True)

TS_URL = "https://api.tushare.pro"
TS_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
SUFFIX = {"SHFE": "SHF", "DCE": "DCE", "CZCE": "ZCE", "INE": "INE", "CFFEX": "CFX"}
EXCHANGES = ["SHFE", "DCE", "CZCE", "INE", "CFFEX"]

OPT_TO_FUT = {
    "IO": "IF", "MO": "IM", "HO": "IH",
    "I2": "I", "M2": "M", "A2": "A", "B2": "B", "C2": "C", "Y2": "Y", "P2": "P",
    "L2": "L", "V2": "V", "PP2": "PP", "JM2": "JM", "JD2": "JD", "EG2": "EG",
    "EB2": "EB", "PG2": "PG", "CS2": "CS", "LH2": "LH", "LG2": "LG", "BZ2": "BZ",
    "AG2": "AG", "AU2": "AU", "CU2": "CU", "AL2": "AL", "ZN2": "ZN", "NI2": "NI",
    "SN2": "SN", "RB2": "RB", "RU2": "RU", "BU2": "BU", "SP2": "SP", "FU2": "FU",
    "PB2": "PB", "BR2": "BR", "SC2": "SC",
}

CN_NAMES = {
    "AU": "黄金", "AG": "白银", "CU": "铜", "AL": "铝", "ZN": "锌", "NI": "镍",
    "SN": "锡", "RB": "螺纹", "RU": "橡胶", "BU": "沥青", "SP": "纸浆", "FU": "燃油",
    "PB": "铅", "SC": "原油", "I": "铁矿", "M": "豆粕", "A": "豆一", "B": "豆二",
    "Y": "豆油", "P": "棕榈油", "C": "玉米", "CS": "淀粉", "JM": "焦煤", "JD": "鸡蛋",
    "L": "塑料", "V": "PVC", "PP": "聚丙烯", "EG": "乙二醇", "EB": "苯乙烯",
    "PG": "LPG", "LH": "生猪", "CF": "棉花", "SR": "白糖", "TA": "PTA", "MA": "甲醇",
    "FG": "玻璃", "SA": "纯碱", "RM": "菜粕", "OI": "菜油", "SM": "锰硅", "SF": "硅铁",
    "IF": "沪深300", "IM": "中证1000", "IH": "上证50", "AD": "氧化铝",
    "BR": "丁二烯", "BC": "国际铜", "NR": "20号胶", "SS": "不锈钢",
    "AP": "苹果", "CJ": "红枣", "PK": "花生", "UR": "尿素", "SH": "烧碱",
}

def ts_api(api_name, **kwargs):
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json={"api_name": api_name, "token": TS_TOKEN,
                                            "params": kwargs, "fields": ""}, timeout=30)
            d = r.json()
            if d.get("code") != 0:
                return None, d.get("msg")
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

def pct(series, current):
    if not series: return 50.0
    return float((np.array(series, dtype=float) <= current).mean() * 100)

# ── 冷启动：从 history_breadth.json 预加载历史到品种缓存 ──
HISTORY_FILE = CACHE_DIR / "history_breadth.json"
_history_by_symbol = {}  # symbol -> [{"date":..., "iv_proxy":..., "vol":..., "amount":..., "oi":...}]

def _load_history():
    if _history_by_symbol:
        return
    if not HISTORY_FILE.exists():
        return
    with open(HISTORY_FILE, encoding="utf-8") as f:
        hist = json.load(f)
    for rec in hist.get("records", []):
        dt = rec["date"]
        for s in rec.get("symbols", []):
            sym = s.get("symbol")
            if not sym:
                continue
            _history_by_symbol.setdefault(sym, []).append({
                "date": dt,
                "iv_proxy": s.get("iv_proxy", 0),
                "vol": s.get("vol", 0),
                "amount": s.get("amount", 0),
                "oi": s.get("oi", 0),
            })
    # 排序去重
    for sym in _history_by_symbol:
        _history_by_symbol[sym] = sorted(_history_by_symbol[sym], key=lambda x: x["date"])

def seed_cache(symbol, cache_records):
    """如果缓存记录太少，用 history_breadth 补齐"""
    _load_history()
    hist = _history_by_symbol.get(symbol, [])
    if not hist or len(cache_records) >= 60:
        return cache_records
    existing_dates = {r["date"] for r in cache_records}
    merged = [r for r in hist if r["date"] not in existing_dates] + cache_records
    merged = sorted(merged, key=lambda x: x["date"])[-180:]
    return merged

print("=" * 60)
print("全品种期权卖权环境指数 V2")
print("=" * 60)

today = datetime.date.today().strftime("%Y%m%d")

# ── Step 1: 批量拉全市场期权 + 期货日线 ──
print("\n[1/3] 批量拉取全市场数据...")

# 1a. 期权日线（按交易所批量）
opt_all = {}  # fut_prefix -> {vol, amount, oi, call_prices, call_vols, exchange}
for ex in EXCHANGES:
    daily, err = ts_api("opt_daily", exchange=ex, trade_date=today,
                       fields="ts_code,close,vol,amount,oi")
    if not daily:
        print(f"  {ex} 期权: 无数据 ({err})")
        continue
    print(f"  {ex} 期权: {len(daily)} 合约")
    for d in daily:
        opt_prefix, cp = parse_opt_prefix(d["ts_code"])
        if not opt_prefix: continue
        fp = get_fut_prefix(opt_prefix)
        if fp not in opt_all:
            opt_all[fp] = {"exchange": ex, "vol": 0, "amount": 0, "oi": 0,
                          "call_prices": [], "call_vols": []}
        row = opt_all[fp]
        row["vol"] += float(d.get("vol", 0) or 0)
        row["amount"] += float(d.get("amount", 0) or 0)
        row["oi"] += float(d.get("oi", 0) or 0)
        if cp == "C":
            p = float(d.get("close", 0) or 0)
            if p > 0:
                row["call_prices"].append(p)
                row["call_vols"].append(float(d.get("vol", 0) or 0))
    time.sleep(0.3)

# 1b. 期货日线（按交易所批量）——用主力合约价格
fut_prices = {}  # fut_prefix -> close
for ex in EXCHANGES:
    daily, err = ts_api("fut_daily", trade_date=today, exchange=ex,
                       fields="ts_code,close,vol")
    if not daily:
        print(f"  {ex} 期货: 无数据 ({err})")
        continue
    print(f"  {ex} 期货: {len(daily)} 合约")
    # 取每个品种成交量最大的合约作为主力
    by_prefix = {}
    for d in daily:
        fp = parse_fut_prefix(d["ts_code"])
        if not fp: continue
        v = float(d.get("vol", 0) or 0)
        c = float(d.get("close", 0) or 0)
        if c > 0 and (fp not in by_prefix or v > by_prefix[fp][1]):
            by_prefix[fp] = (c, v)
    for fp, (c, _) in by_prefix.items():
        fut_prices[fp] = c
    time.sleep(0.3)

print(f"\n  期权品种: {len(opt_all)}, 期货品种: {len(fut_prices)}")

# ── Step 2: 计算各品种指标 ──
print("\n[2/3] 计算各品种卖波+成交热度...")
metrics = []

for fp, info in opt_all.items():
    if fp not in fut_prices: continue
    if info["vol"] < 50 and info["amount"] < 50 and info["oi"] < 100: continue
    if not info["call_prices"]: continue

    F = fut_prices[fp]
    prices = np.array(info["call_prices"])
    vols = np.array(info["call_vols"])
    atm_price = float(np.average(prices, weights=vols)) if vols.sum() > 0 else float(np.median(prices))
    iv_proxy = atm_price / F if F > 0 else 0

    # 读/写缓存（冷启动：从 history_breadth.json 补历史）
    cache_path = CACHE_DIR / f"{fp}_breadth_cache.json"
    cache = json.load(open(cache_path, encoding="utf-8")) if cache_path.exists() else {"records": []}
    records = [r for r in cache.get("records", []) if r.get("date") != today]
    records = seed_cache(fp, records)  # 用历史数据补齐
    records.append({"date": today, "iv_proxy": round(iv_proxy, 6),
                   "vol": round(info["vol"], 2), "amount": round(info["amount"], 2),
                   "oi": round(info["oi"], 2)})
    records = sorted(records, key=lambda x: x["date"])[-180:]
    cache["records"] = records
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    iv_pct = pct([r["iv_proxy"] for r in records], iv_proxy)
    vol_pct = pct([r["vol"] for r in records], info["vol"])
    amt_pct = pct([r["amount"] for r in records], info["amount"])
    oi_pct = pct([r["oi"] for r in records], info["oi"])
    liq_pct = 0.5 * amt_pct + 0.3 * vol_pct + 0.2 * oi_pct
    sell_score = 0.6 * iv_pct + 0.4 * liq_pct

    cn = CN_NAMES.get(fp, fp)
    metrics.append({
        "symbol": fp, "cn_name": cn, "exchange": info["exchange"],
        "fut_price": round(F, 2), "atm_price": round(atm_price, 2),
        "iv_proxy": round(iv_proxy, 4), "iv_percentile": round(iv_pct, 1),
        "total_vol": int(info["vol"]), "total_amount": round(info["amount"], 1),
        "total_oi": int(info["oi"]),
        "vol_percentile": round(vol_pct, 1), "amount_percentile": round(amt_pct, 1),
        "oi_percentile": round(oi_pct, 1), "liquidity_percentile": round(liq_pct, 1),
        "sell_env_score": round(sell_score, 1), "samples": len(records),
    })

print(f"  成功: {len(metrics)} 品种")
if not metrics:
    raise SystemExit("无可用品种")

# ── Step 3: 计算 breadth 指标 ──
print("\n[3/3] 计算 breadth 环境指数...")
total = len(metrics)
high_iv_70 = sum(1 for s in metrics if s["iv_percentile"] >= 70)
high_iv_85 = sum(1 for s in metrics if s["iv_percentile"] >= 85)
high_amt_50 = sum(1 for s in metrics if s["amount_percentile"] >= 50)
high_amt_70 = sum(1 for s in metrics if s["amount_percentile"] >= 70)
high_liq_50 = sum(1 for s in metrics if s["liquidity_percentile"] >= 50)
high_liq_70 = sum(1 for s in metrics if s["liquidity_percentile"] >= 70)
both_high = sum(1 for s in metrics if s["iv_percentile"] >= 70 and s["liquidity_percentile"] >= 50)

pct_iv70 = high_iv_70 / total * 100
pct_iv85 = high_iv_85 / total * 100
pct_amt50 = high_amt_50 / total * 100
pct_amt70 = high_amt_70 / total * 100
pct_liq50 = high_liq_50 / total * 100
pct_liq70 = high_liq_70 / total * 100
pct_both = both_high / total * 100

env_index = pct_iv70 * 0.55 + pct_amt50 * 0.25 + pct_both * 0.20

print(f"  IV>70: {high_iv_70}/{total} ({pct_iv70:.1f}%)")
print(f"  IV>85: {high_iv_85}/{total} ({pct_iv85:.1f}%)")
print(f"  Amount>50: {high_amt_50}/{total} ({pct_amt50:.1f}%)")
print(f"  Liq>50: {high_liq_50}/{total} ({pct_liq50:.1f}%)")
print(f"  双高: {both_high}/{total} ({pct_both:.1f}%)")
print(f"  卖权环境指数: {env_index:.1f}")

history_file = CACHE_DIR / "breadth_env_history.json"
history = json.load(open(history_file, encoding="utf-8")) if history_file.exists() else []
history = [h for h in history if h.get("date") != today]
history.append({"date": today, "env_index": round(env_index, 1),
               "pct_iv70": round(pct_iv70, 1), "pct_amt50": round(pct_amt50, 1),
               "pct_liq50": round(pct_liq50, 1), "pct_both": round(pct_both, 1)})
history = sorted(history, key=lambda x: x["date"])[-365:]
with open(history_file, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

hist_indices = [h["env_index"] for h in history]
env_pct = float((np.array(hist_indices) <= env_index).mean() * 100) if hist_indices else 50.0

if env_index >= 60 and pct_both >= 20:
    regime, label, desc = "STRONG_SELL", "🟢 系统性卖方窗口", "卖波环境高位，成交热度充足，高赔率机会具有普遍性"
elif env_index >= 45 and pct_both >= 10:
    regime, label, desc = "SELECTIVE_SELL", "🟡 精选卖方窗口", "整体环境不差，但仍以精选高赔率合约为主"
elif env_index >= 30:
    regime, label, desc = "NEUTRAL", "⚪ 观察期", "部分维度改善，但系统性卖权窗口尚不够厚"
else:
    regime, label, desc = "AVOID", "🔴 不适合卖权", "卖波环境或成交热度不足，不宜激进做卖方"

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_breadth": {
        "env_index": round(env_index, 1), "env_percentile": round(env_pct, 1),
        "regime": regime, "regime_label": label, "regime_desc": desc, "total_symbols": total,
        "high_iv_70_count": high_iv_70, "high_iv_70_pct": round(pct_iv70, 1),
        "high_iv_85_count": high_iv_85, "high_iv_85_pct": round(pct_iv85, 1),
        "high_amount_50_count": high_amt_50, "high_amount_50_pct": round(pct_amt50, 1),
        "high_amount_70_count": high_amt_70, "high_amount_70_pct": round(pct_amt70, 1),
        "high_liq_50_count": high_liq_50, "high_liq_50_pct": round(pct_liq50, 1),
        "high_liq_70_count": high_liq_70, "high_liq_70_pct": round(pct_liq70, 1),
        "both_high_count": both_high, "both_high_pct": round(pct_both, 1),
    },
    "symbols": sorted(metrics, key=lambda x: x["sell_env_score"], reverse=True),
    "history": history[-60:],
}

with open(BASE / "market_breadth.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成: {label}")
print(f"   卖权环境指数={env_index:.1f}, 历史分位={env_pct:.1f}%")
print(f"   双高品种={both_high}/{total} ({pct_both:.1f}%)")
