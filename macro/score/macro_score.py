#!/usr/bin/env python3
"""
宏观打分 + 策略适配度 — 纯读取现有 JSON，零新增 API 调用
输出 macro_score.json 供前端读取
"""
import json, os, sys, math
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))

def load(rel_path):
    p = os.path.join(ROOT, rel_path)
    if not os.path.exists(p):
        print(f"[WARN] 缺失: {p}")
        return None
    with open(p) as f:
        return json.load(f)

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

# ─── 1. 宏观打分 ───────────────────────────────────────────

def score_liquidity(d):
    """流动性: Shibor走势 + M1-M2剪刀差"""
    if not d: return 50
    score = 50
    # Shibor ON 趋势: 越低越宽松
    shibor = d.get("shibor_on", [])
    if len(shibor) >= 20:
        recent = [x["value"] for x in shibor[-5:]]
        older  = [x["value"] for x in shibor[-20:-15]]
        avg_r = sum(recent)/len(recent)
        avg_o = sum(older)/len(older)
        if avg_r < avg_o:      # Shibor下行 = 宽松
            score += 15
        elif avg_r > avg_o * 1.2:  # 明显上行 = 收紧
            score -= 15
        # 绝对水平
        if avg_r < 1.5:
            score += 10
        elif avg_r > 2.5:
            score -= 10

    # M1-M2 剪刀差
    ms = d.get("money_supply", [])
    if len(ms) >= 2:
        latest = ms[-1]
        scissors = latest.get("scissors", 0)
        if scissors > 0:       # M1>M2 资金活化
            score += 15
        elif scissors < -5:    # 严重低迷
            score -= 15
        else:
            score += scissors * 2  # 线性

    return clamp(score)

def score_fundamentals(d):
    """经济动能: PMI + 美林时钟"""
    if not d: return 50
    score = 50
    mc = d.get("merrill_clock", {})
    phase = mc.get("phase", "")
    pmi = mc.get("pmi", 50)

    # PMI
    if pmi > 51:
        score += 15
    elif pmi > 50:
        score += 5
    elif pmi > 49:
        score -= 5
    else:
        score -= 15

    # PMI趋势
    pmi_list = d.get("pmi", [])
    if len(pmi_list) >= 3:
        vals = [x["pmi"] for x in pmi_list[-3:] if x.get("pmi")]
        if len(vals) >= 3 and vals[-1] > vals[-2] > vals[-3]:
            score += 10  # 连续改善
        elif len(vals) >= 3 and vals[-1] < vals[-2] < vals[-3]:
            score -= 10  # 连续恶化

    # 美林时钟阶段
    phase_map = {"复苏期": 15, "过热期": 5, "滞胀期": -10, "衰退期": -15}
    score += phase_map.get(phase, 0)

    # CPI-PPI剪刀差（企业利润）
    cpi_ppi = d.get("cpi_ppi", [])
    if len(cpi_ppi) >= 1:
        latest = cpi_ppi[-1]
        cpi_v = latest.get("cpi", 0) or 0
        ppi_v = latest.get("ppi", 0) or 0
        if ppi_v < cpi_v:  # PPI<CPI = 下游利润改善
            score += 5
    
    return clamp(score)

def score_rates_fx(d):
    """利率汇率: 中美利差 + 汇率压力"""
    if not d: return 50
    score = 50
    # 中美利差
    spreads = d.get("spread", [])
    if spreads:
        latest_spread = spreads[-1].get("spread", 0)
        if latest_spread > -1:
            score += 15  # 利差收窄
        elif latest_spread > -2:
            score += 0
        elif latest_spread > -3:
            score -= 15
        else:
            score -= 25

    # 汇率
    fx_spread = d.get("fx_spread", 0)
    if abs(fx_spread) > 0.02:   # CNH大幅偏离CNY = 贬值压力
        score -= 10
    
    # 中债走势（越低越宽松利好权益）
    cn10y = d.get("cn10y", [])
    if len(cn10y) >= 20:
        recent = [x["value"] for x in cn10y[-5:] if x.get("value")]
        older  = [x["value"] for x in cn10y[-20:-15] if x.get("value")]
        if recent and older:
            if sum(recent)/len(recent) < sum(older)/len(older):
                score += 10  # 利率下行

    return clamp(score)

