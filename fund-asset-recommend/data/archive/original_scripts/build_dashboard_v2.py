#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMT Dashboard v2 - 全量数据拉取 + 全新UI生成
修复：使用 /company/price (团队净值) 和 /price (平台净值) 双接口
"""

import hashlib, time, requests, json, os
from datetime import datetime, timedelta
from collections import Counter, defaultdict

APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

# 全部28只产品：code -> (显示名, 策略大类, 子策略, 数据源)
# source: 'platform' = /price, 'team' = /company/price
PRODUCTS = {
    "SATW62": ("顽岩量化选股", "量选类", "量化选股", "team"),
    "SARD76": ("正仁股票择时", "量选类", "股票择时", "team"),
    "SXG834": ("正仁双创择时", "风格类", "双创择时", "team"),
    "SZC020": ("瀚鑫纸鸢", "风格类", "微盘择时", "platform"),
    "SAJJ91": ("积沐领航者", "风格类", "1000指增", "team"),
    "SBCA75": ("太衍光年2000增强", "风格类", "2000指增T0", "team"),
    "SSV122": ("时间序列红利增强", "风格类", "红利指增", "platform"),
    "SLQ349": ("赢仕安盈二号", "风格类", "转债集中", "team"),
    "STE836": ("具力芒种1号", "风格类", "转债分散", "team"),
    "AEU46B": ("旌安思源1号B", "绝对收益", "短线择时", "team"),
    "SBDC67": ("创世纪顾锝", "绝对收益", "趋势策略", "team"),
    "SCJ476": ("立心菁英353号", "绝对收益", "主线择时", "team"),
    "VB166A": ("翔云50二号A", "绝对收益", "大盘择时", "team"),
    "SQX078": ("特夫郁金香", "绝对收益", "量化打板", "team"),
    "SVZ009": ("铭跃行远", "商品类", "量化时序CTA", "team"),
    "SXJ836": ("碳硅1号", "商品类", "化工主观", "team"),
    "SZM385": ("涌泉君安三号", "商品类", "黑色主观", "team"),
    "SSR379": ("海鹏扬帆", "商品类", "农产品主观", "team"),
    "SVZ638": ("格林鲲鹏6号", "多策略", "黄金大类", "team"),
    "SARZ77": ("波克宏观配置", "多策略", "宏观大类", "team"),
    "SGN799": ("玉数纯阿尔法一号", "风格类", "300指增T0", "team"),
    "SNY231": ("玉数顺利一号", "风格类", "500指增T0", "team"),
    "SZB966": ("玉数涵瑞专享十七号", "风格类", "1000指增T0", "team"),
    "SACB34": ("龙旗科技创新精选1号", "风格类", "双创指增", "team"),
    "SJD168": ("玉数涵瑞六号", "绝对收益", "300中性T0", "team"),
    "SAST37": ("国联陆联1号FOF", "FOF组合类", "低波私募FOF", "team"),
    "SBHP32": ("正仁听涛二号", "风格类", "灵活方向择时", "team"),
}

COMBI_PRODUCTS = {
    "c59639ceac9aca1f": ("大方向中波思源365", "FOF组合类", "中波公募FOF"),
}

def sign(params):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    s = '&'.join([f'{k}={params[k]}' for k in sorted_keys]) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()

def fetch_nav(reg_code, start_date, end_date, source='team'):
    """获取单只基金净值序列
    source='team' -> /company/price (团队净值，大部分产品)
    source='platform' -> /price (平台净值，少数产品)
    """
    tm = int(time.time())
    uri = '/company/price' if source == 'team' else '/price'
    params = {
        'app_id': APP_ID, 'reg_code': reg_code, 'order': '0',
        'order_by': 'price_date', 'start_date': start_date,
        'end_date': end_date, 'tm': tm
    }
    params['sign'] = sign(params)
    try:
        r = requests.get(f'{BASE_URL}{uri}', params=params, timeout=15, verify=False)
        data = r.json()
        if data.get('error_code') == 0 and data.get('data'):
            return data['data']
        # 如果团队接口失败，尝试平台接口
        if source == 'team':
            return fetch_nav(reg_code, start_date, end_date, source='platform')
    except Exception as e:
        print(f"  ❌ {reg_code} 异常: {e}")
    return []

def fetch_combi_nav(combi_id, start_date, end_date):
    tm = int(time.time())
    params = {
        'app_id': APP_ID, 'combi_id': combi_id, 'order': '0',
        'order_by': 'price_date', 'start_date': start_date,
        'end_date': end_date, 'tm': tm
    }
    params['sign'] = sign(params)
    try:
        r = requests.get(f'{BASE_URL}/combi/price', params=params, timeout=15, verify=False)
        data = r.json()
        if data.get('error_code') == 0 and data.get('data'):
            return data['data']
    except Exception as e:
        print(f"  ❌ combi {combi_id} 异常: {e}")
    return []

def find_nav_on_or_before(navs_by_date, target_date, max_lookback=10):
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    for i in range(max_lookback + 1):
        d = (dt - timedelta(days=i)).strftime('%Y-%m-%d')
        if d in navs_by_date:
            return navs_by_date[d], d
    return None, None

def calc_returns(navs_by_date, stat_end, week_start, month_end_prev, year_end_prev):
    end_nav, end_date = find_nav_on_or_before(navs_by_date, stat_end)
    week_nav, _ = find_nav_on_or_before(navs_by_date, week_start)
    month_nav, _ = find_nav_on_or_before(navs_by_date, month_end_prev)
    year_nav, _ = find_nav_on_or_before(navs_by_date, year_end_prev)
    return {
        'end_nav': end_nav, 'end_date': end_date,
        'week_return': (end_nav / week_nav - 1) if (end_nav and week_nav) else None,
        'month_return': (end_nav / month_nav - 1) if (end_nav and month_nav) else None,
        'ytd_return': (end_nav / year_nav - 1) if (end_nav and year_nav) else None,
    }

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    start_date = '2025-12-01'
    end_date = today
    print(f"=== GAMT Dashboard v2 数据拉取 ===")
    print(f"拉取区间: {start_date} ~ {end_date}\n")

    all_data = []
    for code, (name, strategy, detail, source) in PRODUCTS.items():
        print(f"📡 {name} ({code}, {source})...", end=" ", flush=True)
        navs = fetch_nav(code, start_date, end_date, source=source)
        navs_by_date = {}
        if navs:
            for n in navs:
                d = n.get('price_date', '')
                cum = n.get('cumulative_nav')
                if d and cum:
                    navs_by_date[d] = float(cum)
        dates_sorted = sorted(navs_by_date.keys(), reverse=True)
        latest_date = dates_sorted[0] if dates_sorted else None
        if navs_by_date:
            print(f"✅ {len(navs_by_date)}条, 最新={latest_date}")
        else:
            print(f"❌ 无数据")
        all_data.append({
            'code': code, 'name': name, 'strategy': strategy,
            'detail': detail, 'navs': navs_by_date, 'latest_date': latest_date,
        })
        time.sleep(0.3)

    for combi_id, (name, strategy, detail) in COMBI_PRODUCTS.items():
        print(f"📡 {name} (combi:{combi_id})...", end=" ", flush=True)
        navs = fetch_combi_nav(combi_id, start_date, end_date)
        navs_by_date = {}
        if navs:
            for n in navs:
                d = n.get('price_date', '')
                cum = n.get('cumulative_nav') or n.get('nav')
                if d and cum:
                    navs_by_date[d] = float(cum)
        dates_sorted = sorted(navs_by_date.keys(), reverse=True)
        latest_date = dates_sorted[0] if dates_sorted else None
        if navs_by_date:
            print(f"✅ {len(navs_by_date)}条, 最新={latest_date}")
        else:
            print(f"❌ 无数据")
        all_data.append({
            'code': combi_id, 'name': name, 'strategy': strategy,
            'detail': detail, 'navs': navs_by_date, 'latest_date': latest_date,
        })
        time.sleep(0.3)

    all_latest = [d['latest_date'] for d in all_data if d['latest_date']]
    date_counts = Counter(all_latest)
    stat_end = date_counts.most_common(1)[0][0] if date_counts else today
    stat_dt = datetime.strptime(stat_end, '%Y-%m-%d')
    week_start = (stat_dt - timedelta(days=7)).strftime('%Y-%m-%d')
    first_of_month = stat_dt.replace(day=1)
    month_end_prev = (first_of_month - timedelta(days=1)).strftime('%Y-%m-%d')
    year_end_prev = f"{stat_dt.year - 1}-12-31"

    print(f"\n📊 统计截止日: {stat_end}")
    print(f"  近一周起点: {week_start}")
    print(f"  近一月起点: {month_end_prev}")
    print(f"  今年以来起点: {year_end_prev}\n")

    rows = []
    for d in all_data:
        if not d['navs']:
            rows.append({
                'name': d['name'], 'strategy': d['strategy'], 'detail': d['detail'],
                'week_return': None, 'month_return': None, 'ytd_return': None,
                'status': '无数据', 'end_date': None, 'code': d['code']
            })
            continue
        ret = calc_returns(d['navs'], stat_end, week_start, month_end_prev, year_end_prev)
        status = '正常' if ret['end_date'] == stat_end else f"滞后({ret['end_date']})"
        rows.append({
            'name': d['name'], 'strategy': d['strategy'], 'detail': d['detail'],
            'week_return': ret['week_return'], 'month_return': ret['month_return'],
            'ytd_return': ret['ytd_return'], 'status': status,
            'end_date': ret['end_date'], 'code': d['code']
        })
        w = f"{ret['week_return']*100:+.2f}%" if ret['week_return'] is not None else '-'
        m = f"{ret['month_return']*100:+.2f}%" if ret['month_return'] is not None else '-'
        y = f"{ret['ytd_return']*100:+.2f}%" if ret['ytd_return'] is not None else '-'
        print(f"  {d['name']:20s} 周{w:>8s} 月{m:>8s} YTD{y:>8s} [{status}]")

    output = {
        'stat_end': stat_end, 'week_start': week_start,
        'month_end_prev': month_end_prev, 'year_end_prev': year_end_prev,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'rows': rows
    }
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gamt_data_latest.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 数据已保存: {json_path}")

    generate_html(output)

def generate_html(data):
    rows_json = json.dumps(data['rows'], ensure_ascii=False)
    stat_end = data['stat_end']
    gen_time = data['generated_at']
    week_start = data['week_start']
    month_prev = data['month_end_prev']
    year_prev = data['year_end_prev']

    groups = defaultdict(list)
    for r in data['rows']:
        groups[r['strategy']].append(r)

    strategy_order = ['量选类', '风格类', '绝对收益', '商品类', '多策略', 'FOF组合类']
    strategy_colors = {'量选类':'#3b82f6','风格类':'#10b981','绝对收益':'#8b5cf6','商品类':'#f59e0b','多策略':'#06b6d4','FOF组合类':'#6b7280'}
    strategy_icons = {'量选类':'🎯','风格类':'🔄','绝对收益':'🛡️','商品类':'📦','多策略':'🧩','FOF组合类':'🏛️'}

    summary_data = []
    for s in strategy_order:
        items = groups.get(s, [])
        if not items: continue
        ytds = [r['ytd_return'] for r in items if r['ytd_return'] is not None]
        weeks = [r['week_return'] for r in items if r['week_return'] is not None]
        avg_ytd = sum(ytds)/len(ytds) if ytds else 0
        avg_week = sum(weeks)/len(weeks) if weeks else 0
        best = max(items, key=lambda x: x['ytd_return'] or -999)
        summary_data.append({
            'strategy': s, 'count': len(items), 'avg_ytd': avg_ytd, 'avg_week': avg_week,
            'leader': best['name'], 'color': strategy_colors.get(s,'#666'),
            'icon': strategy_icons.get(s,'📊'), 'items': items
        })
    summary_json = json.dumps(summary_data, ensure_ascii=False)

    total = len(data['rows'])
    up_count = sum(1 for r in data['rows'] if r['week_return'] and r['week_return'] > 0)
    down_count = sum(1 for r in data['rows'] if r['week_return'] and r['week_return'] < 0)
    flat_count = total - up_count - down_count
    ytd_pos = sum(1 for r in data['rows'] if r['ytd_return'] and r['ytd_return'] > 0)
    best_ytd = max(data['rows'], key=lambda x: x['ytd_return'] or -999)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, 'dashboard_template.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    html = template.format(
        stat_end=stat_end, gen_time=gen_time, total=total,
        up_count=up_count, down_count=down_count, flat_count=flat_count,
        ytd_pos=ytd_pos, best_ytd_name=best_ytd['name'],
        best_ytd_val=f"{best_ytd['ytd_return']*100:.2f}" if best_ytd['ytd_return'] else '0',
        week_start=week_start, month_prev=month_prev, year_prev=year_prev,
        rows_json=rows_json, summary_json=summary_json,
    )

    html_path = os.path.join(script_dir, 'GAMT_Dashboard_v2.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Dashboard已生成: {html_path}")
    print(f"   file://{html_path}")

if __name__ == '__main__':
    main()


