#!/usr/bin/env python3
"""强势股环境日报 → 邮件群发（配置化）

客户管理：编辑 email_subscribers.json，加一行 {"email": "xxx", "name": "xxx", "enabled": true} 即可
"""
import smtplib, os, sys, json, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from momentum_daily_report import generate_report

CONFIG_PATH = os.path.join(BASE, 'email_subscribers.json')


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def active_subscribers(cfg):
    return [s for s in cfg['subscribers'] if s.get('enabled', True)]


def report_to_html(text, footer):
    lines = text.strip().split('\n')
    html_parts = []
    date_str = ''
    for line in lines:
        s = line.strip()
        if not s:
            html_parts.append('<br>')
            continue
        if s.startswith('强势股环境日报'):
            date_str = s.split('|')[-1].strip() if '|' in s else ''
            continue
        if '期，' in s and len(s) < 40:
            html_parts.append(f'<div style="background:#4f46e5;color:#fff;padding:8px 12px;border-radius:6px;font-size:15px;margin:8px 0">{s}</div>')
            continue
        if len(s) > 1 and s[0] in '一二三四五六七' and '、' in s[:3]:
            html_parts.append(f'<h3 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:4px;margin:16px 0 8px">{s}</h3>')
            continue
        if s and s[0] in '':
            html_parts.append(f'<div style="font-weight:bold;color:#4f46e5;margin:12px 0 4px">{s}</div>')
            continue
        if s.startswith('- '):
            html_parts.append(f'<div style="padding-left:16px;line-height:1.8">{s}</div>')
            continue
        if s.startswith('其余'):
            html_parts.append(f'<div style="color:#64748b;font-size:13px;margin:4px 0">{s}</div>')
            continue
        if '传导:' in s or '传导：' in s:
            html_parts.append(f'<div style="color:#6366f1;padding-left:24px;font-style:italic">{s.lstrip("- ")}</div>')
            continue
        html_parts.append(f'<div style="line-height:1.8">{s}</div>')

    body = '\n'.join(html_parts)
    return f'''<div style="max-width:640px;margin:0 auto;font-family:-apple-system,sans-serif;font-size:14px;color:#1e293b;padding:16px">
<h2 style="text-align:center;color:#4f46e5">强势股环境日报 | {date_str}</h2>
{body}
<hr style="margin-top:24px;border:none;border-top:1px solid #e2e8f0">
<div style="text-align:center;color:#94a3b8;font-size:12px">{footer}</div>
</div>''', date_str


def send_to_all(report_text):
    cfg = load_config()
    sender_cfg = cfg['sender']
    settings = cfg['settings']
    subs = active_subscribers(cfg)

    if not subs:
        print('⚠ 无活跃订阅者')
        return

    html_body, date_str = report_to_html(report_text, settings.get('footer', ''))
    subject = f'{settings["subject_prefix"]} | {date_str}'
    max_retry = settings.get('max_retry', 2)

    print(f' 准备发送给 {len(subs)} 位订阅者...')

    with smtplib.SMTP_SSL(sender_cfg['smtp_host'], sender_cfg['smtp_port']) as server:
        server.login(sender_cfg['email'], sender_cfg['auth_code'])

        for sub in subs:
            email = sub['email']
            name = sub.get('name', email)
            ok = False
            for attempt in range(1, max_retry + 1):
                try:
                    msg = MIMEMultipart('alternative')
                    msg['From'] = sender_cfg['email']
                    msg['To'] = email
                    msg['Subject'] = subject
                    msg.attach(MIMEText(report_text, 'plain', 'utf-8'))
                    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
                    server.sendmail(sender_cfg['email'], [email], msg.as_string())
                    print(f'   {name} <{email}>')
                    ok = True
                    break
                except Exception as e:
                    print(f'  ⚠ {name} 第{attempt}次失败: {e}')
                    time.sleep(2)
            if not ok:
                print(f'   {name} <{email}> 发送失败')

    print(f' 发送完毕')


def main():
    print('生成日报...')
    report = generate_report()
    send_to_all(report)


if __name__ == '__main__':
    main()
