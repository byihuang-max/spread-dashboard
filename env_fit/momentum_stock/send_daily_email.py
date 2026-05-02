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


import re as _re

def _color_pct(s):
    """仅给涨跌幅数字上色：正数红，负数绿"""
    def _repl(m):
        val = m.group(0)
        if val.startswith('+') or (val[0].isdigit() and float(val.rstrip('%')) > 0):
            return f'<span style="color:#cc2929">{val}</span>'
        elif val.startswith('-'):
            return f'<span style="color:#1a8a4a">{val}</span>'
        return val
    return _re.sub(r'[+-]?\d+\.?\d*%', _repl, s)


def report_to_html(text, footer):
    lines = text.strip().split('\n')
    html_parts = []
    date_str = ''

    # 白底黑字，红绿仅涨跌幅
    C_BG = '#ffffff'
    C_BORDER = '#e5e7eb'
    C_BLACK = '#1a1a1a'
    C_GRAY = '#6b7280'

    for line in lines:
        s = line.strip()
        if not s:
            continue

        if s.startswith('强势股环境日报'):
            date_str = s.split('|')[-1].strip() if '|' in s else ''
            continue

        # 阶段摘要
        if '期，' in s and len(s) < 50:
            html_parts.append(
                f'<div style="border:1px solid {C_BORDER};padding:7px 12px;'
                f'font-size:13px;font-weight:700;color:{C_BLACK};margin:0 0 12px">{s}</div>')
            continue

        # 章节标题
        if len(s) > 1 and s[0] in '一二三四五六七' and '、' in s[:3]:
            html_parts.append(
                f'<div style="border-bottom:1px solid {C_BORDER};padding:4px 0;'
                f'font-size:13px;font-weight:700;color:{C_BLACK};'
                f'margin:16px 0 6px">{s}</div>')
            continue

        # 产业链名称行
        if s and s[0] in '■▪●▶':
            html_parts.append(
                f'<div style="padding:5px 0;margin:8px 0 2px;'
                f'font-weight:700;font-size:13px;color:{C_BLACK}">{_color_pct(s)}</div>')
            continue

        # 传导链
        if '传导:' in s or '传导：' in s:
            content = s.lstrip('- ').lstrip()
            html_parts.append(
                f'<div style="padding:1px 0 1px 18px;color:{C_GRAY};'
                f'font-size:11px">{_color_pct(content)}</div>')
            continue

        # 涨停/跌停主行
        if s.startswith('- 涨停') or s.startswith('- 跌停'):
            html_parts.append(
                f'<div style="padding:4px 0;font-size:13px;font-weight:600;'
                f'color:{C_BLACK}">{_color_pct(s[2:])}</div>')
            continue

        # 方向/强度/额度
        if s.startswith('方向:') or s.startswith('强度:') or s.startswith('额度:'):
            html_parts.append(
                f'<div style="padding:1px 0 1px 16px;font-size:11px;'
                f'color:{C_GRAY};line-height:1.6">{_color_pct(s)}</div>')
            continue

        # 其余
        if s.startswith('其余'):
            html_parts.append(
                f'<div style="padding:4px 0;font-size:11px;color:{C_GRAY};'
                f'line-height:1.5;border-top:1px solid {C_BORDER};margin-top:6px">{s}</div>')
            continue

        # 百亿涨停股票行
        if s.startswith('- ') and '·' in s:
            stocks = s[2:].split('·')
            tags = ''.join(
                f'<span style="display:inline-block;border:1px solid {C_BORDER};'
                f'padding:1px 6px;margin:1px 2px;font-size:11px;'
                f'color:{C_BLACK}">{st.strip()}</span>' for st in stocks if st.strip())
            html_parts.append(f'<div style="padding:1px 0;line-height:1.9">{tags}</div>')
            continue

        # 龙头池
        if '辨识度龙头' in s or '成交额龙头' in s:
            label, val = s.split(':', 1) if ':' in s else (s, '')
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;color:{C_BLACK}">'
                f'<span style="font-weight:600">{label.lstrip("- ")}:</span> {_color_pct(val)}</div>')
            continue

        if '池内' in s and '只' in s:
            content = s.lstrip('- ')
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:11px;color:{C_GRAY}">{content}</div>')
            continue

        # 主攻/注意
        if s.startswith('- 主攻') or s.startswith('- 注意'):
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;font-weight:700;'
                f'color:{C_BLACK}">{s[2:]}</div>')
            continue

        # 状态/最强链
        if '最强链' in s or '状态' in s:
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;'
                f'color:{C_BLACK}">{_color_pct(s[2:] if s.startswith("- ") else s)}</div>')
            continue

        # 普通行
        if s.startswith('- '):
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;'
                f'color:{C_BLACK};line-height:1.7">{_color_pct(s[2:])}</div>')
            continue

        html_parts.append(
            f'<div style="padding:2px 0;font-size:12px;color:{C_BLACK};'
            f'line-height:1.7">{_color_pct(s)}</div>')

    body = '\n'.join(html_parts)
    return f'''<div style="max-width:600px;margin:0 auto;font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:12px;color:{C_BLACK};background:{C_BG};padding:0">
<div style="padding:14px 16px;text-align:center;border-bottom:2px solid {C_BLACK}">
<div style="font-size:15px;font-weight:800;color:{C_BLACK};letter-spacing:1px">GAMT 强势股环境日报</div>
<div style="font-size:11px;color:{C_GRAY};margin-top:2px">{date_str}</div>
</div>
<div style="padding:10px 16px">
{body}
</div>
<div style="border-top:1px solid {C_BORDER};padding:8px 16px;text-align:center">
<div style="color:{C_GRAY};font-size:10px">{footer}</div>
</div>
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
    subject = f'GAMT {settings["subject_prefix"]} | {date_str}'
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
