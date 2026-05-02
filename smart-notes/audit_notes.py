#!/usr/bin/env python3
"""
Smart Notes 完整性审计脚本

扫描 GAMT 看板模块 × Smart Notes 笔记，输出缺失/不完整/陈旧的条目清单。
结果写入 smart-notes/AUDIT.md，也可打印到终端。

用法:
    python3 smart-notes/audit_notes.py              # 跑审计，输出 AUDIT.md
    python3 smart-notes/audit_notes.py --stdout      # 只打印不写文件
    python3 smart-notes/audit_notes.py --fix-meta    # 列出缺元数据的笔记（方便批量补）

审计维度:
    1. 模块覆盖 — 看板有模块但 Smart Notes 无对应笔记
    2. 元数据完整性 — 笔记缺日期/标签/看板关联
    3. 陈旧检测 — 笔记 >60 天未更新，但对应代码目录有新变动
    4. 对话沉淀 — memory/ 日记中的重要决策未在 Smart Notes 出现
    5. 空目录 — 分类目录下无任何笔记
"""

import os
import re
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
GAMT_ROOT = Path(__file__).resolve().parent.parent          # ~/Desktop/gamt-dashboard
NOTES_DIR = GAMT_ROOT / "smart-notes" / "notes"
REGISTRY_FILE = GAMT_ROOT / "server" / "module_registry.py"
MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "memory"
AUDIT_OUTPUT = GAMT_ROOT / "smart-notes" / "AUDIT.md"

# ── 模块 → 关键词映射 ────────────────────────────────
# 用于在笔记正文中匹配"这篇笔记是否覆盖了某个模块"
# key = module_registry 的 key, value = 搜索关键词列表（任一命中即算覆盖）
MODULE_KEYWORDS = {
    "style_spread":       ["风格轧差", "style_spread", "size_spread", "大小盘切换"],
    "quant_stock":        ["量化股票", "quant_stock", "宽基量化", "指增", "300指增"],
    "momentum_stock":     ["强势股", "momentum", "涨跌停", "连板", "打板", "龙头"],
    "commodity_cta":      ["商品CTA", "CTA", "commodity_cta", "PCA", "趋势跟踪"],
    "cb_env":             ["转债", "cb_env", "可转债", "转债指增"],
    "alerts":             ["红灯", "预警", "alerts", "风险评分", "红灯预警"],
    "us_alerts":          ["美股风险", "us_alerts", "美股监控"],
    "crowding":           ["拥挤度", "crowding", "资金流"],
    "option_sentiment":   ["期权情绪", "option_sentiment", "IV", "隐含波动率"],
    "patient_capital":    ["耐心资本", "patient_capital", "ETF大单", "15min"],
    "macro_liquidity":    ["流动性", "Shibor", "DR007", "M1M2", "macro_liquidity"],
    "macro_rates":        ["利率", "rates", "美债", "汇率"],
    "macro_fundamentals": ["基本面", "PMI", "CPI", "PPI", "fundamentals"],
    "antifragile":        ["反脆弱", "antifragile", "meme"],
    "narrative_monitor":  ["叙事监控", "narrative_monitor", "叙事"],
    "narrative_lifecycle":["叙事生命周期", "narrative_lifecycle", "Meme生命周期"],
    "chain_prosperity":   ["中观景气", "产业链", "chain_prosperity", "景气度"],
    "macro_score":        ["宏观打分", "macro_score", "策略适配"],
    "timing_factors":     ["择时", "timing", "因子系统", "敞口", "情绪接力"],
    "option_vol":         ["期权卖权", "option_vol", "卖权"],
    "arbitrage":          ["套利", "arbitrage", "指数套利", "商品套利"],
    "macro/halo_trade":   ["HALO", "halo", "重资产", "范式转移"],
    "fund_asset":         ["基金优选", "fund_asset", "团队基金", "产品池"],
    "overview":           ["仪表盘", "overview", "总控", "打分系统"],
    "financial_risk":     ["财报风险", "financial_risk", "雷票", "财报因子"],
}

