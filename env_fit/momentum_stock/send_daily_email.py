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
    """仅给涨跌幅数字上色：正数红，负数绿，其余不动"""
    def _repl(m):
        val = m.group(0)
        if val.startswith('+') or (val[0].isdigit() and float(val.rstrip('%')) > 0):
            return f'<span style="color:#e85d4a">{val}</span>'
        elif val.startswith('-'):
            return f'<span style="color:#4caf7c">{val}</span>'
        return val
    return _re.sub(r'[+-]?\d+\.?\d*%', _repl, s)


def report_to_html(text, footer):
    lines = text.strip().split('\n')
    html_parts = []
    date_str = ''

    # Bloomberg 三色体系：橙(标题/强调) + 灰(正文) + 红绿(仅涨跌幅)
    C_BG = '#0c0e14'
    C_BORDER = '#1c1f2b'
    C_ACCENT = '#f0a030'       # 橙色 - 标题/章节/强调
    C_BODY = '#9ca3af'         # 灰色 - 所有正文
    C_DIM = '#6b7280'          # 深灰 - 次要信息

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 标题行
        if s.startswith('强势股环境日报'):
            date_str = s.split('|')[-1].strip() if '|' in s else ''
            continue

        # 阶段摘要（加速期，高度3→4板...）
        if '期，' in s and len(s) < 50:
            html_parts.append(
                f'<div style="background:#1a1610;border:1px solid #3d3020;padding:8px 14px;'
                f'font-size:13px;font-weight:700;color:{C_ACCENT};margin:0 0 14px">{s}</div>')
            continue

        # 章节标题（一、二、三...）
        if len(s) > 1 and s[0] in '一二三四五六七' and '、' in s[:3]:
            html_parts.append(
                f'<div style="border-left:3px solid {C_ACCENT};padding:5px 0 5px 10px;'
                f'font-size:13px;font-weight:700;color:{C_ACCENT};'
                f'margin:18px 0 8px">{s}</div>')
            continue

        # 产业链名称行
        if s and s[0] in '■▪●▶':
            html_parts.append(
                f'<div style="background:#12151e;padding:6px 10px;margin:10px 0 3px;'
                f'font-weight:700;font-size:13px;color:{C_ACCENT};'
                f'border-left:2px solid {C_ACCENT}">{_color_pct(s)}</div>')
            continue

        # 传导链
        if '传导:' in s or '传导：' in s:
            content = s.lstrip('- ').lstrip()
            html_parts.append(
                f'<div style="padding:2px 10px 2px 22px;color:{C_DIM};'
                f'font-size:11px">{_color_pct(content)}</div>')
            continue

        # 涨停/跌停主行 - 用灰色正文，数字自带红绿
        if s.startswith('- 涨停') or s.startswith('- 跌停'):
            html_parts.append(
                f'<div style="padding:5px 10px;font-size:13px;font-weight:600;'
                f'color:{C_BODY};margin:3px 0 1px">{_color_pct(s[2:])}</div>')
            continue

        # 方向/强度/额度子行
        if s.startswith('方向:') or s.startswith('强度:') or s.startswith('额度:'):
            html_parts.append(
                f'<div style="padding:1px 10px 1px 24px;font-size:11px;'
                f'color:{C_DIM};line-height:1.6">{_color_pct(s)}</div>')
            continue

        # 其余（产业链汇总）
        if s.startswith('其余'):
            html_parts.append(
                f'<div style="padding:5px 10px;font-size:11px;color:{C_DIM};'
                f'line-height:1.5;border-top:1px solid {C_BORDER};margin-top:6px">{s}</div>')
            continue

        # 百亿涨停股票行
        if s.startswith('- ') and '·' in s:
            stocks = s[2:].split('·')
            tags = ''.join(
                f'<span style="display:inline-block;background:#111318;border:1px solid {C_BORDER};'
                f'padding:2px 6px;margin:1px 2px;font-size:11px;'
                f'color:{C_BODY}">{st.strip()}</span>' for st in stocks if st.strip())
            html_parts.append(f'<div style="padding:1px 10px;line-height:1.9">{tags}</div>')
            continue

        # 龙头池 - 辨识度/成交额龙头
        if '辨识度龙头' in s or '成交额龙头' in s:
            label, val = s.split(':', 1) if ':' in s else (s, '')
            html_parts.append(
                f'<div style="padding:3px 10px 3px 14px;font-size:12px;color:{C_BODY}">'
                f'<span style="color:{C_ACCENT};font-weight:600">{label.lstrip("- ")}:</span> {_color_pct(val)}</div>')
            continue

        # 池内N只
        if '池内' in s and '只' in s:
            content = s.lstrip('- ')
            html_parts.append(
                f'<div style="padding:3px 10px 3px 14px;font-size:11px;color:{C_DIM}">{content}</div>')
            continue

        # 主攻/注意 - 结论强调行
        if s.startswith('- 主攻') or s.startswith('- 注意'):
            html_parts.append(
                f'<div style="padding:3px 10px 3px 14px;font-size:12px;font-weight:600;'
                f'color:{C_ACCENT}">{s[2:]}</div>')
            continue

        # 最强链
        if '最强链' in s or '状态' in s:
            html_parts.append(
                f'<div style="padding:3px 10px 3px 14px;font-size:12px;'
                f'color:{C_BODY}">{_color_pct(s[2:] if s.startswith("- ") else s)}</div>')
            continue

        # 普通 - 开头行
        if s.startswith('- '):
            content = s[2:]
            html_parts.append(
                f'<div style="padding:2px 10px 2px 14px;font-size:12px;'
                f'color:{C_BODY};line-height:1.7">{_color_pct(content)}</div>')
            continue

        # 默认行
        html_parts.append(
            f'<div style="padding:2px 10px;font-size:12px;color:{C_BODY};'
            f'line-height:1.7">{_color_pct(s)}</div>')

    body = '\n'.join(html_parts)
    return f'''<div style="max-width:640px;margin:0 auto;font-family:'SF Mono',Menlo,Consolas,'Courier New',monospace;font-size:12px;color:{C_BODY};background:{C_BG};padding:0">
<div style="background:#000;padding:12px 14px;text-align:center;border-bottom:1px solid {C_BORDER}">
<div style="font-size:16px;font-weight:800;color:{C_ACCENT};letter-spacing:1.5px">GAMT 强势股环境日报</div>
<div style="font-size:11px;color:{C_DIM};margin-top:3px">{date_str}</div>
</div>
<div style="padding:10px 12px">
{body}
</div>
<div style="border-top:1px solid {C_BORDER};padding:8px 12px;text-align:center">
<div style="color:{C_DIM};font-size:10px">{footer}</div>
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
