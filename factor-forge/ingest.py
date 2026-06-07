#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Factor Forge 端到端 CLI
========================
PDF 研报 → 抽正文 → 蒸馏因子 → 看板顾问 → 入库

用法:
  python3 ingest.py report.pdf --source "中信证券-半导体深度"
  python3 ingest.py report.pdf --source "..." --no-advice   # 跳过看板顾问(快)
  python3 ingest.py report.pdf --dry                         # 只看结果不入库
  echo "正文..." | python3 ingest.py --text - --source "..."  # 直接喂文本
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path

BASE = Path("/Users/apple/Desktop/gamt-dashboard/factor-forge")
sys.path.insert(0, str(BASE))
import forge, store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", help="PDF 路径")
    ap.add_argument("--text", help="'-' 从 stdin 读正文（替代 PDF）")
    ap.add_argument("--source", default="", help="研报来源")
    ap.add_argument("--no-advice", action="store_true")
    ap.add_argument("--dry", action="store_true", help="不入库")
    args = ap.parse_args()

    # 1. 拿正文
    if args.text == "-":
        text = sys.stdin.read()
        src = args.source or "stdin"
    elif args.pdf:
        from extract_pdf import extract_pdf
        res = extract_pdf(args.pdf)
        text = res["text"]
        src = args.source or Path(args.pdf).stem
        sys.stderr.write(f"[抽取] {res['engine']} / {res['pages']}页 / {len(text)}字\n")
    else:
        ap.error("需要提供 PDF 路径或 --text -")

    if len(text.strip()) < 100:
        sys.stderr.write("[ERROR] 正文太短\n"); sys.exit(2)

    # 2. 蒸馏 + 顾问
    sys.stderr.write("[蒸馏] 调 LLM 中...\n")
    factors = forge.forge(text, source_hint=src, with_advice=not args.no_advice)
    sys.stderr.write(f"[蒸馏] 得到 {len(factors)} 条因子\n")

    # 3. 入库
    if not args.dry and factors:
        r = store.add_factors(factors)
        sys.stderr.write(f"[入库] 新增{r['added']} 跳过{r['skipped']} 库内共{r['total']}\n")
    elif args.dry:
        sys.stderr.write("[dry] 未入库\n")

    print(json.dumps(factors, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