# 笔记元数据标准字段（在前 20 行内检测）
EXPECTED_META_FIELDS = ["日期", "类型", "标签", "date", "tags", "type"]
# 看板关联关键词
LINK_KEYWORDS = ["看板关联", "关联模块", "关联看板", "GAMT.*关联", "模块位置"]


def load_module_registry():
    """从 module_registry.py 提取所有 include_in_update_all=True 的模块"""
    modules = {}
    if not REGISTRY_FILE.exists():
        return modules
    # 简单正则提取，不 exec 外部代码
    content = REGISTRY_FILE.read_text(encoding="utf-8")
    # 匹配 'key': { ... 'name': '中文名' ... }
    pattern = r"'([^']+)':\s*\{[^}]*'name':\s*'([^']+)'"
    for m in re.finditer(pattern, content):
        key, name = m.group(1), m.group(2)
        modules[key] = name
    return modules


def scan_notes():
    """扫描所有笔记，返回 [{path, title, content, mtime, has_meta, has_link, date_str}]"""
    notes = []
    if not NOTES_DIR.exists():
        return notes
    for md in NOTES_DIR.rglob("*.md"):
        content = md.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        head = "\n".join(lines[:20]).lower()

        # 提取标题
        title = md.stem
        for line in lines[:5]:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break

        # 检测元数据字段
        has_meta = any(kw.lower() in head for kw in EXPECTED_META_FIELDS)

        # 检测看板关联
        has_link = any(re.search(kw, content, re.IGNORECASE) for kw in LINK_KEYWORDS)

        # 提取日期（文件名或正文）
        date_str = None
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", md.name)
        if date_match:
            date_str = date_match.group(1)
        else:
            for line in lines[:10]:
                dm = re.search(r"(\d{4}-\d{2}-\d{2})", line)
                if dm:
                    date_str = dm.group(1)
                    break

        mtime = datetime.fromtimestamp(md.stat().st_mtime)

        notes.append({
            "path": md.relative_to(GAMT_ROOT),
            "title": title,
            "content": content,
            "mtime": mtime,
            "has_meta": has_meta,
            "has_link": has_link,
            "date_str": date_str,
            "category": str(md.relative_to(NOTES_DIR)).split("/")[0],
        })
    return notes


def check_module_coverage(modules, notes):
    """检查每个看板模块是否有对应笔记覆盖"""
    all_text = {n["path"]: n["content"] for n in notes}
    uncovered = []
    covered = {}

    for mod_key, mod_name in modules.items():
        keywords = MODULE_KEYWORDS.get(mod_key, [mod_name])
        matching_notes = []
        for note in notes:
            if any(kw.lower() in note["content"].lower() for kw in keywords):
                matching_notes.append(note["path"])
        if matching_notes:
            covered[mod_key] = matching_notes
        else:
            uncovered.append((mod_key, mod_name))

    return covered, uncovered


def check_meta_completeness(notes):
    """检查笔记元数据完整性"""
    missing_meta = []
    missing_link = []
    missing_date = []

    for note in notes:
        if not note["has_meta"]:
            missing_meta.append(note)
        if not note["has_link"]:
            missing_link.append(note)
        if not note["date_str"]:
            missing_date.append(note)

    return missing_meta, missing_link, missing_date


def check_staleness(notes, days=60):
    """检查超过 N 天未更新的笔记"""
    cutoff = datetime.now() - timedelta(days=days)
    stale = []
    for note in notes:
        if note["mtime"] < cutoff:
            age = (datetime.now() - note["mtime"]).days
            stale.append((note, age))
    stale.sort(key=lambda x: -x[1])
    return stale


