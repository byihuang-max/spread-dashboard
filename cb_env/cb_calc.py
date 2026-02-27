#!/usr/bin/env python3
"""
转债指增策略环境 — 计算模块
读取 cb_data.json，计算4个维度指标，输出 cb_env.json + cb_env.csv
"""

import json, os, csv, math
from collections import defaultdict

BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/cb_env'
INPUT_JSON = os.path.join(BASE_DIR, 'cb_data.json')
OUTPUT_JSON = os.path.join(BASE_DIR, 'cb_env.json')
OUTPUT_CSV = os.path.join(BASE_DIR, 'cb_env.csv')

CSV_HEADERS = [
    'trade_date',
    'cb_amount', 'cb_active_count', 'corr_1000', 'corr_2000',
    'avg_price', 'avg_premium', 'price_percentile',
    'delta_median',
    'below_par_ratio', 'median_price',
]

def log(msg):
    print(msg, flush=True)

def load_data():
    with open(INPUT_JSON) as f:
        return json.load(f)

def median(arr):
    if not arr: return None
    s = sorted(arr)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2

def mean(arr):
    if not arr: return None
    return sum(arr) / len(arr)

def percentile_rank(value, history):
    """value 在 history 中的分位数 (0-100)"""
    if not history or len(history) < 2:
        return 50.0
    below = sum(1 for v in history if v < value)
    return below / len(history) * 100

def rolling_corr(xs, ys, window=20):
    """滚动相关系数"""
    if len(xs) < window or len(ys) < window:
        return None
    xs_w = xs[-window:]
    ys_w = ys[-window:]
    n = len(xs_w)
    mx = sum(xs_w) / n
    my = sum(ys_w) / n
    cov = sum((xs_w[i] - mx) * (ys_w[i] - my) for i in range(n)) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs_w) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys_w) / n)
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    return cov / (sx * sy)

def rolling_beta(cb_rets, stk_rets, window=20):
    """滚动回归斜率 (实证DELTA)"""
    if len(cb_rets) < window or len(stk_rets) < window:
        return None
    x = stk_rets[-window:]
    y = cb_rets[-window:]
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    var_x = sum((xi - mx) ** 2 for xi in x)
    if var_x < 1e-10:
        return None
    return cov / var_x


# ═══ 模块一：市场活跃度 & 小盘相关性 ═══

def calc_mod1(data):
    log("\n[Mod1] 市场活跃度 & 小盘相关性...")
    dates = data["meta"]["dates"]
    cb_daily = data["cb_daily"]
    idx_daily = data["idx_daily"]

    # 每天转债总成交额（万元 → 亿元）
    cb_amount_series = []
    cb_active_count_series = []
    for dt in dates:
        recs = cb_daily.get(dt, [])
        total_amt = sum(r.get("amount", 0) for r in recs) / 10000  # 万元→亿元
        cb_amount_series.append(total_amt)
        cb_active_count_series.append(len(recs))

    # 中证1000/2000 涨跌幅
    idx1000 = idx_daily.get("000852.SH", {})
    idx2000 = idx_daily.get("932000.CSI", {})
    
    pct1000 = [idx1000.get(dt, {}).get("pct_chg", 0) for dt in dates]
    pct2000 = [idx2000.get(dt, {}).get("pct_chg", 0) for dt in dates]

    # 转债成交额日涨跌幅（用于算相关性）
    cb_amt_pct = []
    for i in range(len(cb_amount_series)):
        if i == 0 or cb_amount_series[i-1] < 0.01:
            cb_amt_pct.append(0)
        else:
            cb_amt_pct.append((cb_amount_series[i] / cb_amount_series[i-1] - 1) * 100)

    # 滚动相关系数时序
    corr1000_series = []
    corr2000_series = []
    for i in range(len(dates)):
        if i < 19:
            corr1000_series.append(None)
            corr2000_series.append(None)
        else:
            c1 = rolling_corr(cb_amt_pct[:i+1], pct1000[:i+1], 20)
            c2 = rolling_corr(cb_amt_pct[:i+1], pct2000[:i+1], 20)
            corr1000_series.append(round(c1, 4) if c1 is not None else None)
            corr2000_series.append(round(c2, 4) if c2 is not None else None)

    latest = {
        "cb_amount": round(cb_amount_series[-1], 2) if cb_amount_series else 0,
        "cb_active_count": cb_active_count_series[-1] if cb_active_count_series else 0,
        "corr_1000": corr1000_series[-1],
        "corr_2000": corr2000_series[-1],
        "cb_amount_ma5": round(mean(cb_amount_series[-5:]), 2) if len(cb_amount_series) >= 5 else None,
    }
    log(f"  成交额: {latest['cb_amount']}亿 | 活跃转债: {latest['cb_active_count']}只")
    log(f"  相关系数: 1000={latest['corr_1000']} | 2000={latest['corr_2000']}")

    return {
        "latest": latest,
        "series": {
            "dates": dates,
            "cb_amount": [round(v, 2) for v in cb_amount_series],
            "cb_active_count": cb_active_count_series,
            "corr_1000": corr1000_series,
            "corr_2000": corr2000_series,
        }
    }


