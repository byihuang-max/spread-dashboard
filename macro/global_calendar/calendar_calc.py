#!/usr/bin/env python3
"""
全球金融日历 - 打标与输出
读：cache/eco_cal_raw.csv + event_library.json
输出：calendar.json（给前端）
规则：
  - 按 event_library.json 的 keywords 匹配事件名 → 重要性 + 影响资产 + 逻辑
  - 未命中 → 默认 ● (1) 级 + "一般经济数据"
  - 按重要性 DESC、时间 ASC 排序
  - 分三段：已公布 / 本周 / 下周
"""
import os, sys, json
import datetime as dt
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')

# 货币 → 国家代码 + 国旗
CURRENCY_MAP = {
    'USD': {'country': '美国', 'code': 'US', 'flag': '🇺🇸'},
    'EUR': {'country': '欧元区', 'code': 'EU', 'flag': '🇪🇺'},
    'CNY': {'country': '中国', 'code': 'CN', 'flag': '🇨🇳'},
    'JPY': {'country': '日本', 'code': 'JP', 'flag': '🇯🇵'},
    'GBP': {'country': '英国', 'code': 'GB', 'flag': '🇬🇧'},
    'AUD': {'country': '澳洲', 'code': 'AU', 'flag': '🇦🇺'},
    'NZD': {'country': '新西兰', 'code': 'NZ', 'flag': '🇳🇿'},
    'CAD': {'country': '加拿大', 'code': 'CA', 'flag': '🇨🇦'},
    'CHF': {'country': '瑞士', 'code': 'CH', 'flag': '🇨🇭'},
    'HKD': {'country': '香港', 'code': 'HK', 'flag': '🇭🇰'},
    'KRW': {'country': '韩国', 'code': 'KR', 'flag': '🇰🇷'},
    'INR': {'country': '印度', 'code': 'IN', 'flag': '🇮🇳'},
    'SGD': {'country': '新加坡', 'code': 'SG', 'flag': '🇸🇬'},
    'THB': {'country': '泰国', 'code': 'TH', 'flag': '🇹🇭'},
    'IDR': {'country': '印尼', 'code': 'ID', 'flag': '🇮🇩'},
    'BRL': {'country': '巴西', 'code': 'BR', 'flag': '🇧🇷'},
    'ZAR': {'country': '南非', 'code': 'ZA', 'flag': '🇿🇦'},
    'RUB': {'country': '俄罗斯', 'code': 'RU', 'flag': '🇷🇺'},
    'MXN': {'country': '墨西哥', 'code': 'MX', 'flag': '🇲🇽'},
    'TRY': {'country': '土耳其', 'code': 'TR', 'flag': '🇹🇷'},
    'VND': {'country': '越南', 'code': 'VN', 'flag': '🇻🇳'},
    'MYR': {'country': '马来西亚', 'code': 'MY', 'flag': '🇲🇾'},
    'PHP': {'country': '菲律宾', 'code': 'PH', 'flag': '🇵🇭'},
    'TWD': {'country': '台湾', 'code': 'TW', 'flag': '🏳'},
    'SEK': {'country': '瑞典', 'code': 'SE', 'flag': '🇸🇪'},
    'NOK': {'country': '挪威', 'code': 'NO', 'flag': '🇳🇴'},
    'DKK': {'country': '丹麦', 'code': 'DK', 'flag': '🇩🇰'},
}


