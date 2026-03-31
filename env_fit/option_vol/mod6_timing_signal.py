"""
mod6_timing_signal.py
综合波动率分位和流动性分位，输出卖权策略择时信号
输出：timing_signal.json
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).parent

# 读取两个分位数据
with open(BASE / "iv_percentile.json", encoding="utf-8") as f:
    iv_data = json.load(f)

with open(BASE / "liquidity_percentile.json", encoding="utf-8") as f:
    liq_data = json.load(f)

market_iv_pct = iv_data.get("market_iv_percentile", 0)
market_liq_pct = liq_data.get("market_liquidity_percentile", 0)

# 综合信号 = IV分位 70% + 流动性分位 30%
# 逻辑：波动率高位更重要（保险费贵），流动性够用就行
composite_score = market_iv_pct * 0.7 + market_liq_pct * 0.3

# 判断信号
if composite_score >= 75 and market_iv_pct >= 75:
    signal = "STRONG_SELL"
    label = "🟢 强卖方窗口"
    desc = "波动率极高位+流动性充足，保险费很贵，强烈适合卖权"
elif composite_score >= 60 and market_iv_pct >= 60:
    signal = "SELECTIVE_SELL"
    label = "🟡 精选窗口"
    desc = "波动率高位，需精选流动性好的品种"
elif composite_score >= 40:
    signal = "WATCH"
    label = "⚪ 观察期"
    desc = "波动率不在极值，等待更好时机"
else:
    signal = "NO_OPPORTUNITY"
    label = "🔴 不适合"
    desc = "波动率低位或流动性不足，不适合卖权"

# 品种级信号：同时满足 IV分位>70 且 流动性分位>50
iv_symbols = {s["symbol"]: s for s in iv_data.get("symbols", [])}
liq_symbols = {s["symbol"]: s for s in liq_data.get("symbols", [])}

opportunities = []
for sym in iv_symbols:
    if sym not in liq_symbols:
        continue
    iv_pct = iv_symbols[sym]["iv_percentile"]
    liq_pct = liq_symbols[sym]["liquidity_percentile"]
    score = iv_pct * 0.7 + liq_pct * 0.3
    
    if iv_pct >= 70 and liq_pct >= 50:
        opportunities.append({
            "symbol": sym,
            "cn_name": iv_symbols[sym]["cn_name"],
            "iv_percentile": iv_pct,
            "liquidity_percentile": liq_pct,
            "composite_score": round(score, 1),
        })

opportunities.sort(key=lambda x: x["composite_score"], reverse=True)

output = {
    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "market_signal": {
        "signal": signal,
        "label": label,
        "description": desc,
        "composite_score": round(composite_score, 1),
        "iv_percentile": market_iv_pct,
        "liquidity_percentile": market_liq_pct,
    },
    "opportunities": opportunities,
    "opportunity_count": len(opportunities),
}

with open(BASE / "timing_signal.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ 市场信号: {label}")
print(f"   综合分: {composite_score:.1f} (IV={market_iv_pct}% × 0.7 + Liq={market_liq_pct}% × 0.3)")
print(f"   机会品种: {len(opportunities)} 个")
if opportunities:
    print(f"   Top 3: {', '.join([o['symbol']+'('+o['cn_name']+')' for o in opportunities[:3]])}")
