#!/usr/bin/env python3
"""强势股环境日报 → 飞书消息卡片发送"""
import requests, json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from momentum_daily_report import generate_report

APP_ID = 'cli_a91c36caf5785cb2'
APP_SECRET = 'HWhYR833N0xObKumrjNCKdRSHq3jg0zi'
CHAT_ID = 'oc_1e941df394190b21d4c4edd83deae4f3'


def get_token():
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': APP_ID, 'app_secret': APP_SECRET}
    )
    return resp.json().get('tenant_access_token')


def build_card(report_text):
    lines = report_text.split('\n')
    elements = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('强势股环境日报'):
            continue

        if '期，' in s and ('板' in s or '共振' in s or '分化' in s or '全跌' in s or '偏' in s or '震荡' in s):
            elements.append({"tag": "markdown", "content": f"*{s}*"})
            elements.append({"tag": "hr"})
            continue

        if len(s) > 1 and s[0] in '一二三四五六七' and '、' in s[:3]:
            elements.append({"tag": "markdown", "content": f"**{s}**"})
            continue

        if s.startswith('- '):
            elements.append({"tag": "markdown", "content": s})
            continue

        if s and s[0] in '①②③':
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": f"**{s}**"})
            continue

        if s.startswith('其余:') or s.startswith('其余：'):
            elements.append({"tag": "markdown", "content": f"*{s}*"})
            continue

        if '传导:' in s:
            elements.append({"tag": "markdown", "content": f"*{s.replace('- ', '')}*"})
            continue

        elements.append({"tag": "markdown", "content": s})

    date_str = lines[0].split('|')[-1].strip() if '|' in lines[0] else ''

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"强势股环境日报 | {date_str}"},
            "template": "indigo"
        },
        "elements": elements
    }


def send_card(card, token):
    resp = requests.post(
        'https://open.feishu.cn/open-apis/im/v1/messages',
        params={'receive_id_type': 'chat_id'},
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={
            'receive_id': CHAT_ID,
            'msg_type': 'interactive',
            'content': json.dumps(card)
        }
    )
    return resp.json()


def main():
    print('生成日报...')
    report = generate_report()
    print('构建卡片...')
    card = build_card(report)
    print('获取 token...')
    token = get_token()
    print('发送卡片...')
    result = send_card(card, token)
    if result.get('code') == 0:
        print('✅ 日报卡片发送成功')
    else:
        print(f'❌ 发送失败: {result.get("msg")}')
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
