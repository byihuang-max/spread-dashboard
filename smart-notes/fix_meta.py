#!/usr/bin/env python3
"""
批量为 Smart Notes 补充标准元数据头。
从文件名提取日期，无日期则用 git 首次提交日期，再 fallback 到 mtime。
自动推断类型和分类标签。

用法:
    python3 smart-notes/fix_meta.py          # dry-run，只打印
    python3 smart-notes/fix_meta.py --apply  # 实际写入
"""

import os
import re
import sys
import subprocess
from pathlib import Path
from datetime import datetime

GAMT_ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = GAMT_ROOT / "smart-notes" / "notes"

# 分类 → 类型推断
CATEGORY_TYPE_MAP = {
    "research/factors": "概念",
    "research/strategy": "对话",
    "research/narrative": "概念",
    "engineering": "工程",
    "reports": "研报",
    "emerging_markets": "思考",
}

# 分类 → 默认标签
CATEGORY_TAGS = {
    "research/factors": "#因子 #择时",
    "research/strategy": "#策略 #框架",
    "research/narrative": "#叙事 #宏观",
    "engineering": "#工程 #部署",
    "reports": "#研报 #外部",
    "emerging_markets": "#新兴市场",
}

# 元数据检测：前 20 行有这些关键词就算有元数据
META_KEYWORDS = ["日期", "类型", "标签", "date", "tags", "type"]


def get_git_date(filepath):
    """获取文件的 git 首次提交日期"""
    try:
        result = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", str(filepath)],
            capture_output=True, text=True, cwd=str(GAMT_ROOT), timeout=5
        )
        dates = result.stdout.strip().split("\n")
        if dates and dates[-1]:
            return dates[-1][:10]  # YYYY-MM-DD
    except Exception:
        pass
    return None


def extract_date(filepath: Path):
    """从文件名提取日期，fallback git，再 fallback mtime"""
    # 文件名
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filepath.name)
    if m:
        return m.group(1), "filename"

    # 正文前 10 行
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        for line in content.split("\n")[:10]:
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            if dm:
                return dm.group(1), "content"
    except Exception:
        pass

    # git log
    git_date = get_git_date(filepath)
    if git_date:
        return git_date, "git"

    # mtime
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d"), "mtime"


def get_category(filepath: Path):
    """获取笔记的分类路径"""
    rel = str(filepath.relative_to(NOTES_DIR))
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "research":
        return f"research/{parts[1]}"
    return parts[0]


def has_meta(content):
    """检查前 20 行是否已有元数据"""
    head = "\n".join(content.split("\n")[:20]).lower()
    return any(kw.lower() in head for kw in META_KEYWORDS)


def build_meta_block(date_str, note_type, tags):
    """构建标准元数据块"""
    return f"**日期**: {date_str}  \n**类型**: {note_type}  \n**标签**: {tags}\n"


def fix_note(filepath: Path, apply=False):
    """为单个笔记补充元数据"""
    content = filepath.read_text(encoding="utf-8", errors="replace")

    if has_meta(content):
        return None  # 已有元数据，跳过

    date_str, source = extract_date(filepath)
    category = get_category(filepath)
    note_type = CATEGORY_TYPE_MAP.get(category, "笔记")
    tags = CATEGORY_TAGS.get(category, "#未分类")

    # 从文件名/标题提取更具体的标签
    title_line = ""
    lines = content.split("\n")
    for line in lines[:5]:
        if line.startswith("# "):
            title_line = line
            break

    meta_block = build_meta_block(date_str, note_type, tags)

    # 插入位置：标题行之后，第一个空行之前
    new_lines = []
    inserted = False
    for i, line in enumerate(lines):
        new_lines.append(line)
        if not inserted and line.startswith("# ") and i < 5:
            new_lines.append("")
            new_lines.append(meta_block)
            inserted = True

    if not inserted:
        # 没找到标题行，插在最前面
        new_lines = [meta_block, ""] + lines

    new_content = "\n".join(new_lines)

    if apply:
        filepath.write_text(new_content, encoding="utf-8")

    return {
        "path": filepath.relative_to(GAMT_ROOT),
        "date": date_str,
        "source": source,
        "type": note_type,
    }


def main():
    apply = "--apply" in sys.argv

    results = []
    for md in sorted(NOTES_DIR.rglob("*.md")):
        result = fix_note(md, apply=apply)
        if result:
            results.append(result)

    if not results:
        print("所有笔记已有元数据，无需修复。")
        return

    print(f"{'已修复' if apply else '待修复'} {len(results)} 篇笔记:\n")
    for r in results:
        print(f"  {'OK' if apply else '--'} {r['path']}  (日期: {r['date']} from {r['source']}, 类型: {r['type']})")

    if not apply:
        print(f"\n加 --apply 参数实际写入文件。")


if __name__ == "__main__":
    main()
