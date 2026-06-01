#!/usr/bin/env python3
"""百亿涨停质量分层 → 飞书 RONIHUANG BOT 试验版

按涨停时间排序 + 换手板标注 + 近7日板数（辨识度）
"""
import json, os, sys, requests

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

APP_ID = 'cli_a91c36caf5785cb2'
APP_SECRET = 'HWhYR833N0xObKumrjNCKdRSHq3jg0zi'
CHAT_ID = 'oc_1e941df394190b21d4c4edd83deae4f3'


def get_token():
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': APP_ID, 'app_secret': APP_SECRET}
    )
    return resp.json().get('tenant_access_token')


def parse_time(first_time_str):
    """将 '93318' 或 '100530' 解析为 (分钟数, 显示字符串)"""
    if not first_time_str:
        return None, '--:--'
    s = str(first_time_str).strip()
    s = s.zfill(6)
    h, m, sec = int(s[:2]), int(s[2:4]), int(s[4:6])
    return h * 60 + m, f'{h:02d}:{m:02d}'


def calc_7day_limits(target_date, cache_dir):
    """计算每只票近7个交易日的涨停天数（含当日）"""
    # 找最近7个缓存文件（按日期倒序）
    files = sorted([f for f in os.listdir(cache_dir) if f.endswith('.json') and len(f) == 13])
    # 找 target_date 的位置
    target_file = f'{target_date}.json'
    if target_file in files:
        idx = files.index(target_file)
    else:
        idx = len(files) - 1
    recent_files = files[max(0, idx - 6):idx + 1]  # 最多7天

    # 统计每只票涨停天数
    limit_days = {}  # ts_code → count
    for fname in recent_files:
        with open(os.path.join(cache_dir, fname)) as f:
            data = json.load(f)
        for u in data.get('U', []):
            code = u.get('ts_code', '')
            if code:
                limit_days[code] = limit_days.get(code, 0) + 1
    return limit_days


def classify_limit(item):
    """分类涨停质量"""
    open_times = item.get('open_times') or 0
    first_time = item.get('first_time')
    total_mv = (item.get('total_mv') or 0) / 1e8  # 亿

    minutes, time_str = parse_time(first_time)

    if open_times > 0:
        quality = 'swap'  # 换手板
    elif minutes is not None and minutes >= 13 * 60 and total_mv < 100:
        quality = 'weak'  # 尾盘硬封小票
    elif open_times == 0 and minutes is not None and minutes <= 9 * 60 + 35:
        quality = 'yizi'  # 一字板
    else:
        quality = 'normal'

    return quality, minutes, time_str


