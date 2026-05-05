#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每月 1 号给 Roni 推一张飞书卡片，提醒开代理推 GitHub 备份。
部署位置：腾讯云 cron，每月 1 号早上 09:00。
"""
import json
import requests
from datetime import datetime

FEISHU_APP_ID = "cli_a91c36caf5785cb2"
FEISHU_APP_SECRET = "HWhYR833N0xObKumrjNCKdRSHq3jg0zi"
RONI_OPEN_ID = "ou_4f9c4d14f2e27f4863a5e2743dba3482"


def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    return r.json()["tenant_access_token"]


def build_card():
    month = datetime.now().strftime("%Y年%m月")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📦 GitHub 月度备份提醒"},
            "template": "violet",
        },
        "elements": [
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": f"**{month}** 的 GitHub 备份时间到。\n\nGitee 是主链，GitHub 是异地备份（代理访问）。本月记得抽空推一次，防单点。",
            }},
            {"tag": "hr"},
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": "**操作方式：** 打开代理（Clash/VPN 端口 7897），在终端执行：\n```bash\nbash ~/Desktop/gamt-dashboard/scripts/push_github.sh\n```\n脚本会自动检测代理、对齐 Gitee、推送 GitHub。",
            }},
            {"tag": "div", "text": {
                "tag": "lark_md",
                "content": "_本月有空再推就行，不急。_",
            }},
        ],
    }


def main():
    token = get_token()
    r = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        params={"receive_id_type": "open_id"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": RONI_OPEN_ID,
            "msg_type": "interactive",
            "content": json.dumps(build_card()),
        },
    )
    print(f"[{datetime.now()}] 飞书推送: {r.json()}")


if __name__ == "__main__":
    main()
