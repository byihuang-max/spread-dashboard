#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子蒸馏器（Factor Forge 核心）
================================
研报正文 → 可观测因子候选 → 看板辅助建议

两个 LLM 角色，刻意分开：
  · 蒸馏器(distiller)：忠于原文，把"观点"翻译成"可观测信号"
  · 看板顾问(advisor)：结合 GAMT 看板上下文，判断这因子对系统有什么用

核心理念：研报里的"观点"不等于"因子"。
"我们看好半导体复苏"是观点，不可观测；
真因子是"观察 capex同比/库存天数/DRAM现货价，三者拐头向上则成立"。

复用 smart-notes/intelligence/llm_client.call_claude（自带 GPT fallback）。
"""
from __future__ import annotations
import os, sys, json, re, argparse, datetime as dt, hashlib
from pathlib import Path

INTEL_DIR = Path("/Users/apple/Desktop/gamt-dashboard/smart-notes/intelligence")
sys.path.insert(0, str(INTEL_DIR))
from llm_client import call_claude  # noqa: E402

# ── GAMT 看板模块清单（看板顾问的上下文）──────────────────
GAMT_MODULES = """GAMT 看板现有模块（因子要挂靠到这些上面才有用）：
- 宏观与流动性: 流动性/利率汇率/基本面/美林时钟/PMI-CPI
- 中观景气(chain_prosperity): 产业链景气度/AI算力链轮动
- 策略环境适配度: 量化股票/强势股/商品CTA/转债/期权/套利 六大策略打分
- 资金流与微观结构: 拥挤度/期权情绪/耐心资本
- 景气度股票池: 接龙群推票的多因子打分(质量分=缠论结构+共识+量能-拥挤; 动量分独立)
- 红灯预警: A股+美股风险监控
- 风格轧差: 大小盘风格轮动"""

# ══════════════════════════════════════════
# 角色一：蒸馏器
# ══════════════════════════════════════════
DISTILLER_SYSTEM = """你是 Roni（二级量化投研，FOF 背景）的研报因子蒸馏器。

你的唯一任务：把研报正文里的"投资观点"翻译成"可观测的市场因子"。

铁律——区分观点与因子：
- "我们看好半导体H2复苏" = 观点（不可观测，没用）
- 真因子 = 把观点拆成具体能跟踪的数据信号 + 成立条件 + 证伪条件

每条因子必须能回答："我每天/每周看哪个数,看到什么就说明这观点在兑现/证伪？"
如果一个观点实在无法落到可观测信号上，宁可不输出，也不要硬凑。

分层：
- macro: 宏观层（PMI/利率/流动性/汇率级别的方向判断）
- industry: 行业/产业链层（某行业景气/涨价/库存周期）
- stock: 个股层（某公司基本面拐点/事件驱动）

一篇研报可能蒸馏出 0~4 条因子。质量优先，不要凑数。
不编造原文没有的数据。原文模糊的地方，observable 写"原文未给出具体指标"。"""

DISTILLER_OUTPUT = """严格返回 JSON 数组，每个元素是一条因子，不要任何额外文字：

[
  {
    "layer": "macro|industry|stock",
    "factor_name": "<简洁因子名，8字内，如'面板涨价周期'>",
    "direction": "看多|看空|中性",
    "logic_chain": "<逻辑链：为什么这个信号指向这个方向，2-3句>",
    "observable": "<【最重要】具体看什么数据/指标。如'DRAM现货价(集邦/CFM)+三大原厂capex同比+渠道库存周数'。原文没给就写'原文未给出具体指标，建议跟踪XXX'>",
    "trigger": "<触发条件：满足什么则观点成立。如'现货价连续2周环比转正且库存周数低于8周'>",
    "invalidation": "<证伪条件：满足什么则作废。如'现货价连续2月续跌或capex指引下修'>",
    "horizon": "短|中|长",
    "linked_industry": "<关联行业，如'半导体存储'>",
    "linked_tickers": ["<关联个股代码或名称>", "..."]
  }
]