def generate_mega_limit_report(trade_date=None):
    """生成百亿涨停质量分层报告"""
    cache_dir = os.path.join(BASE, '_cache')
    if trade_date:
        cache_file = os.path.join(cache_dir, f'{trade_date}.json')
    else:
        files = sorted([f for f in os.listdir(cache_dir) if f.endswith('.json') and len(f) == 13])
        if not files:
            return None, '无缓存数据'
        cache_file = os.path.join(cache_dir, files[-1])
        trade_date = files[-1][:8]

    if not os.path.exists(cache_file):
        return None, f'缓存不存在: {trade_date}'

    with open(cache_file) as f:
        data = json.load(f)

    ups = data.get('U', [])
    # 百亿以上
    mega = [u for u in ups if (u.get('total_mv') or 0) >= 1e10
            and u.get('close', 0) > 0 and abs(u.get('pct_chg', 0)) < 50]

    if not mega:
        return trade_date, '当日无百亿涨停'

    # 近7日涨停天数
    limit_7d = calc_7day_limits(trade_date, cache_dir)

    # 分类 + 排序
    enriched = []
    for item in mega:
        quality, minutes, time_str = classify_limit(item)
        enriched.append({
            **item,
            '_quality': quality,
            '_minutes': minutes if minutes else 9999,
            '_time_str': time_str,
            '_mv_yi': (item.get('total_mv') or 0) / 1e8,
            '_amt_yi': (item.get('amount') or 0) / 1e8,
            '_turnover': item.get('turnover_ratio') or 0,
            '_7d_limits': limit_7d.get(item.get('ts_code', ''), 1),
        })

    # 排序：换手板优先，组内按成交额从大到小
    quality_order = {'swap': 0, 'normal': 1, 'yizi': 2, 'weak': 3}
    enriched.sort(key=lambda x: (quality_order.get(x['_quality'], 9), -x['_amt_yi']))

    # 生成文本
    lines = []
    lines.append(f'百亿涨停质量分层 | {trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}')
    lines.append(f'共 {len(enriched)} 只 | 换手板 {sum(1 for e in enriched if e["_quality"]=="swap")} | '
                 f'一字板 {sum(1 for e in enriched if e["_quality"]=="yizi")} | '
                 f'尾盘硬封 {sum(1 for e in enriched if e["_quality"]=="weak")}')
    lines.append('')

    def format_section(title, items):
        """格式化一个分类区块，带表头"""
        block = []
        block.append(f'■ {title}')
        block.append('名称(行业) | 封板 | 成交额 | 换手 | 7日板数')
        block.append('─' * 40)
        for e in items:
            lt = e.get('limit_times', 1)
            d7 = e['_7d_limits']
            # 7日板数显示：当日板数/7日累计
            d7_str = f'{lt}/{d7}' if d7 > lt else f'{lt}'
            row = (
                f'{e["name"]}({e.get("industry","")}) | '
                f'{e["_time_str"]} | '
                f'{e["_amt_yi"]:.1f}亿 | '
                f'{e["_turnover"]:.1f}% | '
                f'{d7_str}'
            )
            block.append(row)
        block.append('')
        return block

    def format_section_yizi(title, items):
        """一字板简化格式"""
        block = []
        block.append(f'■ {title}')
        block.append('名称(行业) | 成交额 | 7日板数')
        block.append('─' * 30)
        for e in items:
            lt = e.get('limit_times', 1)
            d7 = e['_7d_limits']
            d7_str = f'{lt}/{d7}' if d7 > lt else f'{lt}'
            row = f'{e["name"]}({e.get("industry","")}) | {e["_amt_yi"]:.1f}亿 | {d7_str}'
            block.append(row)
        block.append('')
        return block

    # 换手板
    swaps = [e for e in enriched if e['_quality'] == 'swap']
    if swaps:
        lines.extend(format_section('换手涨停（重点关注）', swaps))

    # 正常封板
    normals = [e for e in enriched if e['_quality'] == 'normal']
    if normals:
        lines.extend(format_section('正常封板', normals))

    # 一字板
    yizis = [e for e in enriched if e['_quality'] == 'yizi']
    if yizis:
        lines.extend(format_section_yizi('一字板（买不到）', yizis))

    # 尾盘硬封
    weaks = [e for e in enriched if e['_quality'] == 'weak']
    if weaks:
        lines.extend(format_section('尾盘硬封（降权）', weaks))

    return trade_date, '\n'.join(lines)


def build_card(trade_date, report_text):
    """构建飞书消息卡片 — 纯 markdown 不加 code 包裹"""
    elements = []
    for line in report_text.split('\n'):
        s = line.strip()
        if not s:
            continue
        if s.startswith('百亿涨停质量分层'):
            continue
        if s.startswith('共 '):
            elements.append({"tag": "markdown", "content": f"*{s}*"})
            elements.append({"tag": "hr"})
            continue
        if s.startswith('■'):
            elements.append({"tag": "markdown", "content": f"**{s}**"})
            continue
        if s.startswith('─'):
            # 分隔线用 hr
            elements.append({"tag": "hr"})
            continue
        if s.startswith('名称'):
            # 表头加粗
            elements.append({"tag": "markdown", "content": f"**{s}**"})
            continue
        # 普通行直接输出，不加引号
        elements.append({"tag": "markdown", "content": s})

    date_str = f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}'
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"百亿涨停质量分层 | {date_str}"},
            "template": "red"
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
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    trade_date = args[0] if args else None
    dt, report = generate_mega_limit_report(trade_date)

    if not dt:
        print(f'错误: {report}')
        return

    print(report)
    print()

    if '--send' in sys.argv:
        print('发送到飞书...')
        token = get_token()
        card = build_card(dt, report)
        result = send_card(card, token)
        if result.get('code') == 0:
            print('发送成功')
        else:
            print(f'发送失败: {result.get("msg")}')
    else:
        print('(加 --send 参数发送到飞书)')


if __name__ == '__main__':
    main()