# ═══ 模块二：估值水位（价格分位 + 转股溢价率）═══

def calc_mod2(data):
    log("\n[Mod2] 估值水位...")
    dates = data["meta"]["dates"]
    cb_daily = data["cb_daily"]
    cb_map = data["cb_map"]
    stk_daily = data["stk_daily"]

    avg_price_series = []
    avg_premium_series = []
    
    for dt in dates:
        recs = cb_daily.get(dt, [])
        if not recs:
            avg_price_series.append(None)
            avg_premium_series.append(None)
            continue
        
        # 按成交量排序，取前50%
        recs_sorted = sorted(recs, key=lambda r: r.get("vol", 0), reverse=True)
        top_half = recs_sorted[:max(1, len(recs_sorted) // 2)]
        
        prices = []
        premiums = []
        for r in top_half:
            ts_code = r["ts_code"]
            close = r.get("close", 0)
            if close <= 0:
                continue
            prices.append(close)
            
            # 计算转股溢价率
            cb_info = cb_map.get(ts_code, {})
            conv_price = cb_info.get("conv_price")
            stk_code = cb_info.get("stk_code")
            if conv_price and conv_price > 0 and stk_code:
                stk_data = stk_daily.get(stk_code, {}).get(dt, {})
                stk_close = stk_data.get("close")
                if stk_close and stk_close > 0:
                    # 转股价值 = 面值/转股价 × 正股价
                    conv_value = (100 / conv_price) * stk_close
                    premium = (close - conv_value) / conv_value * 100
                    premiums.append(premium)
        
        avg_price_series.append(round(mean(prices), 2) if prices else None)
        avg_premium_series.append(round(mean(premiums), 2) if premiums else None)

    # 价格分位数（在历史窗口中的位置）
    price_pct_series = []
    for i in range(len(dates)):
        if avg_price_series[i] is None:
            price_pct_series.append(None)
            continue
        history = [v for v in avg_price_series[:i+1] if v is not None]
        pct = percentile_rank(avg_price_series[i], history)
        price_pct_series.append(round(pct, 1))

    latest = {
        "avg_price": avg_price_series[-1],
        "avg_premium": avg_premium_series[-1],
        "price_percentile": price_pct_series[-1],
    }
    log(f"  均价: {latest['avg_price']} | 溢价率: {latest['avg_premium']}%")
    log(f"  价格分位: {latest['price_percentile']}%")

    return {
        "latest": latest,
        "series": {
            "dates": dates,
            "avg_price": avg_price_series,
            "avg_premium": avg_premium_series,
            "price_percentile": price_pct_series,
        }
    }


# ═══ 模块三：DELTA 股性追踪 ═══

def calc_mod3(data):
    log("\n[Mod3] DELTA 股性追踪...")
    dates = data["meta"]["dates"]
    cb_daily = data["cb_daily"]
    cb_map = data["cb_map"]
    stk_daily = data["stk_daily"]

    # 预建索引：cb_code → {date → pct_chg}，避免 O(n²) 遍历
    log("  建立转债涨跌幅索引...")
    cb_pct_index = defaultdict(dict)  # ts_code → {date → pct_chg}
    for dt in dates:
        for r in cb_daily.get(dt, []):
            cb_pct_index[r["ts_code"]][dt] = r.get("pct_chg", 0)

    delta_median_series = []
    
    for di, dt in enumerate(dates):
        recs = cb_daily.get(dt, [])
        if not recs or di < 20:
            delta_median_series.append(None)
            continue
        
        # 按成交量排序，取前50%
        recs_sorted = sorted(recs, key=lambda r: r.get("vol", 0), reverse=True)
        top_half = recs_sorted[:max(1, len(recs_sorted) // 2)]
        
        deltas = []
        for r in top_half:
            ts_code = r["ts_code"]
            cb_info = cb_map.get(ts_code, {})
            stk_code = cb_info.get("stk_code")
            if not stk_code:
                continue
            
            # 收集过去20天的涨跌幅（用索引，O(1)查找）
            cb_rets = []
            stk_rets = []
            for j in range(max(0, di - 19), di + 1):
                past_dt = dates[j]
                cb_pct = cb_pct_index.get(ts_code, {}).get(past_dt)
                stk_pct = stk_daily.get(stk_code, {}).get(past_dt, {}).get("pct_chg")
                
                if cb_pct is not None and stk_pct is not None:
                    cb_rets.append(cb_pct)
                    stk_rets.append(stk_pct)
            
            if len(cb_rets) >= 10:
                beta = rolling_beta(cb_rets, stk_rets, len(cb_rets))
                if beta is not None and -2 < beta < 3:  # 过滤异常值
                    deltas.append(beta)
        
        delta_median_series.append(round(median(deltas), 4) if deltas else None)
        if (di + 1) % 10 == 0:
            log(f"  [{di+1}/{len(dates)}] deltas computed...")

    latest = {
        "delta_median": delta_median_series[-1],
    }
    log(f"  DELTA中位数: {latest['delta_median']}")

    return {
        "latest": latest,
        "series": {
            "dates": dates,
            "delta_median": delta_median_series,
        }
    }


# ═══ 模块四：债底跟踪 ═══

def calc_mod4(data):
    log("\n[Mod4] 债底跟踪...")
    dates = data["meta"]["dates"]
    cb_daily = data["cb_daily"]
    cb_map = data["cb_map"]

    below_par_ratio_series = []  # 破面值占比
    median_price_series = []     # 全市场转债价格中位数

    for dt in dates:
        recs = cb_daily.get(dt, [])
        if not recs:
            below_par_ratio_series.append(None)
            median_price_series.append(None)
            continue
        
        prices = [r["close"] for r in recs if r.get("close", 0) > 0]
        below_par = sum(1 for p in prices if p < 100)
        
        below_par_ratio_series.append(round(below_par / len(prices) * 100, 1) if prices else None)
        median_price_series.append(round(median(prices), 2) if prices else None)

    latest = {
        "below_par_ratio": below_par_ratio_series[-1],
        "median_price": median_price_series[-1],
    }
    log(f"  破面值占比: {latest['below_par_ratio']}% | 价格中位数: {latest['median_price']}")

    return {
        "latest": latest,
        "series": {
            "dates": dates,
            "below_par_ratio": below_par_ratio_series,
            "median_price": median_price_series,
        }
    }


# ═══ 综合评分 ═══

def calc_score(mod1, mod2, mod3, mod4):
    """
    转债友好度综合评分 (0-100)
    权重：活跃度25% + 估值25% + DELTA25% + 债底25%
    """
    scores = []
    
    # 1. 活跃度：相关系数越高越好 (0~1 → 0~100)
    corr = mod1["latest"].get("corr_2000")
    if corr is not None:
        s1 = max(0, min(100, (corr + 1) / 2 * 100))  # -1~1 → 0~100
        scores.append(("活跃度", s1, 0.25))
    
    # 2. 估值：价格分位越低越好，溢价率越低越好
    price_pct = mod2["latest"].get("price_percentile")
    premium = mod2["latest"].get("avg_premium")
    if price_pct is not None and premium is not None:
        # 价格分位低 → 好 (100 - percentile)
        s2a = 100 - price_pct
        # 溢价率低 → 好 (假设 0~100% 范围，越低越好)
        s2b = max(0, min(100, 100 - premium))
        s2 = s2a * 0.5 + s2b * 0.5
        scores.append(("估值", s2, 0.25))
    
    # 3. DELTA：越高越好 (0~1 → 0~100)
    delta = mod3["latest"].get("delta_median")
    if delta is not None:
        s3 = max(0, min(100, delta * 100))
        scores.append(("DELTA", s3, 0.25))
    
    # 4. 债底：破面值占比越低越好
    below_par = mod4["latest"].get("below_par_ratio")
    if below_par is not None:
        s4 = max(0, min(100, 100 - below_par))
        scores.append(("债底", s4, 0.25))
    
    if not scores:
        return 50.0, []
    
    total_weight = sum(w for _, _, w in scores)
    composite = sum(s * w for _, s, w in scores) / total_weight
    
    details = [(name, round(s, 1)) for name, s, _ in scores]
    return round(composite, 1), details


# ═══ 主流程 ═══

def find_latest_index(mod1):
    """找到最近一个有完整数据的交易日索引（跳过盘中空数据）"""
    amounts = mod1["series"]["cb_amount"]
    counts = mod1["series"]["cb_active_count"]
    for i in range(len(amounts) - 1, -1, -1):
        if counts[i] > 0 and amounts[i] > 0:
            return i
    return len(amounts) - 1  # fallback

def pick_latest(series_dict, idx):
    """从 series 中按 idx 取值，构造 latest dict"""
    result = {}
    for key, arr in series_dict.items():
        if key == 'dates':
            continue
        result[key] = arr[idx] if idx < len(arr) else None
    return result

def main():
    log("=" * 50)
    log("转债指增策略环境 — 计算模块")
    log("=" * 50)

    data = load_data()
    log(f"数据: {data['meta']['n_dates']}天, {data['meta']['n_cb']}只转债")

    mod1 = calc_mod1(data)
    mod2 = calc_mod2(data)
    mod3 = calc_mod3(data)
    mod4 = calc_mod4(data)

    # 检测最后一天是否数据不完整（盘中/未收盘），如果是则用倒数第二天做 latest
    last_idx = len(data["meta"]["dates"]) - 1
    valid_idx = find_latest_index(mod1)
    if valid_idx < last_idx:
        log(f"\n⚠️ 最后一天 {data['meta']['dates'][last_idx]} 数据不完整，总览使用 {data['meta']['dates'][valid_idx]}")
        # 重建各模块的 latest
        mod1["latest"] = pick_latest(mod1["series"], valid_idx)
        mod1["latest"]["cb_amount"] = round(mod1["latest"].get("cb_amount", 0), 2)
        mod1["latest"]["cb_amount_ma5"] = round(mean(mod1["series"]["cb_amount"][max(0,valid_idx-4):valid_idx+1]), 2) if valid_idx >= 4 else None
        mod2["latest"] = pick_latest(mod2["series"], valid_idx)
        mod3["latest"] = pick_latest(mod3["series"], valid_idx)
        mod4["latest"] = pick_latest(mod4["series"], valid_idx)

    effective_date = data["meta"]["dates"][valid_idx]

    score, details = calc_score(mod1, mod2, mod3, mod4)
    log(f"\n综合评分: {score}/100")
    for name, s in details:
        log(f"  {name}: {s}")

    output = {
        "meta": {
            "generated": data["meta"]["generated"],
            "dates": data["meta"]["dates"],
            "n_dates": data["meta"]["n_dates"],
            "n_cb": data["meta"]["n_cb"],
            "last_date": effective_date,
        },
        "score": score,
        "score_details": details,
        "mod1_activity": mod1,
        "mod2_valuation": mod2,
        "mod3_delta": mod3,
        "mod4_floor": mod4,
    }

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    # === CSV 输出 ===
    dates = data["meta"]["dates"]
    csv_rows = []
    for i, dt in enumerate(dates):
        csv_rows.append({
            'trade_date': dt,
            'cb_amount': mod1["series"]["cb_amount"][i],
            'cb_active_count': mod1["series"]["cb_active_count"][i],
            'corr_1000': mod1["series"]["corr_1000"][i] if mod1["series"]["corr_1000"][i] is not None else '',
            'corr_2000': mod1["series"]["corr_2000"][i] if mod1["series"]["corr_2000"][i] is not None else '',
            'avg_price': mod2["series"]["avg_price"][i] if mod2["series"]["avg_price"][i] is not None else '',
            'avg_premium': mod2["series"]["avg_premium"][i] if mod2["series"]["avg_premium"][i] is not None else '',
            'price_percentile': mod2["series"]["price_percentile"][i] if mod2["series"]["price_percentile"][i] is not None else '',
            'delta_median': mod3["series"]["delta_median"][i] if mod3["series"]["delta_median"][i] is not None else '',
            'below_par_ratio': mod4["series"]["below_par_ratio"][i] if mod4["series"]["below_par_ratio"][i] is not None else '',
            'median_price': mod4["series"]["median_price"][i] if mod4["series"]["median_price"][i] is not None else '',
        })

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        w.writeheader()
        w.writerows(csv_rows)

    json_kb = os.path.getsize(OUTPUT_JSON) / 1024
    csv_kb = os.path.getsize(OUTPUT_CSV) / 1024
    log(f"\n✅ 输出:")
    log(f"  cb_env.json: {json_kb:.0f} KB")
    log(f"  cb_env.csv: {csv_kb:.0f} KB ({len(csv_rows)} 行)")


if __name__ == "__main__":
    main()
