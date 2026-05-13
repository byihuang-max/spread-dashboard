#!/usr/bin/env python3
"""通用邮件发送脚本 - 支持多场景订阅

用法:
    python3 send_email.py --scene a_stock_momentum
    python3 send_email.py --scene hk_stock_momentum
    python3 send_email.py --scene a_stock_momentum --force
    python3 send_email.py --scene a_stock_momentum --test   # 只发给 Roni
"""
import smtplib, os, sys, json, time, argparse, importlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date as _date

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
CONFIG_PATH = os.path.join(BASE, 'email_subscribers.json')

# ─── 场景注册表 ───
SCENES = {
    'a_stock_momentum': {
        'name': 'A股强势股日报',
        'subject_prefix': '强势股环境日报',
        'module': 'momentum_daily_report',
        'func': 'generate_report',
        'exchange': 'SSE',  # 交易日判断用
    },
    'hk_stock_momentum': {
        'name': '港股强势股日报',
        'subject_prefix': '港股强势股日报',
        'module': 'hk_momentum_report',
        'func': 'generate_report',
        'exchange': 'HKEX',
    },
    'us_stock_momentum': {
        'name': '美股异动日报',
        'subject_prefix': '美股异动日报',
        'module': 'us_momentum_report',
        'func': 'generate_report',
        'exchange': 'NASDAQ',
    },
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def active_subscribers(cfg, scene_key):
    """获取订阅了指定场景的活跃用户"""
    subs = []
    for s in cfg['subscribers']:
        if s.get('status') != 'active':
            continue
        # 兼容旧格式（无 subscriptions 字段 → 默认只订阅 A股）
        subscriptions = s.get('subscriptions', {'a_stock_momentum': True})
        if subscriptions.get(scene_key, False):
            subs.append(s)
    return subs


def is_trading_day(exchange='SSE'):
    """判断今天是否为交易日"""
    if exchange == 'HKEX':
        # 港股：周一到周五（简化判断，不含港股特殊假期）
        return _date.today().weekday() < 5
    elif exchange == 'NASDAQ':
        return _date.today().weekday() < 5
    else:
        # A股：用 Tushare
        try:
            from momentum_data import tushare_call
            ds = _date.today().strftime('%Y%m%d')
            data = tushare_call('trade_cal', {
                'exchange': 'SSE', 'start_date': ds, 'end_date': ds
            })
            if data and len(data) > 0:
                return data[0].get('is_open') == 1
        except Exception as e:
            print(f'  交易日判断失败({e})，默认放行')
    return True


def generate_report(scene_key):
    """动态加载对应场景的报告生成器"""
    scene = SCENES[scene_key]
    mod = importlib.import_module(scene['module'])
    func = getattr(mod, scene['func'])
    return func()


def send_to_all(report_html, scene_key, cfg, test_only=False):
    """发送邮件给订阅者"""
    scene = SCENES[scene_key]
    sender_cfg = cfg['sender']
    
    if test_only:
        # 测试模式：只发给 Roni
        recipients = [s for s in cfg['subscribers'] if '黄冰熠' in s.get('name', '') or 'roni' in s.get('email', '').lower()]
        if not recipients:
            recipients = cfg['subscribers'][:1]
        print(f'[测试模式] 只发给: {recipients[0]["name"]}')
    else:
        recipients = active_subscribers(cfg, scene_key)
    
    if not recipients:
        print(f'  ⚠ 场景 {scene["name"]} 无订阅者，跳过')
        return

    today = _date.today().strftime('%m/%d')
    subject = f'{scene["subject_prefix"]} | {today}'
    footer = cfg.get('settings', {}).get('footer', 'GAMT 投研看板 · 自动推送')

    # 构建邮件 HTML
    html_body = f'''<div style="max-width:680px;margin:0 auto;font-family:-apple-system,'PingFang SC',sans-serif;background:#fff;padding:20px">
{report_html}
<div style="margin-top:20px;padding-top:12px;border-top:1px solid #e5e7eb;font-size:10px;color:#9ca3af;text-align:center">
{footer}<br>如需退订请回复此邮件
</div></div>'''

    print(f'  场景: {scene["name"]}')
    print(f'  订阅者: {len(recipients)} 人')
    print(f'  主题: {subject}')

    # SMTP 发送
    try:
        server = smtplib.SMTP_SSL(sender_cfg['smtp_host'], sender_cfg['smtp_port'])
        server.login(sender_cfg['email'], sender_cfg['auth_code'])
    except Exception as e:
        print(f'  ✗ SMTP 连接失败: {e}')
        return

    success, fail = 0, 0
    for sub in recipients:
        email = sub['email']
        name = sub.get('name', '')
        msg = MIMEMultipart('alternative')
        msg['From'] = f'GAMT投研 <{sender_cfg["email"]}>'
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        for attempt in range(1, 4):
            try:
                server.sendmail(sender_cfg['email'], email, msg.as_string())
                print(f'    ✓ {name} <{email}>')
                success += 1
                break
            except Exception as e:
                if attempt < 3:
                    time.sleep(2)
                else:
                    print(f'    ✗ {name} <{email}> 失败: {e}')
                    fail += 1

    server.quit()
    print(f'  完成: {success} 成功, {fail} 失败')


def main():
    parser = argparse.ArgumentParser(description='多场景邮件发送')
    parser.add_argument('--scene', required=True, choices=list(SCENES.keys()),
                        help='发送场景')
    parser.add_argument('--force', action='store_true', help='跳过交易日判断')
    parser.add_argument('--test', action='store_true', help='测试模式（只发给 Roni）')
    args = parser.parse_args()

    scene = SCENES[args.scene]
    print(f'═══ {scene["name"]} ═══')

    # 交易日判断
    if not args.force and not args.test:
        if not is_trading_day(scene['exchange']):
            print('今日非交易日，跳过发送')
            return

    # 加载配置
    cfg = load_config()

    # 生成报告
    print('生成报告...')
    try:
        report_html = generate_report(args.scene)
    except Exception as e:
        print(f'  ✗ 报告生成失败: {e}')
        sys.exit(1)

    # 发送
    send_to_all(report_html, args.scene, cfg, test_only=args.test)


if __name__ == '__main__':
    main()
