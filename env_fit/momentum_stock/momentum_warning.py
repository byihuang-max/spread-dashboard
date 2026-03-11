#!/usr/bin/env python3
"""情绪预警条件链汇总脚本 — 增量模式"""

import json, csv, os, statistics, datetime
from pathlib import Path

DIR = Path(__file__).resolve().parent
CSV_PATH = DIR / "momentum_warning.csv"
JSON_PATH = DIR / "momentum_warning.json"
SENTIMENT_PATH = DIR / "momentum_sentiment.json"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AMOUNT_PATH = _PROJECT_ROOT / "env_fit/quant_stock/amount_vol.json"
PATIENT_PATH = _PROJECT_ROOT / "micro_flow/patient_capital/patient_capital.json"

LOOKBACK = 120

def load_json(p, label):
    if not p.exists():
        print(f"⚠️  {label} 不存在: {p}")
        return None
    with open(p) as f:
        return json.load(f)

def existing_dates():
    if not CSV_PATH.exists():
        return set()
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        return {r["date"] for r in reader}

# ── Signal layer ──────────────────────────────────────────────
def check_signals(daily, idx):
    """Return (triggered: bool, details: list[str])"""
    details = []
    d = daily[idx]

    # helper: get field list for range
    def vals(field, start, end):
        return [daily[i][field] for i in range(start, end) if 0 <= i < len(daily) and daily[i].get(field) is not None]

    # 高位断板: max_height vs peak of previous 5 days
    if idx >= 5:
        prev_peak = max(vals("max_height", idx-5, idx))
        cur = d.get("max_height", 0)
        if prev_peak - cur >= 2:
            details.append(f"高位断板({prev_peak}→{cur})")

    # 炸板率飙升: 连续2日上升且当日>40%
    if idx >= 2:
        zr = [daily[i].get("zha_rate", 0) for i in (idx-2, idx-1, idx)]
        if zr[2] > 40 and zr[2] > zr[1] > zr[0]:
            details.append(f"炸板率飙升({zr[2]:.1f}%)")

    # 晋级率断崖: 较前5日均值下降>50%
    if idx >= 5:
        prev_avg = statistics.mean(vals("promotion_rate", idx-5, idx))
        cur_pr = d.get("promotion_rate", 0)
        if prev_avg > 0 and (prev_avg - cur_pr) / prev_avg > 0.5:
            details.append(f"晋级率断崖({prev_avg:.1f}→{cur_pr:.1f})")

    # 情绪指数急跌
    cur_s = d.get("sentiment", 50)
    if idx >= 1:
        prev_s = daily[idx-1].get("sentiment", 50)
        if prev_s - cur_s > 15:
            details.append(f"情绪单日急跌({prev_s:.0f}→{cur_s:.0f})")
    if idx >= 3:
        s3 = daily[idx-3].get("sentiment", 50)
        if s3 - cur_s > 25:
            details.append(f"情绪3日跌>{25}({s3:.0f}→{cur_s:.0f})")

    return (len(details) > 0, details)

# ── Confirmation layer ────────────────────────────────────────
def check_confirmation(amount_daily, date_str):
    """Return (confirmation, volume_declining, volume_cv_high)"""
    idx_map = {r["date"]: i for i, r in enumerate(amount_daily)}
    if date_str not in idx_map:
        return False, False, False
    idx = idx_map[date_str]

    # ma5 vs ma20 from raw data (already computed)
    rec = amount_daily[idx]
    ma5 = rec.get("ma5")
    ma20 = rec.get("ma20")
    volume_declining = False
    if ma5 is not None and ma20 is not None and ma20 > 0:
        if (ma20 - ma5) / ma20 > 0.10:
            volume_declining = True

    # CV of last 10 days
    start = max(0, idx - 9)
    amounts = [amount_daily[i]["amount_yi"] for i in range(start, idx + 1) if amount_daily[i].get("amount_yi")]
    volume_cv_high = False
    if len(amounts) >= 5:
        mu = statistics.mean(amounts)
        if mu > 0:
            cv = statistics.stdev(amounts) / mu
            volume_cv_high = cv > 0.15

    return (volume_declining or volume_cv_high), volume_declining, volume_cv_high

# ── Filter layer ──────────────────────────────────────────────
def build_patient_cost_series(patient_data):
    """Extract date→cost_idx from patient_capital.json (沪深300)"""
    if not patient_data:
        return {}
    indices = patient_data.get("indices", {})
    hs300 = indices.get("沪深300", {})
    series = {}
    for r in hs300.get("daily", []):
        c = r.get("cost_idx")
        if c is not None and c != 0:
            series[r["date"]] = c
    return series

