#!/usr/bin/env python3
"""
模块二：品种趋势扫描
- 扫描活跃期货品种（日均成交额>500万）
- 输出每个品种的趋势评分和信号
- 输出 JSON: commodity_cta/mod2_trend_scan.json
"""

import json, os, time, re, math
from datetime import datetime, timedelta
import requests

# ── 配置 ──
TUSHARE_URL = "http://lianghua.nanyangqiankun.top"
TUSHARE_TOKEN = "33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 交易所后缀映射
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

CONT_RE = re.compile(r"^([A-Z]+)\.([A-Z]+)$")


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
        print("[FATAL] 无法获取交易日历")
        return []
    dates = sorted([r["cal_date"] for r in rows], reverse=True)
    with open(cache_file, "w") as f:
        json.dump(dates, f)
    return dates[:n]


def get_fut_daily(trade_date):
    cache_file = os.path.join(CACHE_DIR, f"fut_daily_{trade_date}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    rows = tushare_api(
        "fut_daily",
        {"trade_date": trade_date},
        "ts_code,trade_date,close,pre_close,change,pct_chg,vol,amount,oi"
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
                r["sector"] = SYMBOL_SECTOR.get(sym, "其他")
                cont_rows.append(r)
    with open(cache_file, "w") as f:
        json.dump(cont_rows, f, ensure_ascii=False)
    print(f"  缓存 {trade_date}: {len(cont_rows)} 条连续合约")
    return cont_rows


def compute_trend_scan(dates_7):
    """用最近7个交易日数据计算每品种趋势评分"""
    # 拉数据
    daily_data = {}
    for d in dates_7:
        rows = get_fut_daily(d)
        daily_data[d] = {r["symbol"]: r for r in rows}
        time.sleep(0.3)

    dates_asc = sorted(daily_data.keys())
    if len(dates_asc) < 2:
        print("[WARN] 数据不足2天")
        return None

    latest_date = dates_asc[-1]

    # 收集所有出现过的品种
    symbols_seen = set()
    for d in dates_asc:
        symbols_seen.update(daily_data[d].keys())

    # 构建每品种时间序列
    sym_series = {}  # symbol -> list of rows (按日期升序)
    for sym in symbols_seen:
        series = []
        for d in dates_asc:
            row = daily_data[d].get(sym)
            if row and row.get("close"):
                series.append(row)
        sym_series[sym] = series

    # ── 每品种计算 ──
    results = []
    for sym in symbols_seen:
        series = sym_series.get(sym, [])
        if len(series) < 3:
            continue

        close_vals = [float(r["close"]) for r in series]
        pct_vals = [float(r.get("pct_chg", 0) or 0) for r in series]
        amt_vals = [float(r.get("amount", 0) or 0) for r in series]

        latest_close = close_vals[-1]
        sector = SYMBOL_SECTOR.get(sym, "其他")

        # chg_20d：用可用天数的涨跌幅%
        n_avail = min(len(close_vals), 20)
        chg_20d = (close_vals[-1] / close_vals[-n_avail] - 1) * 100 if close_vals[-n_avail] else 0

        # MA20斜率 → trend_dir
        n_ma = min(len(close_vals), 20)
        ma_now = sum(close_vals[-n_ma:]) / n_ma
        if len(close_vals) > n_ma:
            ma_prev = sum(close_vals[-n_ma-1:-1]) / n_ma
        elif len(close_vals) >= 2:
            # 用前N-1天的均值近似
            ma_prev = sum(close_vals[-n_ma:-1]) / (n_ma - 1) if n_ma > 1 else ma_now
        else:
            ma_prev = ma_now
        ma_slope = (ma_now - ma_prev) / ma_prev * 100 if ma_prev else 0

        if ma_slope > 0.5:
            trend_dir = "多头"
        elif ma_slope < -0.5:
            trend_dir = "空头"
        else:
            trend_dir = "震荡"

        # vol_20d：20日年化波动率
        recent_pcts = pct_vals[-20:]
        if len(recent_pcts) >= 3:
            mean_r = sum(recent_pcts) / len(recent_pcts)
            var = sum((r - mean_r) ** 2 for r in recent_pcts) / len(recent_pcts)
            vol_20d = math.sqrt(var) * math.sqrt(252) / 100  # pct_chg是百分比
        else:
            vol_20d = 0

        # vol_pctile_60d：波动率在60日窗口的分位数
        # 用滚动窗口计算历史波动率序列，然后看当前值的分位
        vol_history = []
        for i in range(3, len(pct_vals) + 1):
            window = pct_vals[max(0, i-20):i]
            if len(window) >= 3:
                m = sum(window) / len(window)
                v = sum((x - m) ** 2 for x in window) / len(window)
                vol_history.append(math.sqrt(v) * math.sqrt(252) / 100)
        if vol_history:
            # 60日窗口
            hist_window = vol_history[-60:]
            below = sum(1 for v in hist_window if v <= vol_20d)
            vol_pctile_60d = below / len(hist_window)
        else:
            vol_pctile_60d = 0.5

        # vol_trend：当前vol_20d > 5日前的vol_20d
        if len(vol_history) >= 6:
            vol_5d_ago = vol_history[-6]
            vol_trend = vol_20d > vol_5d_ago
        elif len(vol_history) >= 2:
            vol_trend = vol_20d > vol_history[0]
        else:
            vol_trend = False

        # volume_ratio：成交额MA20/MA60
        n_ma20 = min(len(amt_vals), 20)
        n_ma60 = min(len(amt_vals), 60)
        ma20_amt = sum(amt_vals[-n_ma20:]) / n_ma20 if n_ma20 else 0
        ma60_amt = sum(amt_vals[-n_ma60:]) / n_ma60 if n_ma60 else 0
        volume_ratio = ma20_amt / ma60_amt if ma60_amt > 0 else 1.0

        # volume_signal
        volume_signal = volume_ratio > 1.2

        # 日均成交额（万元）
        avg_daily_amt = ma20_amt

        # 活跃品种筛选：日均成交额>500万
        if avg_daily_amt <= 500:
            continue

        # drivers & signal_count
        drivers = []
        if trend_dir in ("多头", "空头"):
            drivers.append(f"趋势{trend_dir}")
        if vol_trend:
            drivers.append("波动放大")
        if volume_signal:
            drivers.append("放量")
        signal_count = len(drivers)

        results.append({
            "symbol": sym,
            "sector": sector,
            "close": round(latest_close, 2),
            "chg_20d": round(chg_20d, 2),
            "trend_dir": trend_dir,
            "vol_20d": round(vol_20d, 4),
            "vol_pctile_60d": round(vol_pctile_60d, 4),
            "vol_trend": vol_trend,
            "volume_ratio": round(volume_ratio, 4),
            "volume_signal": volume_signal,
            "avg_daily_amt": round(avg_daily_amt, 2),
            "signal_count": signal_count,
            "drivers": drivers,
            # 下面的 trend_score 在标准化后填充
            "_abs_chg_20d": abs(chg_20d),
            "_volume_ratio": volume_ratio,
        })

    if not results:
        return None

    # ── 标准化并计算 trend_score ──
    abs_chgs = [r["_abs_chg_20d"] for r in results]
    vol_ratios = [r["_volume_ratio"] for r in results]

    max_chg = max(abs_chgs) if abs_chgs else 1
    min_chg = min(abs_chgs) if abs_chgs else 0
    max_vr = max(vol_ratios) if vol_ratios else 1
    min_vr = min(vol_ratios) if vol_ratios else 0

    for r in results:
        chg_norm = (r["_abs_chg_20d"] - min_chg) / (max_chg - min_chg) if max_chg > min_chg else 0.5
        vr_norm = (r["_volume_ratio"] - min_vr) / (max_vr - min_vr) if max_vr > min_vr else 0.5
        r["trend_score"] = round(0.40 * chg_norm + 0.30 * r["vol_pctile_60d"] + 0.30 * vr_norm, 4)
        del r["_abs_chg_20d"]
        del r["_volume_ratio"]

    # 按 trend_score 降序
    results.sort(key=lambda x: x["trend_score"], reverse=True)

    return {
        "scan_date": latest_date,
        "n_scanned": len(results),
        "symbols": results,
    }


def main():
    print("=" * 50)
    print("模块二：品种趋势扫描")
    print("=" * 50)

    dates = get_trade_dates(80)
    if not dates:
        print("[FATAL] 无交易日数据")
        return

    dates_7 = dates[:7]
    print(f"拉取 {len(dates_7)} 个交易日数据: {dates_7[-1]} ~ {dates_7[0]}")

    result = compute_trend_scan(dates_7)
    if not result:
        print("[FATAL] 计算失败，无活跃品种")
        return

    out_file = os.path.join(os.path.dirname(__file__), "mod2_trend_scan.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 模块二完成")
    print(f"  扫描日期: {result['scan_date']}")
    print(f"  活跃品种数: {result['n_scanned']}")
    print(f"  Top 10:")
    for i, s in enumerate(result["symbols"][:10]):
        print(f"    {i+1}. {s['symbol']:>4s} ({s['sector']})  score={s['trend_score']:.3f}  "
              f"chg={s['chg_20d']:+.1f}%  {s['trend_dir']}  signals={s['signal_count']} {s['drivers']}")
    print(f"  输出: {out_file}")


if __name__ == "__main__":
    main()
