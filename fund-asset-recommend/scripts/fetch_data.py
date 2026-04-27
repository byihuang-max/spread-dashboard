#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - 数据采集
统一封装火富牛 API 调用，支持 SDK 和 REST 两种方式
"""

import hashlib, time, json, os, math, urllib.parse
import requests
from datetime import datetime, timedelta

from config import (
    APP_ID, APP_KEY, BASE_URL, DATA_DIR, RAW_DIR,
    PRODUCTS, COMBIS, MARKET_IDS, PLATFORM_SOURCE_CODES,
)

# ========== 通用工具 ==========

def api_sign(params):
    """火富牛 API 签名：参数 key 升序拼接 + APP_KEY，MD5"""
    sorted_keys = sorted(k for k in params if k != 'sign')
    s = '&'.join(f'{k}={params[k]}' for k in sorted_keys) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()


def api_get(path, params, timeout=15):
    """通用 GET 请求"""
    params['app_id'] = APP_ID
    params['tm'] = str(int(time.time()))
    params['sign'] = api_sign(params)
    r = requests.get(f'{BASE_URL}{path}', params=params, timeout=timeout, verify=False)
    data = r.json()
    if data.get('error_code') != 0:
        print(f"  ⚠️ API 错误 {path}: {data.get('msg', data)}")
        return None
    return data.get('data')


# ========== 1. 产品净值采集 ==========

def fetch_fund_nav_history(reg_code, start_date="2025-01-01", source="team"):
    """拉取单只基金历史净值"""
    path = '/company/price' if source == 'team' else '/price'
    end_date = datetime.now().strftime('%Y-%m-%d')
    data = api_get(path, {
        'reg_code': reg_code,
        'start_date': start_date,
        'end_date': end_date,
        'order_by': 'price_date',
        'order': '0',  # 倒序
    })
    if data:
        return [(n['price_date'], float(n['cumulative_nav'])) for n in data
                if n.get('price_date') and n.get('cumulative_nav')]
    # team 接口失败，fallback 到 platform
    if source == 'team':
        return fetch_fund_nav_history(reg_code, start_date, source='platform')
    return []


def fetch_all_products():
    """批量拉取所有产品净值，计算收益指标"""
    print(f"📡 拉取 {len(PRODUCTS)} 只产品净值...")
    results = []
    for p in PRODUCTS:
        source = 'platform' if p['code'] in PLATFORM_SOURCE_CODES else 'team'
        print(f"  {p['name']} ({p['code']}, {source})...", end=" ", flush=True)
        navs = fetch_fund_nav_history(p['code'], source=source)
        if navs:
            metrics = compute_fund_metrics(navs)
            results.append({**p, **metrics, 'source_type': 'fund', 'data_source': 'api', 'status': '正常'})
            print(f"✅ {len(navs)}条")
        else:
            results.append({**p, 'source_type': 'fund', 'data_source': 'api', 'status': '无数据'})
            print("❌")
        time.sleep(0.3)
    return results


# ========== 2. 组合净值采集 ==========

def fetch_combi_nav(combi_id):
    """拉取组合净值"""
    data = api_get('/combi/price', {'id': combi_id})
    if data:
        data.sort(key=lambda x: x['price_date'])
        return [(d['price_date'], float(d['cumulative_nav'])) for d in data]
    return []


def fetch_all_combis():
    """批量拉取所有组合净值"""
    print(f"📡 拉取 {len(COMBIS)} 个组合净值...")
    results = []
    for c in COMBIS:
        print(f"  {c['name']} ({c['id']})...", end=" ", flush=True)
        navs = fetch_combi_nav(c['id'])
        if navs:
            metrics = compute_fund_metrics(navs)
            results.append({**c, 'code': c['id'], **metrics, 'source_type': 'combi', 'data_source': 'api', 'status': '正常'})
            print(f"✅ {len(navs)}条")
        else:
            results.append({**c, 'code': c['id'], 'source_type': 'combi', 'data_source': 'api', 'status': '无数据'})
            print("❌")
        time.sleep(0.3)
    return results


# ========== 3. 市场策略基准 ==========

def fetch_market_category(type_val):
    """拉取市场策略基准数据"""
    ids_encoded = urllib.parse.quote(MARKET_IDS, safe='')
    end_date = datetime.now().strftime('%Y-%m-%d')
    # 这个接口签名比较特殊，ids 需要 encode 后参与签名
    tm = str(int(time.time()))
    sign_params = {'app_id': APP_ID, 'end_date': end_date, 'ids': ids_encoded, 'tm': tm, 'type': str(type_val)}
    sorted_keys = sorted(sign_params.keys())
    sign_str = '&'.join(f'{k}={sign_params[k]}' for k in sorted_keys) + APP_KEY
    sign_val = hashlib.md5(sign_str.encode()).hexdigest()
    url = f'{BASE_URL}/market/category?app_id={APP_ID}&end_date={end_date}&ids={ids_encoded}&sign={sign_val}&tm={tm}&type={type_val}'
    r = requests.get(url, timeout=15, verify=False)
    return r.json().get('data', [])


def fetch_market_data():
    """拉取年度/月度/季度市场策略基准"""
    print("📡 拉取市场策略基准...")
    annual = fetch_market_category(5)
    print(f"  年度: {len(annual)} 策略")
    time.sleep(0.3)
    monthly = fetch_market_category(2)
    print(f"  月度: {len(monthly)} 策略")
    time.sleep(0.3)
    quarterly = fetch_market_category(3)
    print(f"  季度: {len(quarterly)} 策略")
    return annual, monthly, quarterly


# ========== 收益指标计算 ==========

def compute_fund_metrics(nav_list):
    """
    输入: [(date_str, cum_nav), ...]  倒序或正序均可
    输出: dict with week_return, month_return, ytd_return, latest_nav, latest_date, etc.
    """
    # 确保正序
    sorted_navs = sorted(nav_list, key=lambda x: x[0])
    if len(sorted_navs) < 2:
        return {}

    dates = [n[0] for n in sorted_navs]
    vals = [n[1] for n in sorted_navs]

    latest_date = dates[-1]
    latest_nav = vals[-1]

    # 统计截止日 = 最新净值日
    stat_end = latest_date

    def find_nav_before(target_date):
        """找 target_date 当天或之前最近的净值"""
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= target_date:
                return vals[i], dates[i]
        return vals[0], dates[0]

    # 近一周
    week_ago = (datetime.strptime(stat_end, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
    week_base, _ = find_nav_before(week_ago)
    week_return = (latest_nav / week_base - 1) if week_base else None

    # 近一月
    month_ago = (datetime.strptime(stat_end, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
    month_base, _ = find_nav_before(month_ago)
    month_return = (latest_nav / month_base - 1) if month_base else None

    # 今年以来
    ytd_base, _ = find_nav_before(f'{int(stat_end[:4])-1}-12-31')
    ytd_return = (latest_nav / ytd_base - 1) if ytd_base else None

    # 日收益率序列
    returns = [(vals[i] / vals[i-1] - 1) for i in range(1, len(vals))]

    # 年化波动率
    if len(returns) > 1:
        avg_ret = sum(returns) / len(returns)
        var = sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
        ann_vol = math.sqrt(var) * math.sqrt(252)
    else:
        ann_vol = 0

    # 年化收益
    d0 = datetime.strptime(dates[0], '%Y-%m-%d')
    d1 = datetime.strptime(dates[-1], '%Y-%m-%d')
    days = (d1 - d0).days
    ann_ret = (vals[-1] / vals[0]) ** (365 / max(days, 1)) - 1

    # 夏普
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0

    # 最大回撤
    peak = vals[0]
    max_dd = 0
    for v in vals:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    # 卡玛
    calmar = ann_ret / max_dd if max_dd > 0 else 0

    return {
        'latest_date': latest_date,
        'latest_cum_nav': latest_nav,
        'stat_end_date': stat_end,
        'stat_end_cum_nav': latest_nav,
        'week_return': week_return,
        'month_return': month_return,
        'ytd_return': ytd_return,
        'ann_ret': ann_ret,
        'ann_vol': ann_vol,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'calmar': calmar,
    }


# ========== 汇总输出 ==========

def build_strategy_summary(products, combis):
    """
    把产品按策略组聚合，生成 strategySummary 格式
    与原 v3 HTML 中的 JS 变量结构一致
    """
    from collections import defaultdict
    groups = defaultdict(list)

    for p in products + combis:
        groups[p['group']].append(p)

    # 策略组描述
    GROUP_DESC = {
        "量选类": "系统化选股/择时",
        "风格类": "风格增强与弹性轮动",
        "绝对收益": "回撤控制与稳健收益",
        "商品类": "分散配置与宏观对冲",
        "多策略": "跨资产平衡配置",
        "FOF组合类": "组合配置与稳健增强",
        "FOF组合": "FOF组合净值跟踪",
    }

    summary = []
    for group_name, items in groups.items():
        valid = [i for i in items if i.get('week_return') is not None]
        avg_week = sum(i['week_return'] for i in valid) / len(valid) if valid else 0
        avg_month = sum(i.get('month_return', 0) or 0 for i in valid) / len(valid) if valid else 0
        avg_ytd = sum(i.get('ytd_return', 0) or 0 for i in valid) / len(valid) if valid else 0

        # 找 leader（YTD 最高）
        leader = max(valid, key=lambda x: x.get('ytd_return', 0) or 0)['name'] if valid else '-'

        summary.append({
            'strategy': group_name,
            'description': GROUP_DESC.get(group_name, ''),
            'color': items[0].get('color', '#666'),
            'count': len(items),
            'avg_week': avg_week,
            'avg_month': avg_month,
            'avg_ytd': avg_ytd,
            'leader': leader,
            'items': [{
                'name': i['name'],
                'code': i['code'],
                'strategy': i['group'],
                'strategy_detail': i.get('detail', ''),
                'advisor': '-',
                'source_type': i.get('source_type', 'fund'),
                'latest_date': i.get('latest_date', ''),
                'latest_cum_nav': i.get('latest_cum_nav'),
                'stat_end_date': i.get('stat_end_date', ''),
                'stat_end_cum_nav': i.get('stat_end_cum_nav'),
                'week_return': i.get('week_return'),
                'month_return': i.get('month_return'),
                'ytd_return': i.get('ytd_return'),
                'status': i.get('status', '正常'),
                'data_source': i.get('data_source', 'api'),
            } for i in items],
        })

    return summary


def save_data(products, combis, market_annual, market_monthly, market_quarterly):
    """保存所有数据到 JSON"""
    os.makedirs(RAW_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')

    strategy_summary = build_strategy_summary(products, combis)

    # 主数据文件
    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy_summary': strategy_summary,
        'market_data': {
            'annual': market_annual,
            'monthly': market_monthly,
            'quarterly': market_quarterly,
        },
    }

    # 保存带日期版本
    dated_path = os.path.join(RAW_DIR, f'fund_asset_{today}.json')
    with open(dated_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 保存: {dated_path}")

    # 保存 latest 版本
    latest_path = os.path.join(DATA_DIR, 'fund_asset_latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 保存: {latest_path}")

    return output


# ========== 主入口 ==========

def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("=" * 50)
    print("团队基金优选 - 数据采集")
    print("=" * 50)

    # 1. 产品净值
    products = fetch_all_products()

    # 2. 组合净值
    combis = fetch_all_combis()

    # 3. 市场基准
    annual, monthly, quarterly = fetch_market_data()

    # 4. 保存
    output = save_data(products, combis, annual, monthly, quarterly)

    # 统计
    ok_count = sum(1 for p in products + combis if p.get('status') == '正常')
    total = len(products) + len(combis)
    print(f"\n✅ 完成: {ok_count}/{total} 只产品有数据")

    return output


if __name__ == '__main__':
    main()
