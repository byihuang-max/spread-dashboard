#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 score.py 输出渲染成飞书卡片发送"""
from __future__ import annotations
import json, sys, subprocess, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
PY = "/opt/homebrew/bin/python3"
ENV = Path("/Users/apple/.hermes/profiles/leijun/.env")
DEFAULT_CHAT = "oc_37010c57554d7a88ee06ab4567bbd35a"

def load_env():
    d = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d

def http_post(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get_token(env):
    r = http_post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
                  {"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
                  {"Content-Type": "application/json"})
    return r["tenant_access_token"]

def run_score(jl_file, end_date):
    out = subprocess.check_output([PY, str(BASE/"score.py"), jl_file, end_date],
                                  stderr=subprocess.DEVNULL, text=True)
    return json.loads(out[out.index("{"):])

def medal(i):
    return ["🥇","🥈","🥉"][i] if i < 3 else f"{i+1}."

def tag(x):
    if x >= 9.9: return f"🔴{x:+.1f}%"
    if x > 0: return f"🔺{x:+.1f}%"
    if x == 0: return f"⚪0%"
    return f"🟢{x:+.1f}%"

def chan_emoji(r):
    """缠论多级别信号的紧凑标记"""
    parts = []
    sig = r.get("small_signal")
    div = r.get("mid_div")
    if sig and "买" in sig: parts.append("🟢买")
    elif sig and "卖" in sig: parts.append("🔴卖")
    if div == "bot": parts.append("底背驰")
    elif div == "top": parts.append("⚠顶背驰")
    pos = r.get("mid_pos")
    if pos == "中枢上方(强)": parts.append("枢上")
    elif pos == "中枢下方(弱)": parts.append("枢下")
    elif pos == "中枢内(震荡)": parts.append("枢内")
    return " ".join(parts) if parts else "—"

def fmt_group(title, items, elements):
    if not items: return
    lines = [f"**{title}**"]
    for x in items:
        con = f"{'★'*min(x['consensus'],5)}" if x["consensus"] else ""
        chan = chan_emoji(x)
        lines.append(
            f"{medal(x['rank']-1)} **{x['name']}** `{x['ticker']}`　"
            f"{tag(x['ret20'])}20日 {tag(x['ret5'])}5日　{con}\n"
            f"　└ 缠论: {chan}　_{x['sector']}_"
        )
    elements.append({"tag":"div","text":{"tag":"lark_md","content":"\n".join(lines)}})
    elements.append({"tag":"hr"})

def build_card(d):
    e = d["env"]
    r = d["ranking"]
    env_color = "green" if e["coef"] > 0.55 else ("red" if e["coef"] < 0.45 else "yellow")
    elements = []

    # 环境判断
    elements.append({"tag":"div","text":{"tag":"lark_md","content":
        f"**风格环境** `{e['verdict']}`　系数 **{e['coef']}**\n"
        f"小市值5日 `{e['sml5']:+.3f}`　动量5日 `{e['mom5']:+.3f}`　高波5日 `{e['rv5']:+.3f}`"}})
    elements.append({"tag":"hr"})

    # 全排名
    elements.append({"tag":"div","text":{"tag":"lark_md","content":"**📋 全排名（量价×Barra×缠论×共识四层合成）**"}})

    strong  = [x for x in r if x["score"] >  0.10]
    neutral = [x for x in r if -0.10 <= x["score"] <= 0.10]
    weak    = [x for x in r if x["score"] < -0.10]

    fmt_group("🟢 强势区（综合分 >0.1）", strong, elements)
    fmt_group("⚪ 中性区", neutral, elements)
    fmt_group("🔴 弱势区（综合分 <-0.1）", weak, elements)

    # 题材情绪
    sec_lines = ["**🎯 题材情绪排名**"]
    for s in d["sector_mood"][:10]:
        bar = "█" * min(int(abs(s["avg_ret20"])/10)+1, 8)
        sign = "+" if s["avg_ret20"] >= 0 else ""
        sec_lines.append(f"`{s['sector']}` {sign}{s['avg_ret20']:.1f}% {bar} ({s['n']}票)")
    elements.append({"tag":"div","text":{"tag":"lark_md","content":"\n".join(sec_lines)}})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": env_color,
                   "title": {"tag":"plain_text","content":f"🧮 多因子全排名  {d['end_date']}  回看{d['lookback']}日"}},
        "elements": elements
    }

def send_card(token, chat_id, card):
    return http_post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        {"receive_id": chat_id, "msg_type": "interactive",
         "content": json.dumps(card, ensure_ascii=False)},
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})

def main():
    jl   = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"data/jielong_2026-06-03.json")
    date = sys.argv[2] if len(sys.argv) > 2 else "20260605"
    chat = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_CHAT
    env  = load_env()
    tok  = get_token(env)
    d    = run_score(jl, date)
    card = build_card(d)
    r    = send_card(tok, chat, card)
    print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()
