#!/usr/bin/env python3
"""
mod10_contract_scanner.py
合约级卖方机会扫描器

目标：从全市场期权合约中，找出"深虚值但保险费依然肥"的异常机会。
输入：mod7 的 market_breadth.json（品种层环境）
输出：contract_opportunities.json（合约级机会清单）

扫描逻辑：
1. 从 market_breadth.json 取 sell_env_score 排名靠前的品种
2. 拉这些品种的全部活跃合约（opt_basic + opt_daily）
3. 对每个合约计算：
   - 虚值程度 = |K - F| / F
   - 距到期天数
   - 权利金（settle 或 close）
   - 时间价值效率 = 权利金 / 距到期天数
   - 虚值安全垫 = 虚值程度（越大越安全）
   - 成交量 / 成交额 / OI
4. 综合评分，筛出高赔率机会
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

# 期权前缀 → 期货前缀
OPT_TO_FUT = {
    "IO": "IF", "MO": "IM", "HO": "IH",
    "I2": "I", "M2": "M", "A2": "A", "B2": "B", "C2": "C", "Y2": "Y", "P2": "P",
    "L2": "L", "V2": "V", "PP2": "PP", "JM2": "JM", "JD2": "JD", "EG2": "EG",
    "EB2": "EB", "PG2": "PG", "CS2": "CS", "LH2": "LH", "LG2": "LG", "BZ2": "BZ",
    "AG2": "AG", "AU2": "AU", "CU2": "CU", "AL2": "AL", "ZN2": "ZN", "NI2": "NI",
    "SN2": "SN", "RB2": "RB", "RU2": "RU", "BU2": "BU", "SP2": "SP", "FU2": "FU",
    "PB2": "PB", "BR2": "BR", "SC2": "SC",
}
FUT_TO_OPT = {}
for ok, fk in OPT_TO_FUT.items():
    FUT_TO_OPT.setdefault(fk, []).append(ok)

CN_NAMES = {
    "AU": "黄金", "AG": "白银", "CU": "铜", "AL": "铝", "ZN": "锌", "NI": "镍",
    "SN": "锡", "RB": "螺纹", "RU": "橡胶", "SC": "原油", "I": "铁矿", "M": "豆粕",
    "Y": "豆油", "P": "棕榈油", "C": "玉米", "L": "塑料", "V": "PVC", "PP": "聚丙烯",
    "EG": "乙二醇", "EB": "苯乙烯", "PG": "LPG", "LH": "生猪", "CF": "棉花",
    "SR": "白糖", "TA": "PTA", "MA": "甲醇", "FG": "玻璃", "SA": "纯碱",
    "IF": "沪深300", "IM": "中证1000", "IH": "上证50",
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
        if m: return m.group(1)
    return None

def get_fut_prefix(opt_prefix):
    return OPT_TO_FUT.get(opt_prefix, opt_prefix)

print("=" * 60)
print("合约级卖方机会扫描器")
print("=" * 60)

today = datetime.date.today()
today_str = today.strftime("%Y%m%d")

# 读 market_breadth.json
breadth_file = BASE / "market_breadth.json"
if not breadth_file.exists():
    raise SystemExit("请先运行 mod7_market_breadth_v2.py")
breadth = json.load(open(breadth_file, encoding="utf-8"))

# 取 sell_env_score 排名前 20 的品种做深度扫描
top_symbols = breadth["symbols"][:20]
print(f"扫描品种: {len(top_symbols)}")
for s in top_symbols[:5]:
    print(f"  {s['symbol']} {s['cn_name']} score={s['sell_env_score']}")

# Step 1: 批量拉合约基础信息（opt_basic）
print("\n[1/3] 拉取合约基础信息...")
all_basics = {}  # ts_code -> {call_put, exercise_price, maturity_date}
for ex in EXCHANGES:
    data, err = ts_api("opt_basic", exchange=ex,
                       fields="ts_code,call_put,exercise_price,maturity_date,delist_date,per_unit")
    if not data:
        print(f"  {ex}: {err}")
        continue
    # 只保留还在交易的
    for d in data:
        if d.get("delist_date", "99999999") >= today_str:
            all_basics[d["ts_code"]] = d
    print(f"  {ex}: {len([d for d in data if d.get('delist_date','99999999') >= today_str])} 活跃合约")
    time.sleep(0.3)

print(f"  总活跃合约: {len(all_basics)}")

# Step 2: 批量拉今日行情
print("\n[2/3] 拉取今日合约行情...")
all_daily = {}  # ts_code -> {close, settle, vol, amount, oi}
for ex in EXCHANGES:
    data, err = ts_api("opt_daily", exchange=ex, trade_date=today_str,
                       fields="ts_code,close,settle,vol,amount,oi")
    if not data:
        print(f"  {ex}: {err}")
        continue
    for d in data:
        all_daily[d["ts_code"]] = d
    print(f"  {ex}: {len(data)} 条行情")
    time.sleep(0.3)

# Step 3: 对每个 top 品种，扫描合约机会
print("\n[3/3] 扫描合约级机会...")
opportunities = []

for sym_info in top_symbols:
    fp = sym_info["symbol"]
    F = sym_info["fut_price"]
    cn = sym_info["cn_name"]
    ex = sym_info["exchange"]

    # 找这个品种对应的期权前缀
    opt_prefixes = FUT_TO_OPT.get(fp, [fp])

    # 从 all_basics 里找匹配的合约
    matched = []
    for ts_code, basic in all_basics.items():
        opt_pf = parse_opt_prefix(ts_code)
        if opt_pf and get_fut_prefix(opt_pf) == fp:
            daily = all_daily.get(ts_code)
            if daily:
                matched.append({**basic, **daily})

    if not matched:
        continue

    for contract in matched:
        K = float(contract.get("exercise_price", 0) or 0)
        cp = contract.get("call_put", "")
        maturity = contract.get("maturity_date", "")
        settle = float(contract.get("settle", 0) or 0)
        close = float(contract.get("close", 0) or 0)
        vol = float(contract.get("vol", 0) or 0)
        amount = float(contract.get("amount", 0) or 0)
        oi = float(contract.get("oi", 0) or 0)
        per_unit = float(contract.get("per_unit", 1) or 1)

        premium = settle if settle > 0 else close
        if premium <= 0 or K <= 0 or F <= 0:
            continue

        # 距到期天数
        try:
            mat_date = datetime.datetime.strptime(maturity, "%Y%m%d").date()
            dte = (mat_date - today).days
        except:
            continue
        if dte < 5 or dte > 120:
            continue

        # 虚值程度
        if cp == "C":
            otm_pct = (K - F) / F  # 正 = 虚值
        else:
            otm_pct = (F - K) / F  # 正 = 虚值

        # 只看虚值合约（OTM >= 3%）
        if otm_pct < 0.03:
            continue

        # 权利金占标的比例
        premium_pct = premium / F

        # 时间价值效率：每天能收多少保险费（占标的比例）
        theta_efficiency = premium_pct / dte * 10000  # bps/day

        # 卖方机会评分
        # 核心逻辑：虚值够远（安全垫大）+ 保险费还很肥（赔率高）+ 有流动性
        safety_score = min(otm_pct / 0.15, 1.0) * 30  # 虚值安全垫，15%封顶
        premium_score = min(theta_efficiency / 5.0, 1.0) * 40  # 时间价值效率
        liquidity_score = min(vol / 500, 1.0) * 15 + min(oi / 1000, 1.0) * 15  # 流动性

        opp_score = safety_score + premium_score + liquidity_score

        # 只保留有一定分数的
        if opp_score < 30:
            continue

        # 一句话理由
        reasons = []
        if otm_pct >= 0.10:
            reasons.append(f"深虚值{otm_pct:.0%}")
        elif otm_pct >= 0.05:
            reasons.append(f"虚值{otm_pct:.0%}")
        if theta_efficiency >= 3:
            reasons.append(f"保险费肥({theta_efficiency:.1f}bps/天)")
        if dte <= 30:
            reasons.append(f"近月({dte}天)")
        elif dte <= 60:
            reasons.append(f"中期({dte}天)")
        if vol >= 500:
            reasons.append("流动性好")

        premium_value = premium * per_unit
        opportunities.append({
            "ts_code": contract["ts_code"],
            "symbol": fp,
            "cn_name": cn,
            "call_put": cp,
            "exercise_price": K,
            "fut_price": F,
            "otm_pct": round(otm_pct * 100, 1),
            "premium": round(premium, 2),
            "premium_value": round(premium_value, 0),
            "dte": dte,
            "maturity": maturity,
            "theta_efficiency": round(theta_efficiency, 2),
            "vol": int(vol),
            "amount": round(amount, 1),
            "oi": int(oi),
            "opp_score": round(opp_score, 1),
            "reason": " | ".join(reasons) if reasons else "一般机会",
        })

# 按机会分排序
opportunities.sort(key=lambda x: x["opp_score"], reverse=True)

print(f"\n扫描完成: {len(opportunities)} 个机会")
print(f"\n=== Top 15 卖方机会 ===")
for i, opp in enumerate(opportunities[:15], 1):
    cp_label = "Call" if opp["call_put"] == "C" else "Put"
    print(f"{i:2}. {opp['cn_name']} {cp_label} K={opp['exercise_price']:.0f} "
          f"虚值={opp['otm_pct']:.1f}% {opp['dte']}天 "
          f"保险费={opp['premium']:.1f}(≈{opp['premium_value']:.0f}元) "
          f"效率={opp['theta_efficiency']:.1f}bps/天 "
          f"vol={opp['vol']} score={opp['opp_score']:.1f}")
    print(f"     {opp['reason']}")

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "scan_count": len(opportunities),
    "top_symbols_scanned": len(top_symbols),
    "opportunities": opportunities[:50],  # 保留 Top 50
}

with open(BASE / "contract_opportunities.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 已保存 contract_opportunities.json")
