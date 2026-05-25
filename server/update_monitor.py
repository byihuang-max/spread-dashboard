#!/usr/bin/env python3
"""
GAMT 数据更新监控 — 每日 21:30 飞书卡片汇报

检查逻辑：
1. 读 update_log.json 获取脚本运行状态
2. 对关键模块额外检查数据文件最新日期是否 = 当天交易日
3. 生成飞书卡片：绿点=正常，红点=异常

用法：
  python3 server/update_monitor.py          # 发送监控卡片
  python3 server/update_monitor.py --dry    # 预览不发送
"""

import json, os, sys, requests
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATE_LOG = os.path.join(BASE_DIR, 'server', 'update_log.json')

# 飞书配置
FEISHU_APP_ID = 'cli_a91c36caf5785cb2'
FEISHU_APP_SECRET = 'HWhYR833N0xObKumrjNCKdRSHq3jg0zi'
RONI_CHAT_ID = 'oc_1e941df394190b21d4c4edd83deae4f3'

# Tushare 交易日历
TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# 模块分组
CLOSE_MODULES = [
    'fund_nav', 'style_spread', 'quant_stock', 'commodity_cta', 'cb_env',
    'alerts', 'us_alerts', 'crowding', 'option_sentiment',
    'macro_liquidity', 'macro_rates', 'macro_fundamentals',
    'global_calendar', 'antifragile', 'narrative_monitor',
    'overseas_digest', 'narrative_lifecycle', 'chain_prosperity',
    'macro_score', 'option_vol', 'arbitrage', 'macro/halo_trade',
    'fund_asset', 'overview',
]

LATE_MODULES = [
    'barra_style', 'patient_capital', 'momentum_stock',
    'timing_factors', 'merger_pool', 'merger_report',
]

# 关键模块的数据文件 + 日期提取方式
# (file_path_relative, extract_func_name)
DATA_CHECKS = {
    'momentum_stock': {
        'file': 'env_fit/momentum_stock/momentum_sentiment.json',
        'extract': 'momentum_date',
    },
    'patient_capital': {
        'file': 'micro_flow/patient_capital/patient_capital.json',
        'extract': 'patient_date',
    },
    'crowding': {
        'file': 'micro_flow/crowding/crowding.json',
        'extract': 'crowding_date',
    },
    'style_spread': {
        'file': 'size_spread/spread_data.json',
        'extract': 'generic_update_time',
    },
    'option_sentiment': {
        'file': 'micro_flow/option_sentiment/option_sentiment.json',
        'extract': 'generic_update_time',
    },
    'timing_factors': {
        'file': 'timing-research/timing_factors.json',
        'extract': 'generic_update_time',
    },
}


def get_latest_trade_date():
    """获取最近交易日（今天如果是交易日就返回今天，否则返回上一个）"""
    today = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
    try:
        resp = requests.post(TUSHARE_URL, json={
            'api_name': 'trade_cal',
            'token': TUSHARE_TOKEN,
            'params': {'exchange': 'SSE', 'start_date': start, 'end_date': today, 'is_open': '1'},
            'fields': ''
        }, timeout=15, proxies={'http': None, 'https': None})
        data = resp.json()
        if data.get('code') == 0 and data.get('data', {}).get('items'):
            dates = sorted([row[1] for row in data['data']['items']])
            return dates[-1]  # 最近的交易日
    except Exception:
        pass
    # fallback: 假设今天是交易日
    return today


def extract_momentum_date(filepath):
    """从 momentum_sentiment.json 提取最新日期"""
    try:
        with open(filepath) as f:
            d = json.load(f)
        return d.get('meta', {}).get('date_range', '').split('~')[-1].strip()
    except Exception:
        return None


def extract_patient_date(filepath):
    """从 patient_capital.json 提取最新日期"""
    try:
        with open(filepath) as f:
            d = json.load(f)
        # updated 格式: "2026-05-20 22:32"
        updated = d.get('updated', '')
        return updated.split(' ')[0].replace('-', '') if updated else None
    except Exception:
        return None


def extract_crowding_date(filepath):
    """从 crowding.json 提取最新日期"""
    try:
        with open(filepath) as f:
            d = json.load(f)
        updated = d.get('update_time', '')
        return updated.split(' ')[0].replace('-', '') if updated else None
    except Exception:
        return None