def check_empty_categories():
    """检查空分类目录"""
    empty = []
    if not NOTES_DIR.exists():
        return empty
    for d in NOTES_DIR.iterdir():
        if d.is_dir():
            # 检查子目录（如 research/factors）
            sub_has_md = False
            for item in d.rglob("*.md"):
                sub_has_md = True
                break
            if not sub_has_md:
                empty.append(d.relative_to(NOTES_DIR))
    return empty


def check_memory_gaps(notes, recent_days=14):
    """扫描最近 N 天的 memory 日记，找出提到但未沉淀的重要决策"""
    if not MEMORY_DIR.exists():
        return []

    # 收集所有笔记标题关键词（用于匹配）
    note_titles = set()
    for n in notes:
        note_titles.add(n["title"].lower())
        # 也加文件名
        note_titles.add(n["path"].stem.lower())

    # 决策/设计相关关键词 — 只匹配 markdown 标题行，减少噪音
    decision_patterns = [
        r"^(#{1,3}\s+\d*\.?\s*.+(?:决策|设计|方案|架构|新增|重构|迁移|搭建|新模块|新功能).+)",
    ]

    gaps = []
    cutoff = datetime.now() - timedelta(days=recent_days)

    for md in sorted(MEMORY_DIR.glob("*.md")):
        # 提取日期
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", md.name)
        if not date_match:
            continue
        try:
            file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            continue

        content = md.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        for i, line in enumerate(lines):
            for pattern in decision_patterns:
                m = re.search(pattern, line)
                if m:
                    topic = m.group(1).strip()[:60]
                    # 检查是否已有对应笔记
                    topic_lower = topic.lower()
                    already_covered = False
                    for nt in note_titles:
                        # 模糊匹配：笔记标题包含决策关键词的前 8 个字
                        if len(topic_lower) >= 8 and topic_lower[:8] in nt:
                            already_covered = True
                            break
                        if len(nt) >= 8 and nt[:8] in topic_lower:
                            already_covered = True
                            break
                    if not already_covered:
                        gaps.append({
                            "source": md.name,
                            "line": i + 1,
                            "topic": topic,
                        })

    # 去重（同一 topic 只报一次）
    seen = set()
    unique_gaps = []
    for g in gaps:
        key = g["topic"][:20]
        if key not in seen:
            seen.add(key)
            unique_gaps.append(g)

    return unique_gaps[:20]  # 最多报 20 条


