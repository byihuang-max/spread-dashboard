#!/usr/bin/env python3
"""
模块三：宏观比价信号
- 铜金比（CU/AU）、油金比（SC/AU）
- 工业品/农产品篮子比
- 各比价的20日变化%、60日分位、趋势方向
- 输出 JSON: commodity_cta/mod3_macro_ratio.json
"""

import json, os, time, re, math
from datetime import datetime, timedelta
import requests

# ── 配置（和模块一共用） ──
TUSHARE_URL = "http://lianghua.nanyangqiankun.top"
TUSHARE_TOKEN = "33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

CONT_RE = re.compile(r"^([A-Z]+)\.([A-Z]+)$")

# 品种全集（用于缓存过滤）
ALL_SYMBOLS = set([
    "RB", "HC", "I", "J", "JM", "SF", "SM", "SS",
    "CU", "AL", "ZN", "PB", "NI", "SN", "BC", "AO", "SI",
    "AU", "AG",
    "SC", "FU", "LU", "BU", "MA", "EG", "EB", "TA", "PP", "L", "V", "PVC", "PF", "SA", "FG", "UR", "PX", "SP", "RU", "NR", "BR", "PG",
    "A", "B", "M", "Y", "P", "OI", "RM", "CF", "CY", "SR", "C", "CS", "JD", "LH", "AP", "CJ", "PK", "WH", "RI", "RR",
])

# 宏观比价配置
INDUSTRIAL_BASKET = ["RB", "CU", "AL", "MA", "TA", "EG"]
AGRI_BASKET = ["M", "P", "SR", "C", "OI", "CF"]

SECTOR_MAP = {}
for s in ["RB", "HC", "I", "J", "JM", "SF", "SM", "SS"]:
    SECTOR_MAP[s] = "黑色系"
for s in ["CU", "AL", "ZN", "PB", "NI", "SN", "BC", "AO", "SI"]:
    SECTOR_MAP[s] = "有色金属"
for s in ["AU", "AG"]:
    SECTOR_MAP[s] = "贵金属"
for s in ["SC", "FU", "LU", "BU", "MA", "EG", "EB", "TA", "PP", "L", "V", "PVC", "PF", "SA", "FG", "UR", "PX", "SP", "RU", "NR", "BR", "PG"]:
    SECTOR_MAP[s] = "能源化工"
for s in ["A", "B", "M", "Y", "P", "OI", "RM", "CF", "CY", "SR", "C", "CS", "JD", "LH", "AP", "CJ", "PK", "WH", "RI", "RR"]:
    SECTOR_MAP[s] = "农产品"


def tushare_api(api_name, params, fields="", retries=3):
    payload = {
        "api_name": api_name,
        "token": TUSHARE_TOKEN,
        "params": params,
        "fields": fields,
    }
    for attempt in range(retries):
        try:
            r = requests.post(TUSHARE_URL, json=payload, timeout=30)
            data = r.json()
            if data.get("code") != 0:
                print(f"  [WARN] {api_name} code={data.get('code')}: {data.get('msg')}")
                return None
            items = data.get("data", {}).get("items", [])
            cols = data.get("data", {}).get("fields", [])
            return [dict(zip(cols, row)) for row in items]
        except Exception as e:
            print(f"  [ERR] {api_name} attempt {attempt+1}: {e}")
            time.sleep(2)
    return None


def get_trade_dates(n=80):
    cache_file = os.path.join(CACHE_DIR, "trade_cal.json")
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < 86400:
            with open(cache_file) as f:
                dates = json.load(f)
            if len(dates) >= n:
                return dates[:n]

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
    rows = tushare_api("trade_cal", {"exchange": "SSE", "start_date": start, "end_date": end, "is_open": "1"}, "cal_date")
    if not rows:
        return []
    dates = sorted([r["cal_date"] for r in rows], reverse=True)
    with open(cache_file, "w") as f:
        json.dump(dates, f)
    return dates[:n]