def score_option_sentiment(d):
    """期权情绪: IV分位 + PCR"""
    if not d: return 50
    score = 60  # 默认中性偏正
    sigs = d.get("global_signals", [])
    
    for s in sigs:
        s_lower = s.lower() if isinstance(s, str) else str(s).lower()
        if "极低" in s_lower or "iv分位" in s_lower and ("0%" in s_lower or "5%" in s_lower or "10%" in s_lower):
            score += 5   # IV低 = 便宜对冲 = 利好
        if "看空持仓极重" in s_lower:
            score -= 5   # 看空情绪重
        if "oi激增" in s_lower:
            score -= 2   # 大资金博弈

    underlyings = d.get("underlyings", [])
    for u in underlyings:
        iv_hist = u.get("iv_history", [])
        if iv_hist:
            latest = iv_hist[-1] if isinstance(iv_hist[-1], dict) else {}
            pctile = latest.get("percentile", 50)
            if pctile < 20:
                score += 3   # 低波环境
            elif pctile > 80:
                score -= 8   # 高波恐慌

    return clamp(score)

def score_crowding_flow(d):
    """资金流+拥挤度"""
    if not d: return 50
    score = 50
    
    # 三路资金共识
    consensus = d.get("three_flows", {}).get("consensus", "")
    if "三路共振流入" in consensus:
        score += 20
    elif "偏多" in consensus:
        score += 10
    elif "偏空" in consensus:
        score -= 10
    elif "三路共振流出" in consensus:
        score -= 20
    
    # 拥挤度信号
    cs = d.get("crowding_signal", {})
    sigs = cs.get("signals", [])
    for s in sigs:
        if "追高风险" in s:
            score -= 3
        elif "资金确认" in s:
            score += 2
        elif "逆势吸筹" in s:
            score += 1
    
    # 两融
    for s in sigs:
        if "两融余额" in s and "低位" in s:
            score += 5  # 杠杆低位 = 加杠杆空间
        elif "两融余额" in s and "高位" in s:
            score -= 5

    return clamp(score)


def calc_macro_score(config):
    """计算宏观总分"""
    liq = load("macro/liquidity/liquidity.json")
    fun = load("macro/fundamentals/fundamentals.json")
    rat = load("macro/rates/rates.json")
    opt = load("micro_flow/option_sentiment/option_sentiment.json")
    cro = load("micro_flow/crowding/crowding.json")

    w = config["macro_weights"]
    scores = {
        "liquidity":        (score_liquidity(liq),         w["liquidity"]),
        "fundamentals":     (score_fundamentals(fun),      w["fundamentals"]),
        "rates_fx":         (score_rates_fx(rat),          w["rates_fx"]),
        "option_sentiment": (score_option_sentiment(opt),  w["option_sentiment"]),
        "crowding_flow":    (score_crowding_flow(cro),     w["crowding_flow"]),
    }
    
    total = sum(s * wt for s, wt in scores.values())
    
    # 判断阶段
    t = config["thresholds"]["macro"]
    if total >= t["offense"]:
        phase = "进攻"
        emoji = "🟢"
    elif total >= t["balanced"]:
        phase = "均衡"
        emoji = "🟡"
    elif total >= t["cautious"]:
        phase = "谨慎"
        emoji = "🟠"
    else:
        phase = "防守"
        emoji = "🔴"
    
    detail = {k: {"score": round(v[0],1), "weight": v[1]} for k, v in scores.items()}
    
    # 收集原始信号文本
    raw_signals = []
    for src, key in [("macro/liquidity/liquidity.json","signals"),
                     ("macro/rates/rates.json","signals"),
                     ("macro/fundamentals/fundamentals.json","signals"),
                     ("micro_flow/option_sentiment/option_sentiment.json","global_signals")]:
        d = load(src)
        if d:
            sigs = d.get(key, [])
            raw_signals.extend(sigs if isinstance(sigs, list) else [sigs])

    # 美林时钟
    merrill = {}
    if fun:
        merrill = fun.get("merrill_clock", {})

    return {
        "total": round(total, 1),
        "phase": phase,
        "emoji": emoji,
        "detail": detail,
        "merrill_clock": merrill,
        "raw_signals": raw_signals,
    }


# ─── 2. 策略适配度 ─────────────────────────────────────────

