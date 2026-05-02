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
    """给涨跌幅数字上色：正数红，负数绿"""
    def _repl(m):
        val = m.group(0)
        if val.startswith('+') or (val[0].isdigit() and float(val.rstrip('%')) > 0):
            return f'<span style="color:#ff4d4f">{val}</span>'
        elif val.startswith('-'):
            return f'<span style="color:#52c41a">{val}</span>'
        return val
    return _re.sub(r'[+-]?\d+\.?\d*%', _repl, s)


def report_to_html(text, footer):
    lines = text.strip().split('\n')
    html_parts = []
    date_str = ''
    in_section = ''

    # 样式常量
    C_BG = '#0a0e17'
    C_CARD = '#111827'
    C_BORDER = '#1e293b'
    C_TEXT = '#e2e8f0'
    C_MUTED = '#64748b'
    C_ACCENT = '#f59e0b'
    C_RED = '#ff4d4f'
    C_GREEN = '#52c41a'
    C_BLUE = '#60a5fa'

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 标题行
        if s.startswith('强势股环境日报'):
            date_str = s.split('|')[-1].strip() if '|' in s else ''
            continue

        # 阶段摘要行（加速期，高度3→4板...）
        if '期，' in s and len(s) < 50:
            html_parts.append(
                f'<div style="background:{C_ACCENT};color:#000;padding:8px 14px;'
                f'font-size:14px;font-weight:700;margin:0 0 16px;letter-spacing:0.5px">'
                f'{s}</div>')
            continue

        # 章节标题（一、二、三...）
        if len(s) > 1 and s[0] in '一二三四五六七' and '、' in s[:3]:
            in_section = s
            html_parts.append(
                f'<div style="border-left:3px solid {C_ACCENT};padding:6px 0 6px 12px;'
                f'font-size:15px;font-weight:700;color:{C_ACCENT};'
                f'margin:20px 0 10px;letter-spacing:0.5px">{s}</div>')
            continue

        # 产业链名称行（■ 科技 +1.50%...）
        if s and s[0] in '■▪●▶':
            html_parts.append(
                f'<div style="background:#1a2332;padding:8px 12px;margin:12px 0 4px;'
                f'font-weight:700;font-size:14px;color:{C_TEXT};'
                f'border-left:3px solid {C_BLUE}">{_color_pct(s)}</div>')
            continue

        # 传导链
        if '传导:' in s or '传导：' in s:
            content = s.lstrip('- ').lstrip()
            html_parts.append(
                f'<div style="padding:4px 12px 4px 24px;color:{C_BLUE};'
                f'font-size:12px;font-style:italic">{_color_pct(content)}</div>')
            continue

        # 涨停/跌停主行
        if s.startswith('- 涨停') or s.startswith('- 跌停'):
            is_up = '涨停' in s[:6]
            color = C_RED if is_up else C_GREEN
            html_parts.append(
                f'<div style="padding:6px 12px;font-size:14px;font-weight:600;'
                f'color:{color};margin:4px 0 2px">{s[2:]}</div>')
            continue

        # 方向/强度/额度子行（缩进灰色小字）
        if s.startswith('方向:') or s.startswith('强度:') or s.startswith('额度:'):
            html_parts.append(
                f'<div style="padding:2px 12px 2px 28px;font-size:12px;'
                f'color:{C_MUTED};line-height:1.6">{_color_pct(s)}</div>')
            continue

        # 其余行（产业链汇总）
        if s.startswith('其余'):
            html_parts.append(
                f'<div style="padding:6px 12px;font-size:12px;color:{C_MUTED};'
                f'line-height:1.6;border-top:1px solid {C_BORDER};margin-top:8px">{s}</div>')
            continue

        # 百亿涨停股票行
        if s.startswith('- ') and '·' in s:
            stocks = s[2:].split('·')
            tags = ''.join(
                f'<span style="display:inline-block;background:#1a1a2e;border:1px solid #2d2d44;'
                f'padding:2px 8px;margin:2px 3px;border-radius:3px;font-size:12px;'
                f'color:{C_TEXT}">{st.strip()}</span>' for st in stocks if st.strip())
            html_parts.append(f'<div style="padding:2px 12px;line-height:2">{tags}</div>')
            continue

        # 普通 - 开头行
        if s.startswith('- '):
            content = s[2:]
            # 上游→中游→下游链
            if '上游' in content or '中游' in content or '下游' in content:
                html_parts.append(
                    f'<div style="padding:4px 12px 4px 16px;font-size:12px;'
                    f'color:{C_TEXT};line-height:1.8">{_color_pct(content)}</div>')
            else:
                html_parts.append(
                    f'<div style="padding:3px 12px 3px 16px;font-size:13px;'
                    f'color:{C_TEXT};line-height:1.7">{_color_pct(content)}</div>')
            continue

        # 龙头池行
        if '辨识度龙头' in s or '成交额龙头' in s:
            label, val = s.split(':', 1) if ':' in s else (s, '')
            color = C_ACCENT if '辨识度' in s else C_BLUE
            html_parts.append(
                f'<div style="padding:4px 12px 4px 16px;font-size:13px;color:{C_TEXT}">'
                f'<span style="color:{color};font-weight:600">{label.lstrip("- ")}:</span>{_color_pct(val)}</div>')
            continue

        if '池内' in s and '只' in s:
            content = s.lstrip('- ')
            html_parts.append(
                f'<div style="padding:4px 12px 4px 16px;font-size:12px;color:{C_MUTED}">{content}</div>')
            continue

        # 结论区关键行
        if '最强链' in s or '状态' in s:
            html_parts.append(
                f'<div style="padding:4px 12px;font-size:13px;font-weight:600;'
                f'color:{C_ACCENT}">{s}</div>')
            continue

        # 默认行
        html_parts.append(
            f'<div style="padding:3px 12px;font-size:13px;color:{C_TEXT};'
            f'line-height:1.7">{_color_pct(s)}</div>')

    body = '\n'.join(html_parts)
    return f'''<div style="max-width:640px;margin:0 auto;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:13px;color:{C_TEXT};background:{C_BG};padding:0">
<div style="background:#000;padding:14px 16px;text-align:center">
<div style="font-size:18px;font-weight:800;color:{C_ACCENT};letter-spacing:1px">GAMT 强势股环境日报</div>
<div style="font-size:12px;color:{C_MUTED};margin-top:4px">{date_str}</div>
</div>
<div style="padding:12px 16px">
{body}
</div>
<div style="border-top:1px solid {C_BORDER};padding:10px 16px;text-align:center">
<div style="color:{C_MUTED};font-size:11px">{footer}</div>
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