def extract_generic_update_time(filepath):
    """通用：读 update_time 或 updated 字段"""
    try:
        with open(filepath) as f:
            d = json.load(f)
        for key in ('update_time', 'updated', 'last_update', 'generated'):
            if key in d:
                val = d[key]
                if isinstance(val, str) and len(val) >= 10:
                    return val[:10].replace('-', '')
        # 如果是 meta.generated
        if 'meta' in d and isinstance(d['meta'], dict):
            gen = d['meta'].get('generated', '')
            if gen:
                return gen[:10].replace('-', '')
    except Exception:
        pass
    return None


EXTRACTORS = {
    'momentum_date': extract_momentum_date,
    'patient_date': extract_patient_date,
    'crowding_date': extract_crowding_date,
    'generic_update_time': extract_generic_update_time,
}


def load_update_log():
    """读取 update_log.json"""
    if not os.path.exists(UPDATE_LOG):
        return []
    try:
        with open(UPDATE_LOG) as f:
            return json.load(f)
    except Exception:
        return []


def check_modules(expected_date):
    """
    检查所有模块状态
    返回: {module_key: {'ok': bool, 'reason': str, 'phase': str}}
    """
    log_entries = load_update_log()
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 按模块取最新一条今天的记录
    latest = {}
    for entry in log_entries:
        key = entry.get('module', '')
        entry_date = entry.get('date', '')
        if entry_date == today_str:
            if key not in latest or entry.get('time', '') > latest[key].get('time', ''):
                latest[key] = entry

    results = {}

    # 检查 close 模块
    for mod in CLOSE_MODULES:
        entry = latest.get(mod)
        if not entry:
            results[mod] = {'ok': False, 'reason': '今日未运行', 'phase': 'close'}
        elif not entry.get('ok'):
            results[mod] = {'ok': False, 'reason': '脚本报错', 'phase': 'close'}
        else:
            results[mod] = {'ok': True, 'reason': '', 'phase': 'close'}

    # 检查 late 模块
    for mod in LATE_MODULES:
        entry = latest.get(mod)
        if not entry:
            results[mod] = {'ok': False, 'reason': '今日未运行', 'phase': 'late'}
        elif not entry.get('ok'):
            results[mod] = {'ok': False, 'reason': '脚本报错', 'phase': 'late'}
        else:
            results[mod] = {'ok': True, 'reason': '', 'phase': 'late'}

    # 对关键模块做数据文件日期校验
    for mod, check in DATA_CHECKS.items():
        if mod not in results:
            continue
        if not results[mod]['ok']:
            continue  # 已经标红了

        filepath = os.path.join(BASE_DIR, check['file'])
        if not os.path.exists(filepath):
            results[mod] = {'ok': False, 'reason': '数据文件不存在', 'phase': results[mod]['phase']}
            continue

        extractor = EXTRACTORS.get(check['extract'])
        if not extractor:
            continue

        data_date = extractor(filepath)
        if data_date and data_date < expected_date:
            results[mod]['ok'] = False
            results[mod]['reason'] = f'数据停在 {data_date}（预期 {expected_date}）'

    return results


def get_module_name(key):
    """获取模块中文名"""
    names = {
        'fund_nav': '产品净值', 'style_spread': '风格轧差',
        'quant_stock': '宽基量化股票', 'commodity_cta': '商品CTA',
        'cb_env': '转债指增', 'alerts': '红灯预警',
        'us_alerts': '美股风险监控', 'crowding': '资金流拥挤度',
        'option_sentiment': '期权情绪', 'macro_liquidity': '宏观流动性',
        'macro_rates': '利率数据', 'macro_fundamentals': '基本面数据',
        'global_calendar': '全球金融日历', 'antifragile': '反脆弱看板',
        'narrative_monitor': '叙事监控', 'overseas_digest': '海外一手要闻',
        'narrative_lifecycle': '叙事生命周期', 'chain_prosperity': '中观景气度',
        'macro_score': '宏观打分', 'option_vol': '期权卖权',
        'arbitrage': '套利', 'macro/halo_trade': 'HALO交易',
        'fund_asset': '团队基金优选', 'overview': '仪表盘汇总',
        'barra_style': 'Barra风格因子', 'patient_capital': '耐心资本',
        'momentum_stock': '强势股情绪', 'timing_factors': '择时因子系统',
        'merger_pool': '并购池', 'merger_report': '并购深度分析',
    }
    return names.get(key, key)