def check_support(cost_series, date_str, all_dates_sorted):
    """Return has_support bool"""
    if not cost_series:
        return False
    # Get last 5 data points up to date_str
    relevant = [d for d in all_dates_sorted if d <= date_str and d in cost_series]
    pts = relevant[-5:]
    if len(pts) < 3:
        return False
    vals = [cost_series[d] for d in pts]
    # simple slope via linear regression on indices
    n = len(vals)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(vals)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(vals))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den > 0 else 0
    return slope > 0

# ── Narrative ─────────────────────────────────────────────────
def make_narrative(level, details, vol_dec, cv_high, has_sup):
    if level == "GREEN":
        return "情绪正常，无预警信号"
    parts = []
    if details:
        parts.append("；".join(details))
    if vol_dec:
        parts.append("成交额萎缩")
    if cv_high:
        parts.append("成交额波动大")
    sup_str = "耐心资本有托底" if has_sup else "耐心资本无托底"
    parts.append(sup_str)
    prefix = {"RED": "🔴高危", "YELLOW": "🟡警惕", "WATCH": "🟡观察"}
    return f"{prefix.get(level, '')}：{'，'.join(parts)}"

# ── Main ──────────────────────────────────────────────────────
def main():
    # Load data
    sent_data = load_json(SENTIMENT_PATH, "momentum_sentiment.json")
    amount_data = load_json(AMOUNT_PATH, "amount_vol.json")
    patient_data = load_json(PATIENT_PATH, "patient_capital.json")

    if not sent_data:
        print("❌ 情绪数据缺失，无法运行")
        return

    sent_daily = sent_data.get("daily", [])
    if not sent_daily:
        print("❌ 情绪 daily 为空"); return

    amount_daily = []
    if amount_data:
        amount_daily = amount_data.get("history", [])

    cost_series = build_patient_cost_series(patient_data)
    all_cost_dates = sorted(cost_series.keys()) if cost_series else []

    done = existing_dates()
    # Only compute last LOOKBACK days
    target = sent_daily[-LOOKBACK:] if len(sent_daily) > LOOKBACK else sent_daily

    new_rows = []
    for i_rel, rec in enumerate(target):
        dt = rec["date"]
        if dt in done:
            continue
        # absolute index in sent_daily
        offset = len(sent_daily) - len(target)
        abs_idx = offset + i_rel

        sig, details = check_signals(sent_daily, abs_idx)
        conf, vol_dec, cv_high = check_confirmation(amount_daily, dt) if amount_daily else (False, False, False)
        has_sup = check_support(cost_series, dt, all_cost_dates)

        if sig and conf and not has_sup:
            level = "RED"
        elif sig and conf and has_sup:
            level = "YELLOW"
        elif sig and not conf:
            level = "WATCH"
        else:
            level = "GREEN"

        narrative = make_narrative(level, details, vol_dec, cv_high, has_sup)

        new_rows.append({
            "date": dt,
            "signal_triggered": sig,
            "signal_details": "|".join(details),
            "confirmation": conf,
            "volume_declining": vol_dec,
            "volume_cv_high": cv_high,
            "has_support": has_sup,
            "warning_level": level,
            "narrative": narrative,
        })

    # Append to CSV
    fields = ["date","signal_triggered","signal_details","confirmation","volume_declining","volume_cv_high","has_support","warning_level","narrative"]
    write_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)

    # Build full JSON from CSV
    all_rows = []
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            r["signal_triggered"] = r["signal_triggered"] == "True"
            r["confirmation"] = r["confirmation"] == "True"
            r["volume_declining"] = r["volume_declining"] == "True"
            r["volume_cv_high"] = r["volume_cv_high"] == "True"
            r["has_support"] = r["has_support"] == "True"
            r["signal_details"] = r["signal_details"].split("|") if r["signal_details"] else []
            all_rows.append(r)

    all_rows.sort(key=lambda x: x["date"])
    today = datetime.date.today().strftime("%Y-%m-%d")
    out = {"updated": today, "daily": all_rows, "latest": all_rows[-1] if all_rows else {}}
    with open(JSON_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ 新增 {len(new_rows)} 天，共 {len(all_rows)} 天，最新: {all_rows[-1]['date'] if all_rows else 'N/A'}")

if __name__ == "__main__":
    main()
