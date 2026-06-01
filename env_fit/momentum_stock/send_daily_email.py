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


def _highlight_red(s):
    """将 <<text>> 标记转为红色加粗"""
    return _re.sub(r'<<(.+?)>>', r'<span style="color:#cc2929;font-weight:700">\1</span>', s)


def _gray_explain(s):
    """将 ((text)) 标记转为灰色小字"""
    return _re.sub(r'\(\((.+?)\)\)', r'<span style="color:#6b7280;font-size:10px;font-weight:400"> \1</span>', s)


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

        # 模块小字描述（紧跟章节标题的一行说明）
        _subtitles = {'整体市场强势方向与温度', '市场核心聚焦方向',
                      '成交额加权强度 + 上下游传导验证',
                      '高度 + 成交聚焦的核心票筛选',
                      '基于当日最强链与龙头方向',
                      '综合产业链强度、百亿涨停与龙头方向',
                      '跟随当日最强细分方向'}
        if s in _subtitles:
            html_parts.append(
                f'<div style="font-size:10px;color:{C_GRAY};'
                f'margin:-4px 0 6px;padding:0">{s}</div>')
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

        # 涨停/跌停/封单轧差 主行（同级粗体）
        if s.startswith('- 涨停') or s.startswith('- 跌停') or s.startswith('- 封单轧差'):
            html_parts.append(
                f'<div style="padding:4px 0;font-size:13px;font-weight:600;'
                f'color:{C_BLACK}">{_color_pct(s[2:])}</div>')
            continue

        # 涨停下挂的子指标（小灰字缩进）：方向/强度/额度（一级缩进）
        _sub_l1 = ('方向:', '强度:', '额度:')
        if any(s.startswith(kw) for kw in _sub_l1):
            html_parts.append(
                f'<div style="padding:1px 0 1px 16px;font-size:11px;'
                f'color:{C_GRAY};line-height:1.6">{_color_pct(s)}</div>')
            continue

        # 次级标题（>> 开头）：首板/晋级率/1进2/炸板率
        if s.startswith('>> '):
            content = s[3:]
            html_parts.append(
                f'<div style="padding:3px 0 1px 16px;font-size:12px;'
                f'font-weight:600;color:{C_BLACK};margin-top:4px">{_color_pct(content)}</div>')
            continue

        # 次级标题的方向行（深缩进）
        _sub_l2 = ('首板方向:', '晋级方向:', '1进2方向:', '炸板方向:')
        if any(s.startswith(kw) for kw in _sub_l2):
            html_parts.append(
                f'<div style="padding:1px 0 1px 28px;font-size:10px;'
                f'color:{C_GRAY};line-height:1.5">{_color_pct(s)}</div>')
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
            val = _highlight_red(_color_pct(val))
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;color:{C_BLACK}">'
                f'<span style="font-weight:600">{label.lstrip("- ")}:</span> {val}</div>')
            continue

        if '池内' in s and '只' in s:
            content = s.lstrip('- ')
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:11px;color:{C_GRAY}">{content}</div>')
            continue

        # 龙头池变动
        if s.startswith('- 变动:') or s.startswith('- 变动：'):
            content = s.lstrip('- ')
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:11px;color:{C_GRAY};'
                f'line-height:1.6">{content}</div>')
            continue

        # 主攻/注意（主攻+注意标红，括号内解释灰色小字）
        if s.startswith('- <<主攻') or s.startswith('- <<注意') or s.startswith('- 主攻') or s.startswith('- 注意'):
            content = _gray_explain(_highlight_red(s[2:]))
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;font-weight:700;'
                f'color:{C_BLACK}">{content}</div>')
            continue

        # ETF 缩进行
        if s.startswith('etf:'):
            html_parts.append(
                f'<div style="padding:1px 0 1px 20px;font-size:10px;'
                f'color:{C_GRAY};line-height:1.5">{_color_pct(s)}</div>')
            continue

        # 状态/最强链/最强链切换/连续
        if '最强链' in s or '状态' in s:
            content = _gray_explain(_color_pct(s[2:] if s.startswith("- ") else s))
            html_parts.append(
                f'<div style="padding:2px 0 2px 8px;font-size:12px;'
                f'color:{C_BLACK}">{content}</div>')
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


def is_trading_day(dt=None):
    """判断指定日期是否为 A 股交易日（Tushare trade_cal）"""
    from momentum_data import tushare_call
    from datetime import date as _date
    d = dt or _date.today()
    ds = d.strftime('%Y%m%d')
    try:
        data = tushare_call('trade_cal', {
            'exchange': 'SSE', 'start_date': ds, 'end_date': ds
        })
        if data and len(data) > 0:
            return data[0].get('is_open') == 1
    except Exception as e:
        print(f'  交易日判断失败({e})，默认放行')
    return True  # 查询失败时不阻断


def check_data_freshness():
    """检查情绪数据是否足够新，防止发过期日报"""
    import json
    from datetime import date as _date, timedelta
    sent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'momentum_sentiment.json')
    try:
        with open(sent_path) as f:
            data = json.load(f)
        latest_date = data['daily'][-1]['date']
        today = _date.today()
        latest_dt = _date(int(latest_date[:4]), int(latest_date[4:6]), int(latest_date[6:8]))
        gap = (today - latest_dt).days
        if gap > 3:
            print(f'⚠ 数据过期: 最新 {latest_date}，距今 {gap} 天（>3天），跳过发送')
            return False
        # 如果今天是交易日，数据应该是今天的
        today_str = today.strftime('%Y%m%d')
        if latest_date != today_str and is_trading_day():
            print(f'⚠ 数据未更新到今天: 最新 {latest_date}，今天 {today_str}，跳过发送')
            return False
    except Exception as e:
        print(f'⚠ 数据新鲜度检查异常({e})，放行')
    return True


def main():
    # --force 跳过交易日判断（手动补发用）
    if '--force' not in sys.argv and '--test' not in sys.argv:
        if not is_trading_day():
            print('今日非交易日，跳过发送')
            return
        if not check_data_freshness():
            return

    print('生成日报...')
    report = generate_report()
    send_to_all(report)


if __name__ == '__main__':
    main()
