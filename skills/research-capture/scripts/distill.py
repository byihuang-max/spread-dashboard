#!/usr/bin/env python3
"""
正文 → 投研结构化 Markdown
==========================

调 Claude（走 Smart Notes 管线用的 aicanapi-47 provider）把抽出的正文
拆解成标准投研笔记 Markdown。

输出字段参考 references/note_schema.md。
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import datetime as dt
from pathlib import Path

# 复用 Smart Notes 管线的 Claude 客户端，避免重复实现
INTEL_DIR = Path.home() / "Desktop" / "gamt-dashboard" / "smart-notes" / "intelligence"
sys.path.insert(0, str(INTEL_DIR))

from llm_client import call_claude  # noqa: E402


SYSTEM_PROMPT = """你是 Roni（FOF 基金经理）的投研助理。

Roni 的关注点：
- 量化股票 / 强势股 / 商品 CTA / 转债指增 / 套利
- 宏观→中观→微观→策略环境全链路
- 更关心"可交易性"和"新信息密度"，而不是花哨结论

任务：把输入的投研正文，拆解成一份结构化 Markdown 笔记。

要求：
1. 不编造数据和观点，原文没有就不写
2. 一句话结论控制在 50 字内
3. 核心观点 3-5 条，每条 1-2 行
4. 关键证据优先保留数字、日期、具体案例
5. 影响资产/策略部分必须明确到 Roni 的策略池
6. 诚实评估 novelty 和 tradability
7. 风险 / 反方观点必写，至少 1 条
"""


OUTPUT_TEMPLATE = """请严格按以下 JSON 格式返回，不要有任何额外文字：

{
  "title": "<标题>",
  "source": "<发布机构/媒体，未知填空>",
  "author": "<作者，未知填空>",
  "date": "<原文日期 YYYY-MM-DD，未知填空>",
  "theme": "<research/reports | research/factors | research/strategy | research/narrative | conversations | concepts 之一>",
  "novelty": "<高|中|低>",
  "tradability": "<高|中|低>",
  "one_line": "<50 字内一句话结论>",
  "core_views": ["<观点1>", "<观点2>", "<观点3>"],
  "key_evidence": ["<证据/数据1>", "<证据/数据2>"],
  "affected": {
    "a_share": "<A股影响>",
    "bonds": "<债市影响>",
    "commodity": "<商品影响>",
    "fof_strategy": "<对 FOF 策略池的具体含义>"
  },
  "risks": ["<风险/反方观点1>", "<风险/反方观点2>"]
}
"""


def distill(text: str, source_hint: str = "", author_hint: str = "", url: str = "") -> dict:
    prompt_parts = []
    if source_hint:
        prompt_parts.append(f"来源提示：{source_hint}")
    if author_hint:
        prompt_parts.append(f"作者提示：{author_hint}")
    if url:
        prompt_parts.append(f"原文链接：{url}")

    prompt_parts.append("\n[正文]\n")
    prompt_parts.append(text[:20000])  # 保险，超长截断
    prompt_parts.append("\n\n")
    prompt_parts.append(OUTPUT_TEMPLATE)

    prompt = "\n".join(prompt_parts)

    raw = call_claude(prompt, system=SYSTEM_PROMPT, max_tokens=2000)
    # 容错：去掉可能的 ```json 包裹
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    # 多层容错解析
    for attempt_text in [raw, _fix_json(raw)]:
        try:
            return json.loads(attempt_text)
        except json.JSONDecodeError:
            pass

    # 抓第一个 { 到最后一个 }
    l = raw.find("{")
    r = raw.rfind("}")
    if l >= 0 and r > l:
        chunk = raw[l:r + 1]
        for attempt_text in [chunk, _fix_json(chunk)]:
            try:
                return json.loads(attempt_text)
            except json.JSONDecodeError:
                pass

    raise RuntimeError(f"LLM 返回无法解析为 JSON\n原始输出:\n{raw[:1000]}")


def _fix_json(s: str) -> str:
    """尝试修复常见的 JSON 格式问题"""
    import re as _re
    # 修复尾部逗号 (trailing comma before } or ])
    s = _re.sub(r",\s*([}\]])", r"\1", s)
    # 修复换行符在字符串值里没转义
    # 简单策略：把 key: "value 中的裸换行变成 \\n
    # 但这很危险，只修最简单的情况
    return s


def render_markdown(meta: dict, url: str = "") -> str:
    """生成符合 Smart Notes 格式的 Markdown"""
    today = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    def _yaml_safe(v: str) -> str:
        if not v:
            return ""
        # 简单转义
        return str(v).replace('"', "'")

    lines = []
    lines.append("---")
    lines.append(f'source: "{_yaml_safe(meta.get("source", ""))}"')
    lines.append(f'author: "{_yaml_safe(meta.get("author", ""))}"')
    lines.append(f'date: "{_yaml_safe(meta.get("date", ""))}"')
    lines.append(f'url: "{_yaml_safe(url)}"')
    lines.append(f'captured_at: "{today}"')
    lines.append(f'novelty: "{_yaml_safe(meta.get("novelty", ""))}"')
    lines.append(f'tradability: "{_yaml_safe(meta.get("tradability", ""))}"')
    lines.append(f'theme: "{_yaml_safe(meta.get("theme", ""))}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {meta.get('title', '未命名投研笔记')}")
    lines.append("")
    lines.append(f"**一句话结论：** {meta.get('one_line', '')}")
    lines.append("")

    core = meta.get("core_views", []) or []
    if core:
        lines.append("## 核心观点")
        lines.append("")
        for v in core:
            lines.append(f"- {v}")
        lines.append("")

    evi = meta.get("key_evidence", []) or []
    if evi:
        lines.append("## 关键证据 / 数据")
        lines.append("")
        for e in evi:
            lines.append(f"- {e}")
        lines.append("")

    aff = meta.get("affected", {}) or {}
    if any(aff.values()):
        lines.append("## 影响资产 / 策略")
        lines.append("")
        if aff.get("a_share"):
            lines.append(f"- **A 股：** {aff['a_share']}")
        if aff.get("bonds"):
            lines.append(f"- **债市：** {aff['bonds']}")
        if aff.get("commodity"):
            lines.append(f"- **商品：** {aff['commodity']}")
        if aff.get("fof_strategy"):
            lines.append(f"- **FOF 策略含义：** {aff['fof_strategy']}")
        lines.append("")

    risks = meta.get("risks", []) or []
    if risks:
        lines.append("## 风险 / 反方观点")
        lines.append("")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    if url:
        lines.append("## 原文参考")
        lines.append("")
        lines.append(f"- 链接：{url}")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="-", help="正文文件路径；'-' 表示从 stdin 读")
    ap.add_argument("--url", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--json", action="store_true", help="输出 JSON 元数据而不是 Markdown")
    args = ap.parse_args()

    if args.text == "-":
        text = sys.stdin.read()
    else:
        with open(args.text) as f:
            text = f.read()

    if len(text.strip()) < 100:
        print("[ERROR] 正文太短", file=sys.stderr)
        sys.exit(2)

    meta = distill(text, source_hint=args.source, author_hint=args.author, url=args.url)

    if args.json:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(meta, url=args.url))


if __name__ == "__main__":
    main()
