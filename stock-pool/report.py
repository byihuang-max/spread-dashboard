#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接龙跟踪报告生成器：调用 track.py 的逻辑，输出 Markdown 简报。"""
from __future__ import annotations
import json, sys, subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
PY = "/opt/homebrew/bin/python3"

def run_track(jl_file, latest):
    out = subprocess.check_output(
        [PY, str(BASE/"track.py"), jl_file, latest],
        stderr=subprocess.DEVNULL, text=True)
    # 跳过登录提示行，取 JSON
    js = out[out.index("{"):]
    return json.loads(js)

def arrow(x):
    return "🔴" if x >= 9.9 else ("🟢" if x > 0 else ("⚪" if x == 0 else "🔻"))

def fmt(d):
    L = []
    L.append(f"# 📊 接龙跟踪 | 基准 {d['base_date']} → {d['latest']}")
    L.append(f"\n沪深300 同期 **{d['hs300_ret']:+.2f}%** ｜ 有效标的 {d['n_valid']} 支")
    if d["invalid_tickers"]:
        L.append(f"\n⚠️ 待补代码: {', '.join(d['invalid_tickers'])}")

    # 共识榜
    L.append("\n## 🔥 共识榜（被多人推荐）")
    L.append("\n| 票 | 代码 | 共识 | 区间涨跌 | 超额 | 题材 |")
    L.append("|---|---|---|---|---|---|")
    for s in d["stocks"]:
        if s["consensus"] >= 2:
            L.append(f"| {s['name']} | {s['ticker']} | {s['consensus']}人 | "
                     f"{arrow(s['ret'])}{s['ret']:+.1f}% | {s['excess']:+.1f}% | {s['sector']} |")

    # 领涨/掉队
    ranked = sorted(d["stocks"], key=lambda x: -x["ret"])
    L.append("\n## 🚀 区间领涨 TOP5")
    for s in ranked[:5]:
        L.append(f"- {s['name']}({s['ticker']}) {arrow(s['ret'])}**{s['ret']:+.1f}%** 超额{s['excess']:+.1f}% · {'/'.join(s['recs'])}")
    L.append("\n## 🔻 区间掉队 BOTTOM5")
    for s in ranked[-5:]:
        L.append(f"- {s['name']}({s['ticker']}) {arrow(s['ret'])}**{s['ret']:+.1f}%** · {'/'.join(s['recs'])}")

    # 推荐人榜
    L.append("\n## 🏆 推荐人胜率榜 TOP10（按均收益）")
    L.append("\n| 推荐人 | 票数 | 平均收益 | 标的 |")
    L.append("|---|---|---|---|")
    for p in d["persons"][:10]:
        picks = " ".join(f"{nm}{r:+.0f}%" for nm, r in p["picks"])
        L.append(f"| {p['person']} | {p['n']} | {p['avg']:+.1f}% | {picks} |")

    # 题材热度
    L.append("\n## 🎯 题材热度（按入选票数）")
    L.append("\n" + " ｜ ".join(f"{s}×{c}" for s, c in d["sectors"][:8]))
    return "\n".join(L)

def main():
    jl = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"data/jielong_2026-06-03.json")
    latest = sys.argv[2] if len(sys.argv) > 2 else "20260605"
    d = run_track(jl, latest)
    md = fmt(d)
    outp = BASE/"output"/f"report_{d['latest']}.md"
    outp.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n\n💾 saved: {outp}")

if __name__ == "__main__":
    main()