def build_feishu_card(results, expected_date):
    """构建飞书卡片"""
    close_results = {k: v for k, v in results.items() if v['phase'] == 'close'}
    late_results = {k: v for k, v in results.items() if v['phase'] == 'late'}

    close_ok = sum(1 for v in close_results.values() if v['ok'])
    close_total = len(close_results)
    late_ok = sum(1 for v in late_results.values() if v['ok'])
    late_total = len(late_results)

    all_ok = (close_ok == close_total) and (late_ok == late_total)

    # 标题
    if all_ok:
        title = f"✅ 数据更新正常 ({expected_date[:4]}-{expected_date[4:6]}-{expected_date[6:]})"
        title_color = "green"
    else:
        failed = (close_total - close_ok) + (late_total - late_ok)
        title = f"⚠️ 数据更新异常 — {failed} 个模块未跑通"
        title_color = "red"

    elements = []

    # Close phase
    close_lines = []
    for mod in CLOSE_MODULES:
        r = close_results.get(mod, {'ok': False, 'reason': '未注册'})
        dot = "🟢" if r['ok'] else "🔴"
        name = get_module_name(mod)
        line = f"{dot} {name}"
        if not r['ok'] and r.get('reason'):
            line += f"  _{r['reason']}_"
        close_lines.append(line)

    elements.append({
        "tag": "markdown",
        "content": f"**17:00 收盘更新** ({close_ok}/{close_total})\n" + "\n".join(close_lines)
    })

    elements.append({"tag": "hr"})

    # Late phase
    late_lines = []
    for mod in LATE_MODULES:
        r = late_results.get(mod, {'ok': False, 'reason': '未注册'})
        dot = "🟢" if r['ok'] else "🔴"
        name = get_module_name(mod)
        line = f"{dot} {name}"
        if not r['ok'] and r.get('reason'):
            line += f"  _{r['reason']}_"
        late_lines.append(line)

    elements.append({
        "tag": "markdown",
        "content": f"**21:00 晚到数据** ({late_ok}/{late_total})\n" + "\n".join(late_lines)
    })

    # 底部时间
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"检查时间: {datetime.now().strftime('%H:%M')} | 预期交易日: {expected_date}"}]
    })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": title_color,
        },
        "elements": elements,
    }
    return card


def get_feishu_token():
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': FEISHU_APP_ID, 'app_secret': FEISHU_APP_SECRET},
        timeout=10
    )
    return resp.json().get('tenant_access_token', '')


def send_feishu_card(card):
    """发送飞书卡片到 Roni"""
    token = get_feishu_token()
    if not token:
        print("❌ 获取飞书 token 失败")
        return False

    resp = requests.post(
        'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={
            'receive_id': RONI_CHAT_ID,
            'msg_type': 'interactive',
            'content': json.dumps(card, ensure_ascii=False),
        },
        timeout=10
    )
    result = resp.json()
    if result.get('code') == 0:
        print("✅ 飞书卡片已发送")
        return True
    else:
        print(f"❌ 发送失败: {result.get('msg', result)}")
        return False


def main():
    dry_run = '--dry' in sys.argv

    print("获取最近交易日...")
    expected_date = get_latest_trade_date()
    print(f"预期交易日: {expected_date}")

    print("检查模块状态...")
    results = check_modules(expected_date)

    # 统计
    ok_count = sum(1 for v in results.values() if v['ok'])
    total = len(results)
    failed = [k for k, v in results.items() if not v['ok']]

    print(f"\n结果: {ok_count}/{total} 正常")
    if failed:
        print("异常模块:")
        for k in failed:
            print(f"  🔴 {get_module_name(k)}: {results[k]['reason']}")

    card = build_feishu_card(results, expected_date)

    if dry_run:
        print("\n[DRY RUN] 卡片内容:")
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        send_feishu_card(card)


if __name__ == '__main__':
    main()
