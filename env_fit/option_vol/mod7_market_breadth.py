"""
mod7_market_breadth.py
全品种期权卖权环境 breadth 指标

思路：
1. 拉全市场当日期权数据
2. 按品种汇总：成交量、持仓量、ATM期权价格/期货价格比（近似IV水平）
3. 计算 breadth 指标：
   - 高IV品种占比（ATM价格比 > 中位数 * 1.5）
   - 高流动性品种占比（成交量 > 中位数）
   - 综合环境指数
4. 与历史缓存对比，算出当前 breadth 的历史分位
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

# 期权前缀 → 期货前缀映射（不同的才需要映射）
OPT_TO_FUT = {
    "IO2": "IF", "MO2": "IM", "HO2": "IH",
    "I2": "I", "M2": "M", "A2": "A", "B2": "B",
    "C2": "C", "Y2": "Y", "P2": "P", "L2": "L",
    "V2": "V", "PP2": "PP", "JM2": "JM", "JD2": "JD",
    "EG2": "EG", "EB2": "EB", "PG2": "PG", "CS2": "CS",
    "LH2": "LH", "LG2": "LG", "BZ2": "BZ",
    "AG2": "AG", "AU2": "AU", "CU2": "CU", "AL2": "AL",
    "ZN2": "ZN", "NI2": "NI", "SN2": "SN", "RB2": "RB",
    "RU2": "RU", "BU2": "BU", "SP2": "SP", "FU2": "FU",
    "PB2": "PB", "BR2": "BR", "AD2": "AD", "OP2": "OP",
    "SC2": "SC",
}

# CZCE 品种后面带年份数字，需要特殊处理
CZCE_PREFIXES = {
    "CF": "CF", "SR": "SR", "TA": "TA", "MA": "MA", "FG": "FG",
    "SA": "SA", "RM": "RM", "OI": "OI", "SM": "SM", "SF": "SF",
    "SH": "SH", "PX": "PX", "PK": "PK", "UR": "UR", "CJ": "CJ",
    "AP": "AP", "PF": "PF", "PL": "PL", "PR": "PR", "ZC": "ZC",
}

CN_NAMES = {
    "AU": "黄金", "AG": "白银", "CU": "铜", "AL": "铝", "ZN": "锌",
    "NI": "镍", "SN": "锡", "RB": "螺纹", "RU": "橡胶", "BU": "沥青",
    "SP": "纸浆", "FU": "燃油", "PB": "铅", "BR": "丁二烯橡胶", "SC": "原油",
    "I": "铁矿", "M": "豆粕", "A": "豆一", "B": "豆二", "Y": "豆油",
    "P": "棕榈油", "C": "玉米", "CS": "淀粉", "JM": "焦煤", "JD": "鸡蛋",
    "L": "塑料", "V": "PVC", "PP": "聚丙烯", "EG": "乙二醇", "EB": "苯乙烯",
    "PG": "LPG", "LH": "生猪", "CF": "棉花", "SR": "白糖", "TA": "PTA",
    "MA": "甲醇", "FG": "玻璃", "SA": "纯碱", "RM": "菜粕", "OI": "菜油",
    "SM": "锰硅", "SF": "硅铁", "SH": "烧碱", "PX": "对二甲苯", "PK": "花生",
    "UR": "尿素", "CJ": "红枣", "AP": "苹果", "IF": "沪深300", "IM": "中证1000",
    "IH": "上证50",
}

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
            if attempt < 2: time.sleep(1)
            else: return None, str(e)

def parse_opt_prefix(ts_code):
    """从期权 ts_code 提取品种前缀"""
    code = ts_code.split(".")[0]
    # DCE/CFFEX: I2605-C-540
    m = re.match(r'([A-Z]+\d?)(\d{4})-([CP])', code)
    if m: return m.group(1), m.group(3)
    # SHFE/INE: AU2605C1000
    m = re.match(r'([A-Z]+\d?)(\d{4})([CP])', code)
    if m: return m.group(1), m.group(3)
    # CZCE: SR605C4600 / CF605C15000
    m = re.match(r'([A-Z]+)(\d{3})([CP])', code)
    if m: return m.group(1), m.group(3)
    return None, None

def get_fut_prefix(opt_prefix, exchange):
    """期权前缀 → 期货前缀"""
    if opt_prefix in OPT_TO_FUT:
        return OPT_TO_FUT[opt_prefix]
    if exchange == "CZCE" and opt_prefix in CZCE_PREFIXES:
        return CZCE_PREFIXES[opt_prefix]
    return opt_prefix

def get_cn_name(fut_prefix):
    return CN_NAMES.get(fut_prefix, fut_prefix)

print("=" * 60)
print("全品种期权卖权环境 Breadth 指标")
print("=" * 60)

today = datetime.date.today().strftime("%Y%m%d")

# Step 1: 拉全市场期权数据
print("\n[1/3] 拉取全市场期权数据...")
symbols = {}

for ex in ["SHFE", "DCE", "CZCE", "INE", "CFFEX"]:
    sfx = SUFFIX[ex]
    daily, err = ts_api("opt_daily", exchange=ex, trade_date=today,
                       fields="ts_code,close,vol,oi")
    if not daily:
        print(f"  {ex}: 无数据")
        continue
    
    for d in daily:
        opt_prefix, cp = parse_opt_prefix(d["ts_code"])
        if not opt_prefix:
            continue
        
        fut_prefix = get_fut_prefix(opt_prefix, ex)
        key = fut_prefix  # 用期货前缀作为品种 key
        
        if key not in symbols:
            symbols[key] = {
                "opt_prefix": opt_prefix, "exchange": ex, "sfx": sfx,
                "cn_name": get_cn_name(fut_prefix),
                "total_vol": 0, "total_oi": 0, "call_count": 0, "put_count": 0,
                "call_prices": [], "call_vols": [],
            }
        
        vol = float(d.get("vol", 0) or 0)
        oi = float(d.get("oi", 0) or 0)
        symbols[key]["total_vol"] += vol
        symbols[key]["total_oi"] += oi
        
        if cp == 'C':
            symbols[key]["call_count"] += 1
            price = float(d.get("close", 0) or 0)
            if price > 0:
                symbols[key]["call_prices"].append(price)
                symbols[key]["call_vols"].append(vol)
        else:
            symbols[key]["put_count"] += 1

print(f"  全市场品种数: {len(symbols)}")

# 过滤活跃品种
active = {k: v for k, v in symbols.items() if v["total_vol"] > 500}
print(f"  活跃品种数: {len(active)}")

# Step 2: 拉期货价格，计算 ATM 价格比
print("\n[2/3] 计算各品种 ATM 价格比...")
symbol_metrics = []

for fut_prefix, info in active.items():
    ex = info["exchange"]
    sfx = info["sfx"]
    fut_code = f"{fut_prefix}.{sfx}"
    
    fut, _ = ts_api("fut_daily", ts_code=fut_code, trade_date=today, fields="close")
    if not fut or not fut[0].get("close"):
        continue
    
    F = float(fut[0]["close"])
    if not info["call_prices"]:
        continue
    
    prices = np.array(info["call_prices"])
    vols = np.array(info["call_vols"])
    if vols.sum() == 0:
        atm_price = np.median(prices)
    else:
        atm_price = np.average(prices, weights=vols)
    
    price_ratio = atm_price / F
    
    symbol_metrics.append({
        "symbol": fut_prefix,
        "cn_name": info["cn_name"],
        "exchange": ex,
        "fut_price": F,
        "atm_price": round(atm_price, 2),
        "price_ratio": round(price_ratio, 4),
        "total_vol": int(info["total_vol"]),
        "total_oi": int(info["total_oi"]),
    })

print(f"  成功计算: {len(symbol_metrics)} 品种")

# Step 3: 计算 breadth 指标
print("\n[3/3] 计算 breadth 指标...")

price_ratios = [s["price_ratio"] for s in symbol_metrics]
vols_list = [s["total_vol"] for s in symbol_metrics]

pr_median = np.median(price_ratios)
pr_75 = np.percentile(price_ratios, 75)
vol_median = np.median(vols_list)

total = len(symbol_metrics)
high_iv_count = sum(1 for s in symbol_metrics if s["price_ratio"] > pr_75)
high_vol_count = sum(1 for s in symbol_metrics if s["total_vol"] > vol_median)
both_high = sum(1 for s in symbol_metrics 
               if s["price_ratio"] > pr_75 and s["total_vol"] > vol_median)

high_iv_pct = high_iv_count / total * 100
high_liq_pct = high_vol_count / total * 100
both_pct = both_high / total * 100

env_index = high_iv_pct * 0.6 + high_liq_pct * 0.4

print(f"  高IV品种: {high_iv_count}/{total} ({high_iv_pct:.1f}%)")
print(f"  高流动性: {high_vol_count}/{total} ({high_liq_pct:.1f}%)")
print(f"  双高品种: {both_high}/{total} ({both_pct:.1f}%)")
print(f"  环境指数: {env_index:.1f}")

# 历史缓存
history_file = CACHE_DIR / "breadth_history.json"
if history_file.exists():
    with open(history_file, encoding="utf-8") as f:
        history = json.load(f)
else:
    history = []

history.append({
    "date": today,
    "env_index": round(env_index, 1),
    "high_iv_pct": round(high_iv_pct, 1),
    "high_liq_pct": round(high_liq_pct, 1),
    "both_pct": round(both_pct, 1),
    "total_symbols": total,
})

cutoff = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y%m%d")
history = [h for h in history if h["date"] >= cutoff]

with open(history_file, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

if len(history) > 1:
    hist_indices = [h["env_index"] for h in history]
    current_pct = (np.array(hist_indices) <= env_index).mean() * 100
else:
    current_pct = 50.0

print(f"  历史分位: {current_pct:.1f}% (样本={len(history)})")

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_breadth": {
        "env_index": round(env_index, 1),
        "env_percentile": round(current_pct, 1),
        "high_iv_pct": round(high_iv_pct, 1),
        "high_liq_pct": round(high_liq_pct, 1),
        "both_high_pct": round(both_pct, 1),
        "total_symbols": total,
        "high_iv_count": high_iv_count,
        "high_liq_count": high_vol_count,
        "both_high_count": both_high,
    },
    "symbols": sorted(symbol_metrics, key=lambda x: x["price_ratio"], reverse=True),
    "history": history[-30:],
}

with open(BASE / "market_breadth.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完成")
