#!/usr/bin/env python3
"""
calc_signal.py
基于 2 年历史数据，计算期权卖权环境信号（0~1）

核心逻辑：
1. 读取 history_breadth.json（483 天 × 59 品种）
2. 每天计算全市场横截面指标：
   - IV 中位数
   - 成交额中位数
   - 高 IV 品种占比（IV 分位 > 70%）
   - 高成交额品种占比（成交额分位 > 50%）
3. 对这些指标本身再算历史分位 → 得到 0~1 信号
4. 输出时间序列 + 当前信号值
"""
import json, datetime
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent
CACHE_DIR = BASE / "_cache"

print("=" * 60)
print("计算期权卖权环境信号（基于 2 年历史）")
print("=" * 60)

# 读历史数据
history_file = CACHE_DIR / "history_breadth.json"
if not history_file.exists():
    raise SystemExit("请先运行 backfill_history.py")

with open(history_file, encoding="utf-8") as f:
    history = json.load(f)

records = history.get("records", [])
print(f"历史数据: {len(records)} 天")

if len(records) < 60:
    raise SystemExit("历史数据不足 60 天，无法计算有效信号")

# Step 1: 每天计算横截面指标
daily_metrics = []

for rec in records:
    date = rec["date"]
    symbols = rec.get("symbols", [])
    
    if not symbols:
        continue
    
    # 提取各品种的 IV / 成交额
    ivs = [s["iv_proxy"] for s in symbols if s.get("iv_proxy")]
    amounts = [s["amount"] for s in symbols if s.get("amount")]
    
    if not ivs or not amounts:
        continue
    
    # 横截面中位数
    iv_median = float(np.median(ivs))
    amount_median = float(np.median(amounts))
    
    # 计算每个品种的历史分位（用截至当天的历史）
    # 这里简化：先用全局历史算分位，后续可优化成滚动窗口
    iv_pcts = []
    amt_pcts = []
    
    for s in symbols:
        iv = s.get("iv_proxy")
        amt = s.get("amount")
        if iv is None or amt is None:
            continue
        
        # 用全局历史算分位（简化版）
        all_ivs = []
        all_amts = []
        for r in records:
            if r["date"] <= date:
                for ss in r.get("symbols", []):
                    if ss["symbol"] == s["symbol"]:
                        if ss.get("iv_proxy"):
                            all_ivs.append(ss["iv_proxy"])
                        if ss.get("amount"):
                            all_amts.append(ss["amount"])
        
        if all_ivs:
            iv_pct = (np.array(all_ivs) <= iv).mean() * 100
            iv_pcts.append(iv_pct)
        if all_amts:
            amt_pct = (np.array(all_amts) <= amt).mean() * 100
            amt_pcts.append(amt_pct)
    
    # 高 IV / 高成交额品种占比
    high_iv_ratio = (np.array(iv_pcts) >= 70).mean() * 100 if iv_pcts else 0
    high_amt_ratio = (np.array(amt_pcts) >= 50).mean() * 100 if amt_pcts else 0
    
    daily_metrics.append({
        "date": date,
        "iv_median": round(iv_median, 4),
        "amount_median": round(amount_median, 1),
        "high_iv_ratio": round(high_iv_ratio, 1),
        "high_amt_ratio": round(high_amt_ratio, 1),
        "symbol_count": len(symbols),
    })

print(f"计算完成: {len(daily_metrics)} 天")

# Step 2: 对横截面指标本身算历史分位
iv_medians = [d["iv_median"] for d in daily_metrics]
amt_medians = [d["amount_median"] for d in daily_metrics]
high_iv_ratios = [d["high_iv_ratio"] for d in daily_metrics]
high_amt_ratios = [d["high_amt_ratio"] for d in daily_metrics]

for d in daily_metrics:
    d["iv_median_pct"] = round((np.array(iv_medians) <= d["iv_median"]).mean() * 100, 1)
    d["amount_median_pct"] = round((np.array(amt_medians) <= d["amount_median"]).mean() * 100, 1)
    d["high_iv_ratio_pct"] = round((np.array(high_iv_ratios) <= d["high_iv_ratio"]).mean() * 100, 1)
    d["high_amt_ratio_pct"] = round((np.array(high_amt_ratios) <= d["high_amt_ratio"]).mean() * 100, 1)

# Step 3: 综合信号（0~1）
# 卖权环境信号 = 0.4 * IV中位数分位 + 0.3 * 高IV占比分位 + 0.3 * 高成交额占比分位
for d in daily_metrics:
    signal = (
        0.4 * d["iv_median_pct"] / 100
        + 0.3 * d["high_iv_ratio_pct"] / 100
        + 0.3 * d["high_amt_ratio_pct"] / 100
    )
    d["sell_signal"] = round(signal, 3)

# 保存
output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "total_days": len(daily_metrics),
    "current": daily_metrics[-1] if daily_metrics else None,
    "history": daily_metrics[-120:],  # 保留近 120 天
}

with open(BASE / "sell_signal.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# 输出当前信号
if daily_metrics:
    latest = daily_metrics[-1]
    print(f"\n✅ 当前信号（{latest['date']}）:")
    print(f"   卖权环境信号: {latest['sell_signal']:.3f}")
    print(f"   IV 中位数: {latest['iv_median']:.4f} (分位 {latest['iv_median_pct']:.1f}%)")
    print(f"   高 IV 占比: {latest['high_iv_ratio']:.1f}% (分位 {latest['high_iv_ratio_pct']:.1f}%)")
    print(f"   高成交额占比: {latest['high_amt_ratio']:.1f}% (分位 {latest['high_amt_ratio_pct']:.1f}%)")
    
    if latest['sell_signal'] >= 0.7:
        regime = "🟢 强卖方窗口"
    elif latest['sell_signal'] >= 0.5:
        regime = "🟡 精选卖方窗口"
    elif latest['sell_signal'] >= 0.3:
        regime = "⚪ 观察期"
    else:
        regime = "🔴 不适合卖权"
    
    print(f"   环境判断: {regime}")

print(f"\n已保存: sell_signal.json")
