#!/usr/bin/env python3
"""
Smart Notes 存笔记包装脚本
============================

使用场景：
    当 Roni 在飞书/Claude 对话中说"存笔记：<内容>"时，
    我（leijun bot）调用这个脚本自动归档。

用法：
    # 从 stdin 读：
    echo "笔记内容..." | python3 save_note.py
    
    # 直接传文本（会处理换行）：
    python3 save_note.py "笔记内容..."
    
    # 预览不写入：
    python3 save_note.py --dry "笔记内容..."
    
    # 强制指定类别（跳过 AI 决策）：
    python3 save_note.py --category engineering "内容..."

返回：JSON + 一段中文总结
"""

from __future__ import annotations

import sys
import json
import argparse

from note_pipeline import ingest, ROOT


def format_summary(result: dict) -> str:
    """把 ingest 结果格式化成人话汇报"""
    status = result.get("status")
    if status == "need_confirm":
        lines = ["⚠️  需要你确认一下"]
        lines.append(f"原因：{result.get('reason')}")
        if "meta" in result:
            m = result["meta"]
            lines.append(f"建议标题：{m.get('title','?')}")
            lines.append(f"建议类别（AI）：{m.get('category_hint','?')}")
        return "\n".join(lines)

    icon = "✅" if status == "written" else "🔍"
    kind = "已写入" if status == "written" else "预览"
    path = result.get("path") or result.get("target_path")
    cat = result.get("category")

    lines = [f"{icon} 笔记{kind}：`{path}`"]
    lines.append(f"   类别：{cat}")

    if result.get("is_iteration"):
        lines.append(f"   识别为迭代：v{result.get('iteration_version')}")
        lines.append(f"   来源：{result.get('iteration_of')}")

    meta = result.get("meta", {})
    if meta.get("tags"):
        lines.append(f"   标签：{' '.join('#' + t for t in meta['tags'])}")

    lines.append("")
    lines.append("决策过程：")
    for d in result.get("decisions", []):
        lines.append(f"  {d}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="*", help="笔记内容；留空则从 stdin 读")
    ap.add_argument("--dry", action="store_true", help="预览不写入")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    if args.text:
        text = " ".join(args.text)
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("(没有内容)", file=sys.stderr)
        sys.exit(1)

    result = ingest(text, dry_run=args.dry)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_summary(result))


if __name__ == "__main__":
    main()
