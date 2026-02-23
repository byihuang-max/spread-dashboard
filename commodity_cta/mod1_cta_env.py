#!/usr/bin/env python3
"""
模块一：CTA整体环境指标
- 拉取近7个交易日 fut_daily 数据（连续合约）
- 计算每品种：20日年化波动率、MA20趋势、成交量MA20/MA60
- 汇总：avg_vol_20d、vol_percentile_60d、trend_pct、volume_ratio、cta_friendly
- 输出 JSON: commodity_cta/mod1_cta_env.json
"""

import json, os, time, re, math
from datetime import datetime, timedelta
import requests

# ── 配置 ──
TUSHARE_URL = "http://lianghua.nanyangqiankun.top"
TUSHARE_TOKEN = "33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 交易所后缀映射（fut_daily 返回的后缀）
EX_SUFFIX = {"SHFE": "SFE", "DCE": "DCE", "CZCE": "ZCE", "INE": "INE", "GFEX": "GFEX"}

# 品种分类
SECTORS = {
    "黑色系": ["RB", "HC", "I", "J", "JM", "SF", "SM", "SS"],
    "有色金属": ["CU", "AL", "ZN", "PB", "NI", "SN", "BC", "AO", "SI"],
    "贵金属": ["AU", "AG"],
    "能源化工": ["SC", "FU", "LU", "BU", "MA", "EG", "EB", "TA", "PP", "L", "V", "PVC", "PF", "SA", "FG", "UR", "PX", "SP", "RU", "NR", "BR", "PG"],
    "农产品": ["A", "B", "M", "Y", "P", "OI", "RM", "CF", "CY", "SR", "C", "CS", "JD", "LH", "AP", "CJ", "PK", "WH", "RI", "RR"],
}
ALL_SYMBOLS = set()
SYMBOL_SECTOR = {}
for sec, syms in SECTORS.items():
    for s in syms:
        ALL_SYMBOLS.add(s)
        SYMBOL_SECTOR[s] = sec

# 连续合约正则：纯字母+交易所，如 RB.SFE, CU.SFE
CONT_RE = re.compile(r"^([A-Z]+)\.([A-Z]+)$")


def tushare_api(api_name, params, fields="", retries=3):
    """调用 Tushare HTTP API"""
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
    """获取最近 n 个交易日列表（用于回溯计算窗口）"""
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
        print("[FATAL] 无法获取交易日历")
        return []
    dates = sorted([r["cal_date"] for r in rows], reverse=True)
    with open(cache_file, "w") as f:
        json.dump(dates, f)
    return dates[:n]


def get_fut_daily(trade_date):
    """获取某日全市场期货日线（带缓存）"""
    cache_file = os.path.join(CACHE_DIR, f"fut_daily_{trade_date}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    rows = tushare_api(
        "fut_daily",
        {"trade_date": trade_date},
        "ts_code,trade_date,close,pre_close,vol,amount,oi"
    )
    if rows is None:
        return []
    # 只保留连续合约，自己算 pct_chg
    cont_rows = []
    for r in rows:
        m = CONT_RE.match(r.get("ts_code", ""))
        if m:
            sym = m.group(1)
            if sym in ALL_SYMBOLS:
                r["symbol"] = sym
                r["sector"] = SYMBOL_SECTOR.get(sym, "其他")
                # 自己算涨跌幅
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