def fit_quant_stock(config):
    """量化股票适配度"""
    score = 50
    signals = []
    
    # 成交额活跃度
    qs = load("env_fit/quant_stock/quant_stock_data.json")
    if qs:
        amt = qs.get("total_amount", [])
        if len(amt) >= 20:
            recent = [x["amount_yi"] for x in amt[-5:]]
            ma20   = [x["amount_yi"] for x in amt[-20:]]
            avg_r = sum(recent)/len(recent)
            avg_20 = sum(ma20)/len(ma20)
            ratio = avg_r / avg_20 if avg_20 else 1
            if ratio > 1.2:
                score += 15
                signals.append(f"成交活跃 ({avg_r:.0f}亿, MA20 {avg_20:.0f}亿) 🟢")
            elif ratio > 0.9:
                score += 5
                signals.append(f"成交正常 ({avg_r:.0f}亿) 🟡")
            else:
                score -= 15
                signals.append(f"缩量明显 ({avg_r:.0f}亿, MA20的{ratio:.0%}) 🔴")
        
        # 小盘因子
        factor = qs.get("factor", [])
        if len(factor) >= 5:
            small_cap = [x.get("小盘", 0) for x in factor[-5:]]
            chg = small_cap[-1] - small_cap[0] if small_cap else 0
            if chg > 0:
                score += 10
                signals.append(f"小盘因子近5日 +{chg:.1f}% 🟢")
            else:
                score -= 5
                signals.append(f"小盘因子近5日 {chg:.1f}% 🔴")

        # 基差成本
        basis = qs.get("basis", [])
        if basis:
            latest_b = basis[-1]
            im = latest_b.get("IM", 0) or 0
            if im > -5:
                score += 10
                signals.append(f"IM基差 {im:.1f}%，对冲成本低 🟢")
            elif im > -15:
                score += 0
                signals.append(f"IM基差 {im:.1f}%，对冲成本适中 🟡")
            else:
                score -= 10
                signals.append(f"IM基差 {im:.1f}%，对冲成本高 🔴")

    # 拥挤度
    cro = load("micro_flow/crowding/crowding.json")
    if cro:
        heatmap = cro.get("industry_heatmap", [])
        hot_count = sum(1 for x in heatmap if x.get("crowd_label") == "🔥拥挤")
        if hot_count > 8:
            score -= 10
            signals.append(f"{hot_count}个行业拥挤，回撤风险 🔴")
        elif hot_count > 4:
            score -= 5
            signals.append(f"{hot_count}个行业拥挤 🟡")
        else:
            score += 5
            signals.append(f"仅{hot_count}个行业拥挤 🟢")

    # 期权IV
    opt = load("micro_flow/option_sentiment/option_sentiment.json")
    if opt:
        for u in opt.get("underlyings", []):
            if "1000" in u.get("name", "") or "1000" in u.get("code", ""):
                iv_hist = u.get("iv_history", [])
                if iv_hist:
                    pct = iv_hist[-1].get("percentile", 50) if isinstance(iv_hist[-1], dict) else 50
                    if pct < 20:
                        score += 5
                        signals.append(f"中证1000 IV分位{pct}%，波动率低 🟢")
                    elif pct > 80:
                        score -= 10
                        signals.append(f"中证1000 IV分位{pct}%，波动率高 🔴")

    return {"score": clamp(score), "signals": signals}


def fit_momentum_stock(config):
    """强势股/动量策略适配度"""
    score = 50
    signals = []
    
    ms = load("env_fit/momentum_stock/momentum_sentiment.json")
    if ms:
        daily = ms.get("daily", [])
        if len(daily) >= 5:
            recent = daily[-5:]
            # 赚钱效应
            avg_up = sum(x.get("up_count", 0) for x in recent) / 5
            avg_down = sum(x.get("down_count", 0) for x in recent) / 5
            if avg_up > avg_down:
                score += 15
                signals.append(f"近5日涨家数均值{avg_up:.0f} > 跌家数{avg_down:.0f} 🟢")
            else:
                score -= 10
                signals.append(f"近5日涨家数均值{avg_up:.0f} < 跌家数{avg_down:.0f} 🔴")
            
            # 连板高度
            avg_height = sum(x.get("max_height", 0) for x in recent) / 5
            if avg_height >= 6:
                score += 10
                signals.append(f"连板高度均值{avg_height:.1f}板，情绪活跃 🟢")
            elif avg_height >= 3:
                score += 0
                signals.append(f"连板高度均值{avg_height:.1f}板 🟡")
            else:
                score -= 10
                signals.append(f"连板高度均值{avg_height:.1f}板，情绪冰点 🔴")
            
            # 涨停数
            avg_zt = sum(x.get("zha_count", 0) for x in recent) / 5
            if avg_zt > 50:
                score += 10
                signals.append(f"日均涨停{avg_zt:.0f}家 🟢")
            elif avg_zt > 20:
                score += 0
                signals.append(f"日均涨停{avg_zt:.0f}家 🟡")
            else:
                score -= 10
                signals.append(f"日均涨停{avg_zt:.0f}家 🔴")

    # 北向资金
    cro = load("micro_flow/crowding/crowding.json")
    if cro:
        direction = cro.get("direction_chart", [])
        if len(direction) >= 5:
            north_5d = sum(x.get("north_net", 0) for x in direction[-5:])
            if north_5d > 50:
                score += 10
                signals.append(f"北向5日净流入{north_5d:.0f}亿 🟢")
            elif north_5d > -50:
                signals.append(f"北向5日净流{north_5d:.0f}亿 🟡")
            else:
                score -= 10
                signals.append(f"北向5日净流出{abs(north_5d):.0f}亿 🔴")

    return {"score": clamp(score), "signals": signals}


