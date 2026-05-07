#!/usr/bin/env python3
"""
URL / HTML → 正文抽取
=====================

优先级：
1. readability-lxml（最准）
2. BeautifulSoup 兜底（抓 <article> / <main> / 所有 <p>）
3. 失败返回 {"status": "extract_error", "reason": "..."}
"""

from __future__ import annotations

import re
import sys
import json
import argparse
from urllib.parse import urlparse

import requests
import certifi


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 15) -> tuple[str, str]:
    """返回 (html, final_url)"""
    r = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        verify=certifi.where(),
        allow_redirects=True,
    )
    r.raise_for_status()
    # 编码兜底
    if r.encoding and r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text, r.url


def extract_with_readability(html: str, url: str) -> dict | None:
    try:
        from readability import Document
    except ImportError:
        return None
    try:
        doc = Document(html)
        title = (doc.short_title() or "").strip()
        summary_html = doc.summary(html_partial=True)
        # 剥 HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(summary_html, "html.parser")
        text = _clean_text(soup.get_text("\n"))
        if len(text) < 200:
            return None
        return {"title": title, "text": text, "method": "readability"}
    except Exception as e:
        return None


def extract_with_bs4(html: str) -> dict:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # 标题
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    # 去掉 script / style / nav / aside / footer / header
    for bad in soup(["script", "style", "noscript", "nav", "aside", "footer", "header"]):
        bad.decompose()

    # 优先 article / main
    container = soup.find("article") or soup.find("main")
    if container:
        text = _clean_text(container.get_text("\n"))
        if len(text) >= 200:
            return {"title": title, "text": text, "method": "article"}

    # 否则抓所有 p，按长度排序 top N
    ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    ps = [p for p in ps if len(p) > 20]
    text = "\n\n".join(ps)
    text = _clean_text(text)
    return {"title": title, "text": text, "method": "bs4-paragraphs"}


def _clean_text(text: str) -> str:
    # 压缩多余空白
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = text.strip()
    return text


def extract_from_url(url: str) -> dict:
    try:
        html, final_url = fetch_html(url)
    except Exception as e:
        return {
            "status": "extract_error",
            "reason": f"fetch_failed: {type(e).__name__}: {e}",
            "url": url,
        }

    result = extract_with_readability(html, url)
    if not result:
        result = extract_with_bs4(html)

    text = result.get("text", "")
    if len(text) < 200:
        return {
            "status": "extract_error",
            "reason": f"too_short: len={len(text)}",
            "url": url,
            "title": result.get("title", ""),
            "partial_text": text[:500],
        }

    return {
        "status": "ok",
        "url": url,
        "final_url": final_url,
        "title": result.get("title") or _guess_title(url),
        "text": text,
        "method": result.get("method"),
        "length": len(text),
    }


def _guess_title(url: str) -> str:
    p = urlparse(url)
    return (p.path.rstrip("/").split("/")[-1] or p.netloc) or url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = extract_from_url(args.url)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["status"] != "ok":
            print(f"[ERROR] {result['reason']}", file=sys.stderr)
            sys.exit(2)
        print(f"[{result['method']}] {result['title']}")
        print(f"length: {result['length']}")
        print("---")
        print(result["text"][:2000])


if __name__ == "__main__":
    main()
