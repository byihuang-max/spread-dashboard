#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

FEISHU_APP_ID = "cli_a91c36caf5785cb2"
FEISHU_APP_SECRET = "HWhYR833N0xObKumrjNCKdRSHq3jg0zi"
# 这里必须使用当前飞书应用下实际可用的 open_id；现有 narrative_monitor.py 仍在用旧 open_id 并可正常发送
RONI_OPEN_ID = "ou_4f9c4d14f2e27f4863a5e2743dba3482"

CANDIDATES = [
    Path.home() / "Desktop" / "quant-backtest" / "timing_model",
    Path.home() / "quant-backtest" / "timing_model",
]


def resolve_timing_root() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(f"timing_model not found: {CANDIDATES}")


def get_latest_two_dates(cache_dir: Path) -> tuple[str, str]:
    dates = sorted(
        p.stem for p in cache_dir.glob("*.json")
        if p.stem.isdigit() and len(p.stem) == 8
    )
    if len(dates) < 2:
        raise RuntimeError(f"缓存不足两天: {dates}")
    return dates[-1], dates[-2]


def get_feishu_token() -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"get token failed: {data}")
    return data["tenant_access_token"]


def build_summary(report: dict) -> str:
    b = report["board_structure"]
    high = report["high_level_watch"]
    ch = report["industry_focus"]["change"]

    parts = []
    delta = b["up_count_change"]
    if delta <= -20:
        parts.append("涨停大幅缩量")
    elif delta <= -8:
        parts.append("涨停收缩")
    elif delta >= 20:
        parts.append("涨停大幅扩张")
    elif delta >= 8:
        parts.append("涨停扩张")
    else:
        parts.append("涨停持平")

    mb_delta = b["max_board_change"]
    if mb_delta <= -3:
        parts.append("高度断崖回落")
    elif mb_delta <= -1:
        parts.append("高度降低")
    elif mb_delta >= 2:
        parts.append("高度抬升")

    if high:
        broke = sum(1 for h in high if "断板" in h["today_status"])
        total = len(high)
        if broke == total and total >= 2:
            parts.append("高位全部断板")
        elif broke >= max(1, total * 0.5):
            parts.append("高位多数断板")
        elif broke == 0:
            parts.append("高位全部封住")

    if ch["change_type"] == "切换":
        parts.append("方向切换")
    elif ch["change_type"] == "分化":
        parts.append("方向分化")
    else:
        cont = ch.get("continued", [])
        if cont:
            parts.append(f"{'、'.join(cont[:2])}方向延续")

    return "，".join(parts) + "。"


def build_card(report: dict, replay_url: str) -> dict:
    b = report["board_structure"]
    high = report["high_level_watch"]
    lf = report["leader_follow"]
    ind = report["industry_focus"]
    td = b["today_distribution"]
    dd = b["distribution_change"]
    now = datetime.now().strftime("%m-%d %H:%M")

    high_text = "\n".join(
        f"- {x['name']}：{x['today_status']}" for x in high[:4]
    ) or "- 昨日无 3 板及以上高位票"

    follow_text = "\n".join(
        f"- {x['name']}：{x['today_status']} / {'仍在吐池' if x['still_in_pool'] else '退出吐池'}"
        for x in lf["follow"][:5]
    ) or "- 昨日无吐池样本"

    today_dirs = "、".join(
        f"{x['industry']}({x['count']}家/最高{x['max_board']}板)" for x in ind["today_top"][:5]
    ) or "无"
    change = ind["change"]
    change_line = f"{change['change_type']}"
    if change.get("continued"):
        change_line += f"｜延续：{'、'.join(change['continued'][:3])}"
    if change.get("new"):
        change_line += f"｜新出现：{'、'.join(change['new'][:3])}"
    if change.get("faded"):
        change_line += f"｜淡出：{'、'.join(change['faded'][:3])}"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📈 盘中涨停因子 · 盘后复盘** {report['trade_date']} vs {report['prev_date']}｜{now}"
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"> {build_summary(report)}"
            }
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    "**一、板位结构变化**\n"
                    f"- 涨停 {b['today_up_count']} 家（较昨日 {b['up_count_change']:+d}）\n"
                    f"- 跌停 {b['today_down_count']} 家，炸板 {b['today_zha_count']} 家\n"
                    f"- 最高板 {b['max_board_today']}（较昨日 {b['max_board_change']:+d}）\n"
                    f"- 首板 {td['1']}（{dd['1']:+d}）/ 二板 {td['2']}（{dd['2']:+d}）/ 三板 {td['3']}（{dd['3']:+d}）"
                )
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**二、高位票跟踪**\n{high_text}"
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**三、昨日龙头今日表现**\n{follow_text}"
            }
        },
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**四、核心方向变化**\n- 今日前五方向：{today_dirs}\n- 方向判断：{change_line}"
            }
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "打开盘后复盘页"},
                    "type": "primary",
                    "url": replay_url,
                }
            ]
        },
    ]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📈 盘中涨停因子 · 盘后复盘"},
            "template": "turquoise",
        },
        "elements": elements,
    }


def send_card(card: dict) -> dict:
    token = get_feishu_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "receive_id": RONI_OPEN_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        params={"receive_id_type": "open_id"},
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"feishu send failed: status={resp.status_code} body={resp.text}")
    return resp.json()


def main() -> None:
    timing_root = resolve_timing_root()
    sys.path.insert(0, str(timing_root / "narrative"))
    from narrative_engine import build_report  # pylint: disable=import-outside-toplevel

    gamt_candidates = [
        Path.home() / "Desktop" / "gamt-dashboard",
        Path.home() / "gamt-dashboard",
    ]
    gamt_root = next((p for p in gamt_candidates if (p / "env_fit" / "momentum_stock" / "_cache").exists()), gamt_candidates[0])
    today, prev = get_latest_two_dates(gamt_root / "env_fit" / "momentum_stock" / "_cache")
    report = build_report(today, prev)
    card = build_card(report, "https://dashboard.gamtfof.com/timing-research/intraday_limit_replay.html")
    result = send_card(card)
    print(json.dumps({"trade_date": today, "prev_date": prev, "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