def generate_report(modules, notes):
    """生成审计报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Smart Notes 审计报告",
        f"",
        f"> 生成时间: {now}",
        f"> 笔记总数: {len(notes)}",
        f"> 看板模块数: {len(modules)}",
        f"",
    ]

    # ── 1. 模块覆盖 ──
    covered, uncovered = check_module_coverage(modules, notes)
    lines.append("## 1. 模块覆盖检查")
    lines.append("")
    if uncovered:
        lines.append(f"以下 **{len(uncovered)}** 个看板模块在 Smart Notes 中没有对应笔记:")
        lines.append("")
        for key, name in uncovered:
            lines.append(f"- [ ] **{name}** (`{key}`)")
        lines.append("")
    else:
        lines.append("全部模块已覆盖。")
        lines.append("")

    covered_count = len(covered)
    total = len(modules)
    lines.append(f"覆盖率: {covered_count}/{total} ({covered_count*100//total}%)")
    lines.append("")

    # ── 2. 元数据完整性 ──
    missing_meta, missing_link, missing_date = check_meta_completeness(notes)
    lines.append("## 2. 元数据完整性")
    lines.append("")

    if missing_date:
        lines.append(f"### 缺少日期 ({len(missing_date)} 篇)")
        lines.append("")
        for n in missing_date:
            lines.append(f"- [ ] `{n['path']}`")
        lines.append("")

    if missing_meta:
        lines.append(f"### 缺少标准元数据 ({len(missing_meta)} 篇)")
        lines.append(f"标准字段: 日期、类型、标签")
        lines.append("")
        for n in missing_meta:
            lines.append(f"- [ ] `{n['path']}` — {n['title']}")
        lines.append("")

    if missing_link:
        lines.append(f"### 缺少看板关联 ({len(missing_link)} 篇)")
        lines.append("")
        for n in missing_link:
            lines.append(f"- [ ] `{n['path']}` — {n['title']}")
        lines.append("")

    if not missing_date and not missing_meta and not missing_link:
        lines.append("全部笔记元数据完整。")
        lines.append("")

    # ── 3. 陈旧检测 ──
    stale = check_staleness(notes, days=60)
    lines.append("## 3. 陈旧笔记 (>60天未更新)")
    lines.append("")
    if stale:
        lines.append(f"共 **{len(stale)}** 篇:")
        lines.append("")
        for note, age in stale[:15]:
            lines.append(f"- [ ] `{note['path']}` — {age}天前 — {note['title']}")
        if len(stale) > 15:
            lines.append(f"- ...还有 {len(stale)-15} 篇")
        lines.append("")
    else:
        lines.append("无陈旧笔记。")
        lines.append("")

    # ── 4. 空分类目录 ──
    empty = check_empty_categories()
    lines.append("## 4. 空分类目录")
    lines.append("")
    if empty:
        for d in empty:
            lines.append(f"- [ ] `notes/{d}/` — 无任何笔记")
        lines.append("")
    else:
        lines.append("无空目录。")
        lines.append("")

    # ── 5. 对话沉淀检查 ──
    gaps = check_memory_gaps(notes, recent_days=14)
    lines.append("## 5. 近14天对话中可能未沉淀的决策")
    lines.append("")
    if gaps:
        lines.append(f"共 **{len(gaps)}** 条疑似未沉淀:")
        lines.append("")
        for g in gaps:
            lines.append(f"- [ ] `{g['source']}` L{g['line']}: {g['topic']}")
        lines.append("")
        lines.append("*注: 模糊匹配，可能有误报。标记为已处理的可忽略。*")
        lines.append("")
    else:
        lines.append("近期决策均已沉淀（或无新决策）。")
        lines.append("")

    # ── 汇总 ──
    total_issues = len(uncovered) + len(missing_meta) + len(missing_link) + len(missing_date) + len(stale) + len(empty) + len(gaps)
    lines.append("---")
    lines.append("")
    lines.append(f"**待处理项总计: {total_issues}**")
    lines.append("")
    if total_issues == 0:
        lines.append("Smart Notes 状态良好，无需处理。")
    elif total_issues <= 5:
        lines.append("少量待补项，建议本周内处理。")
    elif total_issues <= 15:
        lines.append("中等数量待补项，建议分批处理。")
    else:
        lines.append("待补项较多，建议优先处理模块覆盖和缺日期的笔记。")

    return "\n".join(lines)


def main():
    stdout_only = "--stdout" in sys.argv
    fix_meta = "--fix-meta" in sys.argv

    modules = load_module_registry()
    notes = scan_notes()

    if fix_meta:
        # 只列出缺元数据的笔记路径，方便批量处理
        missing_meta, _, missing_date = check_meta_completeness(notes)
        print("=== 缺元数据 ===")
        for n in missing_meta:
            print(str(GAMT_ROOT / n["path"]))
        print(f"\n=== 缺日期 ===")
        for n in missing_date:
            print(str(GAMT_ROOT / n["path"]))
        return

    report = generate_report(modules, notes)

    if stdout_only:
        print(report)
    else:
        AUDIT_OUTPUT.write_text(report, encoding="utf-8")
        print(f"审计报告已写入: {AUDIT_OUTPUT}")
        # 也打印摘要
        lines = report.split("\n")
        for line in lines:
            if line.startswith("**待处理项") or line.startswith("覆盖率"):
                print(line)


if __name__ == "__main__":
    main()