def fit_commodity_cta(config):
    """商品CTA适配度"""
    score = 50
    signals = []
    
    cta = load("env_fit/commodity_cta/commodity_cta.json")
    if cta:
        # Mod1: CTA环境
        mod1 = cta.get("mod1_cta_env", {})
        summary = mod1.get("summary", {})
        trend_up = summary.get("trend_up", 0) if isinstance(summary, dict) else 0
        total = summary.get("total", 1) if isinstance(summary, dict) else 1
        if isinstance(summary, str):
            # parse "0/1品种趋势向上" pattern
            import re
            m = re.search(r'(\d+)/(\d+)', summary)
            if m:
                trend_up, total = int(m.group(1)), int(m.group(2))
        
        ratio = trend_up / max(total, 1)
        if ratio > 0.6:
            score += 20
            signals.append(f"{trend_up}/{total}品种趋势向上，CTA友好 🟢")
        elif ratio > 0.3:
            score += 5
            signals.append(f"{trend_up}/{total}品种趋势向上 🟡")
        else:
            score -= 15
            signals.append(f"{trend_up}/{total}品种趋势向上，趋势弱 🔴")

        # Mod2: 趋势扫描
        mod2 = cta.get("mod2_trend_scan", {})
        syms = mod2.get("symbols", [])
        if syms:
            strong = sum(1 for s in syms if isinstance(s, dict) and s.get("trend") == "up")
            weak = sum(1 for s in syms if isinstance(s, dict) and s.get("trend") == "down")
            signals.append(f"趋势扫描: {strong}个向上, {weak}个向下")

        # Mod3: 宏观比值
        mod3 = cta.get("mod3_macro_ratio", {})
        # 铜金比反映经济预期
        cu_au = mod3.get("cu_au", {})
        if isinstance(cu_au, dict) and cu_au.get("trend"):
            if cu_au["trend"] == "up":
                score += 5
                signals.append("铜金比上行，风险偏好改善 🟢")
            else:
                score -= 5
                signals.append("铜金比下行，避险情绪 🔴")

    # 美林时钟对CTA的影响
    fun = load("macro/fundamentals/fundamentals.json")
    if fun:
        mc = fun.get("merrill_clock", {})
        phase = mc.get("phase", "")
        if phase in ["过热期", "滞胀期"]:
            score += 10
            signals.append(f"美林时钟{phase}，商品通常受益 🟢")
        elif phase == "衰退期":
            score -= 10
            signals.append(f"美林时钟衰退期，商品承压 🔴")

    return {"score": clamp(score), "signals": signals}


def fit_cb_env(config):
    """转债策略适配度 — 直接用cb_env已有的分数"""
    score = 50
    signals = []
    
    cb = load("env_fit/cb_env/cb_env.json")
    if cb:
        cb_score = cb.get("score", 50)
        # 映射到我们的体系
        score = cb_score  # cb_env本身就是0-100
        
        details = cb.get("score_details", [])
        for item in details:
            if isinstance(item, list) and len(item) == 2:
                signals.append(f"{item[0]}: {item[1]:.1f}")
        
        # 信用利差（如有）
        mod4 = cb.get("mod4_floor", {})
        latest = mod4.get("latest", {}) if isinstance(mod4, dict) else {}
        if latest:
            signals.append(f"债底保护: {latest}")

    return {"score": clamp(score), "signals": signals}