def load_library():
    path = os.path.join(SCRIPT_DIR, 'event_library.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def match_event(event_name, rules):
    """按 keywords 命中返回规则；全不命中返回 None"""
    if not event_name:
        return None
    for rule in rules:
        for kw in rule['keywords']:
            if kw in event_name:
                return rule
    return None


def determine_status(date_str, time_str, value):
    """
    返回 (status, now_flag)
    status: released(已公布) / today(今日) / upcoming(待公布)
    """
    try:
        d = dt.datetime.strptime(str(date_str), '%Y%m%d').date()
    except Exception:
        return 'upcoming', False

    today = dt.date.today()
    # 有实际值 → released
    has_value = value is not None and str(value).strip() != '' and str(value) != 'nan'
    if has_value:
        return 'released', False
    if d < today:
        return 'released', False  # 已过时但无数据
    if d == today:
        return 'today', True
    return 'upcoming', False


def surprise_flag(value, fore_value):
    """实际 vs 预期，返回 ▲/▼/— 或空"""
    try:
        if value is None or fore_value is None:
            return ''
        v = float(str(value).replace(',', '').replace('%', ''))
        f = float(str(fore_value).replace(',', '').replace('%', ''))
        diff = v - f
        ref = abs(f) if abs(f) > 0.01 else 1.0
        pct_diff = diff / ref
        if pct_diff > 0.02:
            return '▲'
        if pct_diff < -0.02:
            return '▼'
        return '—'
    except Exception:
        return ''


def main():
    raw_path = os.path.join(CACHE_DIR, 'eco_cal_raw.csv')
    if not os.path.exists(raw_path):
        print(f"缺数据: {raw_path}")
        sys.exit(1)

    df = pd.read_csv(raw_path)
    library = load_library()
    rules = library['rules']

    today = dt.date.today()
    week_end = today + dt.timedelta(days=(6 - today.weekday()))  # 本周日

    events = []
    for _, row in df.iterrows():
        cur = str(row.get('currency', '')).strip().upper()
        cinfo = CURRENCY_MAP.get(cur, {'country': cur, 'code': cur, 'flag': '🏳'})
        event_name = str(row.get('event', '')).strip()

        rule = match_event(event_name, rules)
        if rule:
            importance = rule['importance']
            equity = rule.get('equity', '-')
            bond = rule.get('bond', '-')
            logic = rule.get('logic', '')
        else:
            importance = 1
            equity = '-'
            bond = '-'
            logic = '一般经济数据，对主要资产类别影响较边际。'

        date_str = str(row.get('date', ''))
        time_str = str(row.get('time', ''))
        value = row.get('value')
        fore = row.get('fore_value')
        pre = row.get('pre_value')

        status, _ = determine_status(date_str, time_str, value)

        # 归类到 phase
        try:
            d = dt.datetime.strptime(date_str, '%Y%m%d').date()
        except Exception:
            continue

        if status == 'released':
            phase = 'released'
        elif d <= week_end:
            phase = 'thisweek'
        else:
            phase = 'nextweek'

        events.append({
            'date': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
            'time': time_str if time_str and str(time_str) != 'nan' else '-',
            'country': cinfo['country'],
            'country_code': cinfo['code'],
            'flag': cinfo['flag'],
            'currency': cur,
            'event': event_name,
            'importance': importance,
            'importance_dots': '●' * importance,
            'pre_value': '' if (pre is None or str(pre) == 'nan') else str(pre),
            'fore_value': '' if (fore is None or str(fore) == 'nan') else str(fore),
            'value': '' if (value is None or str(value) == 'nan') else str(value),
            'surprise': surprise_flag(value, fore),
            'equity_impact': equity,
            'bond_impact': bond,
            'logic': logic,
            'status': status,
            'phase': phase,
        })

    # 排序：重要性 DESC → 日期 ASC → 时间 ASC
    def sort_key(x):
        return (-x['importance'], x['date'], x['time'] if x['time'] != '-' else '99:99')
    events.sort(key=sort_key)

    # 分三桶
    by_phase = {'released': [], 'thisweek': [], 'nextweek': []}
    for e in events:
        by_phase[e['phase']].append(e)

    # released 按日期倒序（最新在前），同日按重要性倒序
    by_phase['released'].sort(key=lambda x: (-x['importance'], x['date'], x['time'] if x['time'] != '-' else '99:99'))
    by_phase['released'].sort(key=lambda x: x['date'], reverse=True)

    # 只展示 ●● 及以上，默认过滤，但 released 段也保留 ● 以看回顾
    # 前端做筛选，这里全部输出
    
    # 核心事件（●●● 且 today/本周）；若本周为空则从 released 取最近的 ●●● 事件
    today_iso = today.strftime('%Y-%m-%d')
    core = [e for e in events if e['importance'] == 3 and e['phase'] in ('thisweek',) and e['date'] >= today_iso]
    if not core and by_phase['released']:
        # 回退：取 released 中最近日期的 ●●● 事件
        core = [e for e in by_phase['released'] if e['importance'] == 3]
    core = core[:8]

    out = {
        'updated_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'week_of': today.strftime('%Y-%m-%d'),
        'stats': {
            'total': len(events),
            'released': len(by_phase['released']),
            'thisweek': len(by_phase['thisweek']),
            'nextweek': len(by_phase['nextweek']),
            'high_importance': sum(1 for e in events if e['importance'] == 3),
        },
        'core_events': core,
        'released': by_phase['released'],
        'thisweek': by_phase['thisweek'],
        'nextweek': by_phase['nextweek'],
    }

    out_path = os.path.join(SCRIPT_DIR, 'calendar.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✓ 输出 {len(events)} 条事件")
    print(f"  已公布: {len(by_phase['released'])}")
    print(f"  本周: {len(by_phase['thisweek'])}")
    print(f"  下周: {len(by_phase['nextweek'])}")
    print(f"  高重要性: {out['stats']['high_importance']}")
    print(f"  核心卡片: {len(core)}")
    print(f"  → {out_path}")


if __name__ == '__main__':
    main()