def get_fut_daily(trade_date):
    """读取缓存的期货日线（模块一已拉取）"""
    cache_file = os.path.join(CACHE_DIR, f"fut_daily_{trade_date}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    # 如果缓存不存在，自己拉
    rows = tushare_api(
        "fut_daily",
        {"trade_date": trade_date},
        "ts_code,trade_date,close,pre_close,vol,amount,oi"
    )
    if rows is None:
        return []
    cont_rows = []
    for r in rows:
        m = CONT_RE.match(r.get("ts_code", ""))
        if m:
            sym = m.group(1)
            if sym in ALL_SYMBOLS:
                r["symbol"] = sym
                r["sector"] = SECTOR_MAP.get(sym, "其他")
                c = r.get("close")
                pc = r.get("pre_close")
                if c and pc and pc != 0:
                    r["pct_chg"] = (c - pc) / pc * 100
                else:
                    r["pct_chg"] = 0
                cont_rows.append(r)
    with open(cache_file, "w") as f:
        json.dump(cont_rows, f, ensure_ascii=False)
    print(f"  缓存 {trade_date}: {len(cont_rows)} 条连续合约")
    return cont_rows


def build_price_series(dates_asc, symbols):
    """构建品种价格时间序列 {symbol: [(date, close)]}"""
    series = {s: [] for s in symbols}
    for d in dates_asc:
        rows = get_fut_daily(d)
        by_sym = {r["symbol"]: r for r in rows}
        for s in symbols:
            row = by_sym.get(s)
            if row and row.get("close"):
                series[s].append((d, float(row["close"])))
    return series


def calc_ratio_stats(ratio_series):
    """计算比价序列的统计指标"""
    if len(ratio_series) < 2:
        return None

    latest = ratio_series[-1][1]
    dates = [r[0] for r in ratio_series]
    vals = [r[1] for r in ratio_series]

    # 20日变化%
    if len(vals) >= 20:
        chg_20d = (vals[-1] - vals[-20]) / vals[-20] * 100
    else:
        chg_20d = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] != 0 else 0

    # 60日分位数
    window = vals[-60:] if len(vals) >= 60 else vals
    sorted_w = sorted(window)
    rank = sum(1 for v in sorted_w if v <= latest)
    pctile_60d = rank / len(sorted_w) if sorted_w else 0.5

    # 趋势方向（MA5斜率）
    if len(vals) >= 6:
        ma5_now = sum(vals[-5:]) / 5
        ma5_prev = sum(vals[-6:-1]) / 5
        slope = (ma5_now - ma5_prev) / ma5_prev * 100 if ma5_prev else 0
        if slope > 0.3:
            trend = "上升"
        elif slope < -0.3:
            trend = "下降"
        else:
            trend = "横盘"
    else:
        trend = "数据不足"
        slope = 0

    return {
        "latest": round(latest, 6),
        "chg_20d_pct": round(chg_20d, 2),
        "pctile_60d": round(pctile_60d, 4),
        "trend": trend,
        "ma5_slope_pct": round(slope, 4),
        "n_days": len(vals),
        "series": [{"date": d, "value": round(v, 6)} for d, v in ratio_series],
    }


def calc_basket_nav(dates_asc, symbols):
    """
    计算篮子等权归1复利净值序列
    返回 [(date, nav)]
    """
    # 先拿每品种每日涨跌幅
    sym_pct = {s: {} for s in symbols}
    for d in dates_asc:
        rows = get_fut_daily(d)
        by_sym = {r["symbol"]: r for r in rows}
        for s in symbols:
            row = by_sym.get(s)
            if row:
                c = float(row.get("close", 0) or 0)
                pc = float(row.get("pre_close", 0) or 0)
                if c and pc and pc != 0:
                    sym_pct[s][d] = (c - pc) / pc
                else:
                    sym_pct[s][d] = 0

    # 等权平均涨跌幅，归1复利
    nav = 1.0
    nav_series = []
    for d in dates_asc:
        daily_rets = []
        for s in symbols:
            if d in sym_pct[s]:
                daily_rets.append(sym_pct[s][d])
        if daily_rets:
            avg_ret = sum(daily_rets) / len(daily_rets)
            nav *= (1 + avg_ret)
        nav_series.append((d, nav))
    return nav_series