若整篇研报无法蒸馏出任何可观测因子，返回空数组 []。"""

# ══════════════════════════════════════════
# 角色二：看板顾问
# ══════════════════════════════════════════
ADVISOR_SYSTEM = f"""你是 Roni 的 GAMT 看板军师。

{GAMT_MODULES}

任务：给定一条已蒸馏的因子，判断它对 Roni 的看板系统有什么辅助价值。
你要帮他形成"研报知识 → 看板观测"的正反馈闭环。

具体回答：
1. 这因子最该挂在哪个看板模块下（从上面清单选，可多选）
2. 建议在那个模块加什么新观测项/指标（具体可落地）
3. 跟系统里"可能已有的因子"是印证还是矛盾（你看不到全部已存因子，就基于常识判断这类因子通常和什么共振/打架）
4. 一句话给出"采纳价值"判断（高/中/低 + 理由）

务实，不空话。如果这因子对现有看板没什么用，直接说"暂无明确挂靠点"。"""

ADVISOR_OUTPUT = """严格返回 JSON，不要额外文字：
{
  "dashboard_modules": ["<挂靠模块1>", "..."],
  "suggested_observables": ["<建议加的观测项1>", "..."],
  "synergy_or_conflict": "<跟哪类因子印证或矛盾，1-2句>",
  "adoption_value": "高|中|低",
  "adoption_reason": "<一句话理由>"
}"""


def _parse_json(raw: str, expect_array=False):
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    raw = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing comma
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 抓第一个 [..] 或 {..}
    if expect_array:
        l, r = raw.find("["), raw.rfind("]")
    else:
        l, r = raw.find("{"), raw.rfind("}")
    if l >= 0 and r > l:
        chunk = re.sub(r",\s*([}\]])", r"\1", raw[l:r+1])
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass
    raise RuntimeError(f"LLM 返回无法解析为 JSON:\n{raw[:800]}")


def distill_factors(text: str, source_hint: str = "") -> list:
    """研报正文 → 因子候选列表"""
    prompt = f"研报来源: {source_hint or '未知'}\n\n[研报正文]\n{text[:24000]}\n\n{DISTILLER_OUTPUT}"
    raw = call_claude(prompt, system=DISTILLER_SYSTEM, max_tokens=3000)
    factors = _parse_json(raw, expect_array=True)
    if not isinstance(factors, list):
        factors = [factors]
    return factors


def advise_factor(factor: dict) -> dict:
    """对单条因子 → 看板辅助建议"""
    prompt = f"待评估因子:\n{json.dumps(factor, ensure_ascii=False, indent=2)}\n\n{ADVISOR_OUTPUT}"
    raw = call_claude(prompt, system=ADVISOR_SYSTEM, max_tokens=1200)
    return _parse_json(raw, expect_array=False)


def make_factor_id(factor: dict, source: str) -> str:
    key = f"{source}|{factor.get('factor_name','')}|{factor.get('observable','')[:50]}"
    return "F" + hashlib.md5(key.encode()).hexdigest()[:10]


def forge(text: str, source_hint: str = "", with_advice: bool = True) -> list:
    """完整流程：蒸馏 + (可选)看板顾问。返回带完整字段的因子列表。"""
    factors = distill_factors(text, source_hint)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = []
    for f in factors:
        f["factor_id"] = make_factor_id(f, source_hint)
        f["source"] = source_hint
        f["captured_at"] = now
        f["confidence"] = None      # 你自己后填
        f["status"] = "候选"
        if with_advice:
            try:
                f["dashboard_hook"] = advise_factor(f)
            except Exception as e:
                f["dashboard_hook"] = {"error": str(e)}
        out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="-", help="正文文件路径；'-' 读 stdin")
    ap.add_argument("--source", default="", help="研报来源提示")
    ap.add_argument("--no-advice", action="store_true", help="只蒸馏，不调看板顾问")
    args = ap.parse_args()
    text = sys.stdin.read() if args.text == "-" else Path(args.text).read_text()
    if len(text.strip()) < 100:
        print("[ERROR] 正文太短", file=sys.stderr); sys.exit(2)
    factors = forge(text, source_hint=args.source, with_advice=not args.no_advice)
    print(json.dumps(factors, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
