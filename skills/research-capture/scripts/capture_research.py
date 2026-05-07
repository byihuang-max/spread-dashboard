#!/usr/bin/env python3
"""
research-capture 主入口
=======================

用法：
    # URL 入库
    python3 capture_research.py --url "https://xxx" --save

    # 文本入库
    echo "正文..." | python3 capture_research.py --text - --save

    # 预览不落盘
    python3 capture_research.py --url "https://xxx" --dry

    # 带元数据提示
    python3 capture_research.py --url "https://xxx" --source "中信证券" --author "张三" --save

流程：
    extract_content.extract_from_url  →  distill.distill  →  render_markdown
      →  save_note.py（Smart Notes 管线）  →  回执
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract_content import extract_from_url  # noqa: E402
from distill import distill, render_markdown  # noqa: E402


SAVE_NOTE_PY = str(
    Path.home() / "Desktop" / "gamt-dashboard" / "smart-notes" / "intelligence" / "save_note.py"
)


def call_save_note(markdown: str, dry: bool = False) -> dict:
    """把 markdown 喂给 save_note.py，返回 JSON 结果"""
    cmd = ["python3", SAVE_NOTE_PY, "--json"]
    if dry:
        cmd.append("--dry")
    r = subprocess.run(
        cmd,
        input=markdown.encode("utf-8"),
        capture_output=True,
        timeout=120,
    )
    if r.returncode != 0:
        return {
            "status": "save_error",
            "reason": r.stderr.decode("utf-8", errors="replace")[:500],
            "stdout": r.stdout.decode("utf-8", errors="replace")[:500],
        }
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "save_error",
            "reason": "save_note 返回非 JSON",
            "stdout": r.stdout.decode("utf-8", errors="replace")[:500],
        }


def format_receipt(meta: dict, save_result: dict, extract_info: dict | None = None) -> str:
    """飞书回执（终端风格，无装饰 emoji）"""
    status = save_result.get("status", "unknown")
    title = meta.get("title", "未命名")
    novelty = meta.get("novelty", "?")
    tradability = meta.get("tradability", "?")
    theme = meta.get("theme", "?")

    lines = []
    if status == "written":
        lines.append("● 已收录")
        lines.append(f"标题：{title}")
        lines.append(f"主题：{theme}")
        lines.append(f"类别（Smart Notes）：{save_result.get('category', '?')}")
        lines.append(f"新信息密度：{novelty}")
        lines.append(f"可交易性：{tradability}")
        lines.append(f"路径：{save_result.get('path', '?')}")
        if save_result.get("is_iteration"):
            lines.append(f"迭代识别：v{save_result.get('iteration_version')}，来源 {save_result.get('iteration_of')}")
    elif status == "need_confirm":
        lines.append("○ 需要确认")
        lines.append(f"标题：{title}")
        lines.append(f"原因：{save_result.get('reason', '分类置信度不足')}")
        lines.append("建议：手动指定类别，或强制收录")
    elif status == "preview":
        lines.append("◇ 预览（未落盘）")
        lines.append(f"标题：{title}")
        lines.append(f"主题：{theme}")
        lines.append(f"建议类别：{save_result.get('category', '?')}")
        lines.append(f"建议路径：{save_result.get('target_path', '?')}")
    else:
        lines.append("○ 未入库")
        lines.append(f"原因：{save_result.get('reason', '未知')}")

    if extract_info and extract_info.get("method"):
        lines.append(f"抽取方式：{extract_info['method']}（{extract_info.get('length', 0)} 字）")

    return "\n".join(lines)


def run(args) -> int:
    # 1. 获取正文
    extract_info = None
    text = ""
    url = args.url or ""

    if args.url:
        extract_info = extract_from_url(args.url)
        if extract_info["status"] != "ok":
            print("○ 未入库", file=sys.stderr)
            print(f"原因：{extract_info['reason']}", file=sys.stderr)
            print("建议：把原文贴到对话里，我再入库", file=sys.stderr)
            return 2
        text = extract_info["text"]
        # 如果 LLM 没拿到更好的 title，用 extract 的
        url = extract_info.get("final_url") or args.url
    elif args.text:
        if args.text == "-":
            text = sys.stdin.read()
        else:
            with open(args.text) as f:
                text = f.read()
    else:
        print("[ERROR] 必须指定 --url 或 --text", file=sys.stderr)
        return 2

    if len(text.strip()) < 200:
        print("○ 未入库", file=sys.stderr)
        print("原因：正文<200 字，信息量不足", file=sys.stderr)
        return 2

    # 2. LLM 做投研拆解
    try:
        meta = distill(text, source_hint=args.source, author_hint=args.author, url=url)
    except Exception as e:
        print("○ 未入库", file=sys.stderr)
        print(f"原因：distill 失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 3

    # 如果 extract 拿到了标题但 LLM 没给，补上
    if extract_info and not meta.get("title"):
        meta["title"] = extract_info.get("title", "")

    markdown = render_markdown(meta, url=url)

    # 3. 仅预览模式
    if args.preview_only:
        print(markdown)
        return 0

    # 4. 调 Smart Notes 管线
    save_result = call_save_note(markdown, dry=args.dry)

    # 5. 回执
    if args.json:
        print(json.dumps({
            "meta": meta,
            "save_result": save_result,
            "extract_info": extract_info,
        }, ensure_ascii=False, indent=2))
    else:
        print(format_receipt(meta, save_result, extract_info))

    if save_result.get("status") in ("written", "preview"):
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser(
        description="research-capture 主入口：URL/文本 → 投研笔记 → Smart Notes"
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="研报/文章链接")
    src.add_argument("--text", help="正文文件路径，'-' 从 stdin 读")

    ap.add_argument("--source", default="", help="来源机构提示")
    ap.add_argument("--author", default="", help="作者提示")

    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--save", action="store_true", help="正式落盘（默认需显式指定）")
    mode.add_argument("--dry", action="store_true", help="走完管线但不落盘（预览 Smart Notes 分类结果）")
    mode.add_argument("--preview-only", action="store_true", help="只做 distill，不调 save_note，直接打印 Markdown")

    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # 默认 dry，避免误入库
    if not (args.save or args.dry or args.preview_only):
        args.dry = True

    sys.exit(run(args))


if __name__ == "__main__":
    main()