def compute_macro_ratios(dates_asc):
    """计算所有宏观比价"""
    needed = set(["CU", "AU", "SC"] + INDUSTRIAL_BASKET + AGRI_BASKET)
    price = build_price_series(dates_asc, needed)

    results = {}

    # 1. 铜金比 CU/AU
    cu_prices = {d: c for d, c in price.get("CU", [])}
    au_prices = {d: c for d, c in price.get("AU", [])}
    cu_au_ratio = []
    for d in dates_asc:
        if d in cu_prices and d in au_prices and au_prices[d] > 0:
            cu_au_ratio.append((d, cu_prices[d] / au_prices[d]))
    stats = calc_ratio_stats(cu_au_ratio)
    if stats:
        stats["name"] = "铜金比"
        stats["formula"] = "CU连续/AU连续"
        stats["meaning"] = "上升=经济预期改善，下降=避险升温"
        results["cu_au"] = stats

    # 2. 油金比 SC/AU
    sc_prices = {d: c for d, c in price.get("SC", [])}
    sc_au_ratio = []
    for d in dates_asc:
        if d in sc_prices and d in au_prices and au_prices[d] > 0:
            sc_au_ratio.append((d, sc_prices[d] / au_prices[d]))
    stats = calc_ratio_stats(sc_au_ratio)
    if stats:
        stats["name"] = "油金比"
        stats["formula"] = "SC原油连续/AU连续"
        stats["meaning"] = "上升=通胀预期/需求强，下降=衰退预期"
        results["sc_au"] = stats

    # 3. 工业品/农产品篮子比
    ind_nav = calc_basket_nav(dates_asc, INDUSTRIAL_BASKET)
    agri_nav = calc_basket_nav(dates_asc, AGRI_BASKET)
    ind_dict = {d: v for d, v in ind_nav}
    agri_dict = {d: v for d, v in agri_nav}
    ind_agri_ratio = []
    for d in dates_asc:
        if d in ind_dict and d in agri_dict and agri_dict[d] > 0:
            ind_agri_ratio.append((d, ind_dict[d] / agri_dict[d]))
    stats = calc_ratio_stats(ind_agri_ratio)
    if stats:
        stats["name"] = "工业品/农产品"
        stats["formula"] = f"工业篮子({','.join(INDUSTRIAL_BASKET)})/农产品篮子({','.join(AGRI_BASKET)})"
        stats["meaning"] = "上升=工业品相对强势(经济扩张)，下降=农产品相对强势(防御)"
        results["ind_agri"] = stats

    # 附加：篮子净值序列（用于图表）
    results["_basket_nav"] = {
        "industrial": [(d, round(v, 6)) for d, v in ind_nav],
        "agricultural": [(d, round(v, 6)) for d, v in agri_nav],
    }

    return results


def main():
    print("=" * 50)
    print("模块三：宏观比价信号")
    print("=" * 50)

    dates = get_trade_dates(80)
    if not dates:
        print("[FATAL] 无交易日数据")
        return

    # 用25天数据（和模块一一致，共用缓存）
    dates_25 = sorted(dates[:25])
    print(f"使用 {len(dates_25)} 个交易日: {dates_25[0]} ~ {dates_25[-1]}")

    result = compute_macro_ratios(dates_25)

    # 输出
    out_file = os.path.join(os.path.dirname(__file__), "mod3_macro_ratio.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 模块三完成")
    for key in ["cu_au", "sc_au", "ind_agri"]:
        r = result.get(key)
        if r:
            print(f"  {r['name']}: {r['latest']:.4f} | 20日变化: {r['chg_20d_pct']:+.2f}% | 60日分位: {r['pctile_60d']:.0%} | 趋势: {r['trend']}")
    print(f"  输出: {out_file}")


if __name__ == "__main__":
    main()