def fit_arbitrage(config):
    """套利策略适配度"""
    score = 50
    signals = []
    
    # 指数套利: 基差
    qs = load("env_fit/quant_stock/quant_stock_data.json")
    if qs:
        basis = qs.get("basis", [])
        if basis:
            latest = basis[-1]
            # 基差越大套利空间越大
            vals = [abs(latest.get(k, 0) or 0) for k in ["IF", "IC", "IM"]]
            avg_basis = sum(vals) / len(vals) if vals else 0
            if avg_basis > 10:
                score += 15
                signals.append(f"股指基差均值{avg_basis:.1f}%，空间大 🟢")
            elif avg_basis > 5:
                score += 5
                signals.append(f"股指基差均值{avg_basis:.1f}% 🟡")
            else:
                score -= 5
                signals.append(f"股指基差均值{avg_basis:.1f}%，空间小 🔴")

    # 商品套利
    arb_mod1 = load("env_fit/arbitrage/mod1_index_arb.json")
    arb_mod2 = load("env_fit/arbitrage/mod2_commodity_arb.json")
    arb_mod3 = load("env_fit/arbitrage/mod3_option_arb.json")
    
    arb_opps = 0
    for label, d in [("指数", arb_mod1), ("商品", arb_mod2), ("期权", arb_mod3)]:
        if d and isinstance(d, dict):
            # 统计有信号的品种
            opps = d.get("opportunities", [])
            if isinstance(opps, list):
                arb_opps += len(opps)
            # 也检查其他可能的结构
            sigs = d.get("signals", [])
            if isinstance(sigs, list):
                arb_opps += len([s for s in sigs if "偏离" in str(s) or "机会" in str(s)])
    
    if arb_opps > 5:
        score += 15
        signals.append(f"发现{arb_opps}个套利机会 🟢")
    elif arb_opps > 2:
        score += 5
        signals.append(f"发现{arb_opps}个套利机会 🟡")
    else:
        signals.append(f"套利机会较少 🔴")
    
    # 成交量对套利也重要
    if qs:
        amt = qs.get("total_amount", [])
        if amt:
            latest_amt = amt[-1].get("amount_yi", 0)
            if latest_amt > 10000:
                score += 10
                signals.append(f"全A成交{latest_amt:.0f}亿，流动性好 🟢")

    # 期权IV高 = 期权套利机会多
    opt = load("micro_flow/option_sentiment/option_sentiment.json")
    if opt:
        for u in opt.get("underlyings", []):
            iv_hist = u.get("iv_history", [])
            if iv_hist and isinstance(iv_hist[-1], dict):
                pct = iv_hist[-1].get("percentile", 50)
                if pct > 70:
                    score += 5

    return {"score": clamp(score), "signals": signals}


# ─── 3. 配置建议 ────────────────────────────────────────────

def calc_allocation(macro_result, strategy_results, config):
    """基于宏观分数和策略适配度计算配置建议"""
    default = config["default_allocation"]
    macro_score = macro_result["total"]
    
    # 计算调整
    allocation = {}
    total_fit = sum(v["score"] for v in strategy_results.values())
    
    for strat, base_pct in default.items():
        fit = strategy_results.get(strat, {}).get("score", 50)
        
        # 策略适配度调整: 高适配加配，低适配减配
        fit_adj = (fit - 50) / 50 * 10  # ±10% range
        
        # 宏观调整: 宏观差时减风险策略，加防御策略
        macro_adj = 0
        if macro_score < 40:  # 防守
            if strat in ["commodity_cta", "arbitrage"]:
                macro_adj = 5   # 防御型加配
            else:
                macro_adj = -5  # 风险型减配
        elif macro_score > 75:  # 进攻
            if strat in ["quant_stock", "momentum_stock"]:
                macro_adj = 5
        
        adjusted = base_pct + fit_adj + macro_adj
        allocation[strat] = max(5, round(adjusted, 1))  # 最低5%
    
    # 归一化到100%（留一部分现金）
    cash_ratio = 0
    if macro_score < 40:
        cash_ratio = 15
    elif macro_score < 55:
        cash_ratio = 10
    elif macro_score < 75:
        cash_ratio = 5
    
    total = sum(allocation.values())
    target = 100 - cash_ratio
    for k in allocation:
        allocation[k] = round(allocation[k] / total * target, 1)
    
    allocation["cash"] = cash_ratio
    
    # 计算 vs 默认的变化
    changes = {}
    for k, v in allocation.items():
        if k == "cash":
            changes[k] = {"pct": v, "delta": 0, "label": "现金"}
        else:
            delta = v - default.get(k, 0)
            label = {"quant_stock": "量化股票", "momentum_stock": "强势股/动量",
                     "commodity_cta": "商品CTA", "cb_env": "转债", "arbitrage": "套利"}.get(k, k)
            changes[k] = {"pct": v, "delta": round(delta, 1), "label": label}
    
    return changes


