#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书卡片推送：把 track.py 的 JSON 输出渲染成飞书 interactive card 并发送。
用法: /opt/homebrew/bin/python3 feishu_card.py [接龙json] [最新日YYYYMMDD] [chat_id]
凭证从 ~/.hermes/profiles/leijun/.env 读取。
"""
from __future__ import annotations
import json, sys, subprocess, urllib.request, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent
PY = "/opt/homebrew/bin/python3"
ENV = Path("/Users/apple/.hermes/profiles/leijun/.env")
DEFAULT_CHAT = "oc_37010c57554d7a88ee06ab4567bbd35a"

def load_env():
    d = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d

def http_post(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def get_token(env):
    r = http_post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
                  {"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
                  {"Content-Type": "application/json"})
    if r.get("code") != 0:
        raise RuntimeError(f"token error: {r}")
    return r["tenant_access_token"]

def run_track(jl_file, latest):
    out = subprocess.check_output([PY, str(BASE/"track.py"), jl_file, latest],
                                  stderr=subprocess.DEVNULL, text=True)
    return json.loads(out[out.index("{"):])

def color(x):
    if x >= 9.9: return "red"
    if x > 0: return "carmine"
    if x == 0: return "grey"
    return "green"

def tag(x):
    # 飞书里红涨绿跌
    if x >= 9.9: return f"🔴 {x:+.1f}%"
    if x > 0: return f"🔺 {x:+.1f}%"
    if x == 0: return f"⚪ {x:+.1f}%"
    return f"🟢 {x:+.1f}%"

def build_card(d):
    elements = []
    # 概览
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md",
                 "content": f"**沪深300同期** {d['hs300_ret']:+.2f}%　|　**有效标的** {d['n_valid']}支"}
    })
    elements.append({"tag": "hr"})

    # 共识榜
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🔥 共识榜（被多人推荐）**"}})
    consensus = [s for s in d["stocks"] if s["consensus"] >= 2]
    for s in consensus:
        elements.append({
            "tag": "div",
            "fields": [
                {"is_short": True, "text": {"tag": "lark_md",
                 "content": f"**{s['name']}** `{s['ticker']}`\n{s['sector']}"}},
                {"is_short": True, "text": {"tag": "lark_md",
                 "content": f"{s['consensus']}人共识　{tag(s['ret'])}\n超额 {s['excess']:+.1f}%"}},
            ]
        })
    elements.append({"tag": "hr"})

    # 领涨
    ranked = sorted(d["stocks"], key=lambda x: -x["ret"])
    top = "\n".join(f"{tag(s['ret'])}　**{s['name']}**({s['ticker']})　·{'/'.join(s['recs'])}" for s in ranked[:5])
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🚀 区间领涨 TOP5**\n{top}"}})
    bot = "\n".join(f"{tag(s['ret'])}　**{s['name']}**({s['ticker']})　·{'/'.join(s['recs'])}" for s in ranked[-5:])
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🔻 区间掉队 BOTTOM5**\n{bot}"}})
    elements.append({"tag": "hr"})

    # 推荐人榜
    persons = "\n".join(
        f"**{i+1}. {p['person']}**　均{p['avg']:+.1f}%　({p['n']}票)\n　{'  '.join(f'{nm}{r:+.0f}%' for nm,r in p['picks'])}"
        for i, p in enumerate(d["persons"][:8]))
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🏆 推荐人胜率榜 TOP8**\n{persons}"}})
    elements.append({"tag": "hr"})

    # 题材热度
    sectors = "　".join(f"`{s}×{c}`" for s, c in d["sectors"][:8])
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🎯 题材热度**\n{sectors}"}})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": f"📊 接龙跟踪  基准{d['base_date']} → {d['latest']}"}
        },
        "elements": elements,
    }

def send_card(token, chat_id, card):
    r = http_post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                  {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)},
                  {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return r

def main():
    jl = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"data/jielong_2026-06-03.json")
    latest = sys.argv[2] if len(sys.argv) > 2 else "20260605"
    chat = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_CHAT
    env = load_env()
    token = get_token(env)
    d = run_track(jl, latest)
    card = build_card(d)
    r = send_card(token, chat, card)
    print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()