def compute_env(dates):
    """
    用最近交易日数据计算 CTA 整体环境指标。
    dates: 倒序交易日列表（dates[0]是最新）
    需要至少60天数据做分位数，但我们先用7天跑通，分位数用可用数据。
    """
    # 拉数据：按日组织
    daily_data = {}  # date -> {symbol: row}
    for d in dates:
        rows = get_fut_daily(d)
        daily_data[d] = {r["symbol"]: r for r in rows}
        time.sleep(0.3)

    dates_asc = sorted(daily_data.keys())
    if len(dates_asc) < 2:
        print("[WARN] 数据不足2天，无法计算")
        return None

    # 收集每品种时间序列
    symbols_seen = set()
    for d in dates_asc:
        symbols_seen.update(daily_data[d].keys())

    # 每品种每天的收盘价、成交额
    sym_close = {}  # symbol -> [(date, close)]
    sym_amount = {}  # symbol -> [(date, amount)]
    sym_pct = {}  # symbol -> [(date, pct_chg)]
    for sym in symbols_seen:
        closes, amounts, pcts = [], [], []
        for d in dates_asc:
            row = daily_data[d].get(sym)
            if row and row.get("close"):
                c = float(row["close"])
                pc = float(row.get("pre_close", 0) or 0)
                pct = (c - pc) / pc * 100 if pc > 0 else 0
                closes.append((d, c))
                amounts.append((d, float(row.get("amount", 0) or 0)))
                pcts.append((d, pct))
        sym_close[sym] = closes
        sym_amount[sym] = amounts
        sym_pct[sym] = pcts

    latest_date = dates_asc[-1]

    # ── 每品种指标 ──
    per_symbol = {}
    for sym in symbols_seen:
        closes = sym_close.get(sym, [])
        pcts = sym_pct.get(sym, [])
        amounts = sym_amount.get(sym, [])
        if len(pcts) < 3:
            continue

        # 20日年化波动率（用可用天数）
        recent_pcts = [p[1] for p in pcts[-20:]]
        if len(recent_pcts) >= 3:
            mean_r = sum(recent_pcts) / len(recent_pcts)
            var = sum((r - mean_r) ** 2 for r in recent_pcts) / len(recent_pcts)
            vol_20d = math.sqrt(var) * math.sqrt(252) / 100  # pct_chg 是百分比
        else:
            vol_20d = 0

        # MA20 趋势判定
        close_vals = [c[1] for c in closes]
        if len(close_vals) >= 20:
            ma20_now = sum(close_vals[-20:]) / 20
            ma20_prev = sum(close_vals[-21:-1]) / 20 if len(close_vals) >= 21 else ma20_now
            ma20_slope = (ma20_now - ma20_prev) / ma20_prev * 100 if ma20_prev else 0
        elif len(close_vals) >= 5:
            n = len(close_vals)
            ma20_now = sum(close_vals[-n:]) / n
            ma20_prev = sum(close_vals[-n-1:-1]) / (n) if len(close_vals) > n else ma20_now
            ma20_slope = (ma20_now - ma20_prev) / ma20_prev * 100 if ma20_prev else 0
        else:
            ma20_slope = 0

        if ma20_slope > 0.5:
            trend_dir = "多头"
        elif ma20_slope < -0.5:
            trend_dir = "空头"
        else:
            trend_dir = "震荡"

        has_trend = trend_dir in ("多头", "空头")

        # 成交额 MA20/MA60
        amt_vals = [a[1] for a in amounts]
        ma20_amt = sum(amt_vals[-20:]) / min(len(amt_vals), 20) if amt_vals else 0
        ma60_amt = sum(amt_vals[-60:]) / min(len(amt_vals), 60) if amt_vals else 0
        vol_ratio = ma20_amt / ma60_amt if ma60_amt > 0 else 1.0

        # 日均成交额（万元）
        avg_daily_amt = sum(amt_vals[-20:]) / min(len(amt_vals), 20) if amt_vals else 0

        per_symbol[sym] = {
            "symbol": sym,
            "sector": SYMBOL_SECTOR.get(sym, "其他"),
            "close": close_vals[-1] if close_vals else 0,
            "vol_20d": round(vol_20d, 4),
            "ma20_slope": round(ma20_slope, 4),
            "trend_dir": trend_dir,
            "has_trend": has_trend,
            "volume_ratio": round(vol_ratio, 4),
            "avg_daily_amt": round(avg_daily_amt, 2),
        }

    # ── 汇总指标 ──
    # 只看活跃品种（日均成交额 > 500万）
    active = {k: v for k, v in per_symbol.items() if v["avg_daily_amt"] > 500}
    if not active:
        active = per_symbol  # fallback

    n_active = len(active)
    avg_vol_20d = sum(v["vol_20d"] for v in active.values()) / n_active if n_active else 0
    trend_count = sum(1 for v in active.values() if v["has_trend"])
    trend_pct = trend_count / n_active if n_active else 0
    avg_volume_ratio = sum(v["volume_ratio"] for v in active.values()) / n_active if n_active else 1

    # 简化分位数：用当前值做 0-1 标准化（7天数据不够做真正60日分位，先用线性映射）
    # vol_percentile 用 avg_vol_20d 在 [0.10, 0.40] 区间映射到 [0, 1]
    vol_pctile = max(0, min(1, (avg_vol_20d - 0.10) / 0.30))

    # 标准化
    trend_pct_norm = trend_pct  # 已经是 0-1
    vol_pctile_norm = vol_pctile
    vol_ratio_norm = max(0, min(1, (avg_volume_ratio - 0.7) / 0.6))  # [0.7, 1.3] -> [0, 1]

    cta_friendly = 0.40 * trend_pct_norm + 0.30 * vol_pctile_norm + 0.30 * vol_ratio_norm
    cta_friendly_100 = round(cta_friendly * 100, 1)

    summary = {
        "date": latest_date,
        "n_active": n_active,
        "avg_vol_20d": round(avg_vol_20d, 4),
        "vol_percentile_60d": round(vol_pctile, 4),
        "trend_pct": round(trend_pct, 4),
        "trend_count": trend_count,
        "avg_volume_ratio": round(avg_volume_ratio, 4),
        "cta_friendly": cta_friendly_100,
        "cta_friendly_raw": {
            "trend_pct_norm": round(trend_pct_norm, 4),
            "vol_pctile_norm": round(vol_pctile_norm, 4),
            "vol_ratio_norm": round(vol_ratio_norm, 4),
        },
    }

    return {
        "summary": summary,
        "per_symbol": per_symbol,
    }


def main():
    print("=" * 50)
    print("模块一：CTA整体环境指标")
    print("=" * 50)

    # 拉最近80个交易日（用于计算窗口，实际API只拉7天）
    dates = get_trade_dates(80)
    if not dates:
        print("[FATAL] 无交易日数据")
        return

    # 拉最近25个交易日数据（够算20日波动率和MA20）
    dates_25 = dates[:25]
    print(f"拉取 {len(dates_25)} 个交易日数据: {dates_25[-1]} ~ {dates_25[0]}")

    result = compute_env(dates_25)
    if not result:
        print("[FATAL] 计算失败")
        return

    # 输出
    out_file = os.path.join(os.path.dirname(__file__), "mod1_cta_env.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    s = result["summary"]
    print(f"\n✅ 模块一完成")
    print(f"  日期: {s['date']}")
    print(f"  活跃品种: {s['n_active']}")
    print(f"  平均20日波动率: {s['avg_vol_20d']:.2%}")
    print(f"  趋势品种占比: {s['trend_pct']:.1%} ({s['trend_count']}/{s['n_active']})")
    print(f"  成交量比: {s['avg_volume_ratio']:.2f}")
    print(f"  CTA友好度: {s['cta_friendly']}")
    print(f"  输出: {out_file}")


if __name__ == "__main__":
    main()
