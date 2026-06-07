#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 正文抽取（多引擎兜底）
==========================
研报多为 PDF。按可用性依次尝试 pdfplumber → pymupdf(fitz) → pdfminer。
任一成功即返回；全失败则抛错，绝不伪造内容。

用法:
  python3 extract_pdf.py /path/to/report.pdf            # 打印正文
  python3 extract_pdf.py /path/to/report.pdf --json     # {"text":..., "pages":N, "engine":...}
"""
from __future__ import annotations
import sys, json, argparse
from pathlib import Path


def _try_pdfplumber(path: str):
    import pdfplumber
    parts = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            if t.strip():
                parts.append(t)
    return "\n\n".join(parts), n, "pdfplumber"


def _try_pymupdf(path: str):
    import fitz  # pymupdf
    parts = []
    doc = fitz.open(path)
    n = doc.page_count
    for pg in doc:
        t = pg.get_text() or ""
        if t.strip():
            parts.append(t)
    doc.close()
    return "\n\n".join(parts), n, "pymupdf"


def _try_pdfminer(path: str):
    from pdfminer.high_level import extract_text
    t = extract_text(path) or ""
    return t, t.count("\f") + 1, "pdfminer"


ENGINES = [_try_pdfplumber, _try_pymupdf, _try_pdfminer]


def extract_pdf(path: str) -> dict:
    """返回 {text, pages, engine}。全部引擎失败则抛 RuntimeError。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"PDF 不存在: {path}")
    errors = []
    for eng in ENGINES:
        try:
            text, pages, name = eng(path)
            if text and len(text.strip()) >= 100:
                return {"text": text, "pages": pages, "engine": name}
            errors.append(f"{eng.__name__}: 抽出正文过短({len(text.strip())}字)")
        except ImportError as e:
            errors.append(f"{eng.__name__}: 未安装({e})")
        except Exception as e:
            errors.append(f"{eng.__name__}: {e}")
    raise RuntimeError("所有 PDF 引擎均失败:\n  " + "\n  ".join(errors))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = extract_pdf(args.pdf)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        sys.stderr.write(f"[engine={res['engine']} pages={res['pages']}]\n")
        print(res["text"])


if __name__ == "__main__":
    main()