# ─── 4. 中观标签 ────────────────────────────────────────────

def calc_meso_tags():
    """生成中观观察标签"""
    tags = []
    
    # 风格轮动 (从 quant_stock 因子数据)
    qs = load("env_fit/quant_stock/quant_stock_data.json")
    if qs:
        factor = qs.get("factor", [])
        if len(factor) >= 5:
            recent = factor[-1]
            best = max(["价值","成长","红利","小盘"], key=lambda k: recent.get(k, 0))
            tags.append(f"{best}风格占优")
    
    # 产业链景气
    chain = load("meso/chain_prosperity/chain_prosperity.json")
    if chain:
        for s in chain.get("signals", []):
            if "🟢" in str(s):
                tags.append(str(s))
    
    # 拥挤度共识
    cro = load("micro_flow/crowding/crowding.json")
    if cro:
        consensus = cro.get("three_flows", {}).get("consensus", "")
        if consensus:
            tags.append(f"资金面: {consensus}")
        
        # 热门行业
        heatmap = cro.get("industry_heatmap", [])
        hot = [x["name"] for x in heatmap if x.get("crowd_label") == "🔥拥挤"][:3]
        cold = [x["name"] for x in heatmap if x.get("crowd_label") == "❄️冷清"][:3]
        if hot:
            tags.append(f"拥挤行业: {', '.join(hot)}")
        if cold:
            tags.append(f"冷清行业: {', '.join(cold)}")

    return tags


# ─── Main ───────────────────────────────────────────────────

def main():
    config = load("macro/score/score_config.json")
    if not config:
        print("ERROR: score_config.json not found")
        sys.exit(1)
    
    print("=" * 50)
    print("GAMT 宏观打分 & 策略适配度")
    print("=" * 50)
    
    # 1. 宏观打分
    macro = calc_macro_score(config)
    print(f"\n📊 宏观总分: {macro['total']}/100 {macro['emoji']} {macro['phase']}")
    print(f"   美林时钟: {macro['merrill_clock'].get('emoji','')} {macro['merrill_clock'].get('phase','')} (PMI={macro['merrill_clock'].get('pmi','')}, CPI={macro['merrill_clock'].get('cpi','')}%)")
    for k, v in macro["detail"].items():
        print(f"   {k}: {v['score']}/100 (权重{v['weight']*100:.0f}%)")
    
    # 2. 策略适配度
    strategies = {
        "quant_stock":    fit_quant_stock(config),
        "momentum_stock": fit_momentum_stock(config),
        "commodity_cta":  fit_commodity_cta(config),
        "cb_env":         fit_cb_env(config),
        "arbitrage":      fit_arbitrage(config),
    }
    
    strat_names = {"quant_stock":"量化股票","momentum_stock":"强势股/动量",
                   "commodity_cta":"商品CTA","cb_env":"转债","arbitrage":"套利"}
    
    print(f"\n🎯 策略适配度:")
    t = config["thresholds"]["strategy"]
    for k, v in strategies.items():
        sc = v["score"]
        if sc >= t["green"]:
            light = "🟢"
        elif sc >= t["yellow"]:
            light = "🟡"
        else:
            light = "🔴"
        print(f"   {light} {strat_names[k]}: {sc}/100")
        for s in v["signals"]:
            print(f"      {s}")
    
    # 3. 中观标签
    meso_tags = calc_meso_tags()
    print(f"\n🔍 中观观察:")
    for tag in meso_tags:
        print(f"   • {tag}")
    
    # 4. 配置建议
    alloc = calc_allocation(macro, strategies, config)
    print(f"\n💼 配置建议:")
    for k, v in alloc.items():
        delta_str = ""
        if v["delta"] > 0:
            delta_str = f" (↑{v['delta']}%)"
        elif v["delta"] < 0:
            delta_str = f" (↓{abs(v['delta'])}%)"
        print(f"   {v['label']}: {v['pct']}%{delta_str}")
    
    # 5. 输出 JSON
    output = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "macro": macro,
        "strategies": {k: {"score": v["score"], "signals": v["signals"],
                           "label": strat_names.get(k, k)} for k, v in strategies.items()},
        "meso_tags": meso_tags,
        "allocation": alloc,
    }
    
    out_path = os.path.join(BASE, "macro_score.json")
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 输出: {out_path}")


if __name__ == "__main__":
    main()
