#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - 数据采集
================================
统一封装火富牛 API 调用，采集三类数据：
  1. 核心产品净值（28只，FundCompanyPrice / FundPrice SDK）
  2. FOF 组合净值（6只，/combi/price REST API）
  3. 市场策略基准分位数（16个分类，/market/category SDK）

输出：
  - data/fund_asset_latest.json  最新完整数据（render_html.py 读取）
  - data/fund_asset_history.jsonl 每日追加一行（历史快照）
  - data/products_history.csv    产品净值增量（UTF-8 BOM）
  - data/fof_history.csv         FOF 组合净值增量（UTF-8 BOM）
  - data/raw/fund_asset_YYYYMMDD.json  原始 API 响应备份

使用方式：
  python3 fetch_data.py
  （已注册到 module_registry.py，由 update_all.py 自动调用）
"""

import hashlib, time, json, os, sys, math, urllib.parse
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
        print(f"  ⚠ API 错误 {path}: {data.get('msg', data)}")
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
    print(f" 拉取 {len(PRODUCTS)} 只产品净值...")
    results = []
    for p in PRODUCTS:
        source = 'platform' if p['code'] in PLATFORM_SOURCE_CODES else 'team'
        print(f"  {p['name']} ({p['code']}, {source})...", end=" ", flush=True)
        navs = fetch_fund_nav_history(p['code'], source=source)
        if navs:
            metrics = compute_fund_metrics(navs)
            results.append({**p, **metrics, '_raw_navs': navs, 'source_type': 'fund', 'data_source': 'api', 'status': '正常'})
            print(f" {len(navs)}条")
        else:
            results.append({**p, 'source_type': 'fund', 'data_source': 'api', 'status': '无数据'})
            print("")
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
    print(f" 拉取 {len(COMBIS)} 个组合净值...")
    results = []
    for c in COMBIS:
        print(f"  {c['name']} ({c['id']})...", end=" ", flush=True)
        navs = fetch_combi_nav(c['id'])
        if navs:
            metrics = compute_fund_metrics(navs)
            results.append({**c, 'code': c['id'], **metrics, '_raw_navs': navs,
                            'source_type': 'combi', 'data_source': 'api', 'status': '正常'})
            print(f" {len(navs)}条")
        else:
            results.append({**c, 'code': c['id'], 'source_type': 'combi', 'data_source': 'api', 'status': '无数据'})
            print("")
        time.sleep(0.3)
    return results


# ========== 3. 市场策略基准 ==========

def fetch_market_category(type_val, end_date=None):
    """拉取市场策略基准数据"""
    ids_encoded = urllib.parse.quote(MARKET_IDS, safe='')
    if end_date is None:
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


def _fetch_with_fallback(type_val):
    """先试当前日期，如果 return 全 null 则回退到上月末"""
    data = fetch_market_category(type_val)
    if any(d.get('return') is not None for d in data):
        return data
    # 回退到上月末
    last_month_end = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
    fallback = fetch_market_category(type_val, end_date=last_month_end)
    if any(d.get('return') is not None for d in fallback):
        print(f"    (回退到 {last_month_end})")
        return fallback
    # 再退一个月
    prev_month_end = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
    fallback2 = fetch_market_category(type_val, end_date=prev_month_end.strftime('%Y-%m-%d'))
    if any(d.get('return') is not None for d in fallback2):
        print(f"    (回退到 {prev_month_end.strftime('%Y-%m-%d')})")
        return fallback2
    return data


def fetch_market_data():
    """拉取年度/月度/季度市场策略基准（带智能回退）"""
    print(" 拉取市场策略基准...")
    annual = _fetch_with_fallback(5)
    print(f"  年度: {len(annual)} 策略")
    time.sleep(0.3)
    monthly = _fetch_with_fallback(2)
    print(f"  月度: {len(monthly)} 策略")
    time.sleep(0.3)
    quarterly = _fetch_with_fallback(3)
    print(f"  季度: {len(quarterly)} 策略")
    return annual, monthly, quarterly


# ========== 4. 基准指数净值 ==========

def fetch_benchmark_indices():
    """拉取策略对标基准指数的净值序列"""
    from config import STRATEGY_BENCHMARK, PRODUCTS
    from mall_sdk.fof99 import IndexPrice

    # 收集需要拉取的唯一基准代码
    codes = set()
    for cfg in STRATEGY_BENCHMARK.values():
        if cfg.get('benchmark'):
            codes.add(cfg['benchmark'])
    # 也从产品级 benchmark 字段收集
    for p in PRODUCTS:
        if p.get('benchmark'):
            codes.add(p['benchmark'])

    print(f" 拉取基准指数净值 ({len(codes)} 只)...")
    benchmark_navs = {}
    for code in sorted(codes):
        try:
            req = IndexPrice(APP_ID, APP_KEY)
            req.set_params(reg_code=code, start_date='2025-01-01')
            data = req.do_request()
            if data:
                # 转成 [[date, nav], ...] 正序
                series = sorted([[d['price_date'], d['nav']] for d in data], key=lambda x: x[0])
                benchmark_navs[code] = series
                print(f"   {code}: {len(series)} 条")
            else:
                print(f"  ⚠ {code}: 无数据")
            time.sleep(0.2)
        except Exception as e:
            print(f"   {code}: {e}")

    return benchmark_navs


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
        if p.get('hidden'):
            continue
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
                'ann_ret': i.get('ann_ret'),
                'ann_vol': i.get('ann_vol'),
                'sharpe': i.get('sharpe'),
                'max_dd': i.get('max_dd'),
                'calmar': i.get('calmar'),
                'status': i.get('status', '正常'),
                'data_source': i.get('data_source', 'api'),
                'benchmark': i.get('benchmark'),
                'benchmark_name': i.get('benchmark_name'),
            } for i in items],
        })

    return summary


def build_fof_combis(combis):
    """构建 FOF 组合详情数据（含净值曲线、回撤曲线、月度收益等），供 v3 HTML FOF 模块使用"""
    from collections import defaultdict
    fof_list = []
    # 只取 FOF组合 分组的（不含 FOF组合类）
    fof_items = [c for c in combis if c.get('group') == 'FOF组合' and c.get('_raw_navs') and not c.get('hidden')]

    for c in fof_items:
        navs = c['_raw_navs']  # [(date, nav), ...]
        if len(navs) < 2:
            continue

        dates = [n[0] for n in navs]
        vals = [n[1] for n in navs]
        start_date = dates[0]
        end_date = dates[-1]
        latest_nav = vals[-1]
        run_days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days
        total_ret = latest_nav / vals[0] - 1

        # 日收益率
        returns = [(vals[i] / vals[i-1] - 1) for i in range(1, len(vals))]

        # 年化
        ann_ret = (1 + total_ret) ** (365 / max(run_days, 1)) - 1
        avg_ret = sum(returns) / len(returns) if returns else 0
        var = sum((r - avg_ret)**2 for r in returns) / max(len(returns)-1, 1) if returns else 0
        ann_vol = math.sqrt(var) * math.sqrt(252)
        sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0

        # 回撤序列
        peak = vals[0]
        dd_data = []
        max_dd = 0
        max_dd_start = start_date
        max_dd_end = start_date
        current_peak_date = start_date
        for i, v in enumerate(vals):
            if v >= peak:
                peak = v
                current_peak_date = dates[i]
            dd = (v - peak) / peak  # negative
            dd_data.append([dates[i], dd])
            if abs(dd) > max_dd:
                max_dd = abs(dd)
                max_dd_start = current_peak_date
                max_dd_end = dates[i]

        current_dd = abs(dd_data[-1][1]) if dd_data else 0

        # 胜率
        pos_days = sum(1 for r in returns if r > 0)
        neg_days = sum(1 for r in returns if r < 0)
        win_rate = pos_days / max(pos_days + neg_days, 1)

        # 最大单日涨跌
        max_up = max(returns) if returns else 0
        max_up_date = dates[returns.index(max_up) + 1] if returns else ''
        max_down = min(returns) if returns else 0
        max_down_date = dates[returns.index(max_down) + 1] if returns else ''

        # YTD / 周 / 月
        ytd_ret = c.get('ytd_return', 0) or 0
        week_ret = c.get('week_return', 0) or 0
        month_ret = c.get('month_return', 0) or 0

        # 月度收益
        monthly_map = defaultdict(list)
        for i in range(1, len(vals)):
            month_key = dates[i][:7]
            monthly_map[month_key].append(vals[i] / vals[i-1] - 1)
        # 按月累计
        monthly_returns = []
        prev_month_end = None
        month_keys = sorted(monthly_map.keys())
        for mk in month_keys:
            # 找该月最后一个净值
            month_vals = [(dates[i], vals[i]) for i in range(len(dates)) if dates[i][:7] == mk]
            if not month_vals:
                continue
            month_end_nav = month_vals[-1][1]
            # 找上月末净值
            month_start_nav = None
            for i in range(len(dates)):
                if dates[i][:7] == mk:
                    month_start_nav = vals[i-1] if i > 0 else vals[0]
                    break
            if month_start_nav and month_start_nav > 0:
                monthly_returns.append({'month': mk, 'return': month_end_nav / month_start_nav - 1})

        calmar = ann_ret / max_dd if max_dd > 0 else 0

        nav_data = [[d, v] for d, v in zip(dates, vals)]

        fof_list.append({
            'name': c['name'],
            'combi_id': c['id'],
            'start_date': start_date,
            'end_date': end_date,
            'latest_nav': latest_nav,
            'run_days': run_days,
            'total_ret': total_ret,
            'ann_ret': ann_ret,
            'ann_vol': ann_vol,
            'sharpe': sharpe,
            'max_dd': max_dd,
            'dd_period': f"{max_dd_start} ~ {max_dd_end}",
            'current_dd': current_dd,
            'calmar': calmar,
            'win_rate': win_rate,
            'pos_days': pos_days,
            'neg_days': neg_days,
            'max_up': max_up,
            'max_up_date': max_up_date,
            'max_down': max_down,
            'max_down_date': max_down_date,
            'ytd_ret': ytd_ret,
            'week_ret': week_ret,
            'month_ret': month_ret,
            'monthly_returns': monthly_returns,
            'nav_data': nav_data,
            'dd_data': dd_data,
        })

    return fof_list


def save_csv_incremental(products, combis, update_date):
    """增量追加 CSV（产品 + FOF 各一张表）"""
    import csv

    # --- 产品净值快照 ---
    prod_csv = os.path.join(DATA_DIR, 'products_history.csv')
    prod_fields = ['date', 'code', 'name', 'strategy', 'strategy_detail',
                   'latest_date', 'latest_cum_nav', 'week_return', 'month_return', 'ytd_return', 'status']
    write_header = not os.path.exists(prod_csv)
    with open(prod_csv, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=prod_fields)
        if write_header:
            w.writeheader()
        for p in products:
            w.writerow({
                'date': update_date,
                'code': p.get('code', ''),
                'name': p.get('name', ''),
                'strategy': p.get('group', ''),
                'strategy_detail': p.get('detail', ''),
                'latest_date': p.get('latest_date', ''),
                'latest_cum_nav': p.get('latest_cum_nav', ''),
                'week_return': p.get('week_return', ''),
                'month_return': p.get('month_return', ''),
                'ytd_return': p.get('ytd_return', ''),
                'status': p.get('status', ''),
            })
    print(f" CSV追加: {prod_csv} (+{len(products)} 行)")

    # --- FOF 组合快照 ---
    fof_csv = os.path.join(DATA_DIR, 'fof_history.csv')
    fof_fields = ['date', 'combi_id', 'name', 'latest_nav', 'total_ret', 'ann_ret',
                  'ann_vol', 'sharpe', 'max_dd', 'calmar', 'ytd_ret', 'week_ret', 'month_ret']
    write_header = not os.path.exists(fof_csv)
    with open(fof_csv, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fof_fields)
        if write_header:
            w.writeheader()
        for c in combis:
            w.writerow({
                'date': update_date,
                'combi_id': c.get('code', c.get('id', '')),
                'name': c.get('name', ''),
                'latest_nav': c.get('latest_cum_nav', ''),
                'total_ret': c.get('total_return', ''),
                'ann_ret': c.get('ann_return', ''),
                'ann_vol': c.get('ann_vol', ''),
                'sharpe': c.get('sharpe', ''),
                'max_dd': c.get('max_dd', ''),
                'calmar': c.get('calmar', ''),
                'ytd_ret': c.get('ytd_return', ''),
                'week_ret': c.get('week_return', ''),
                'month_ret': c.get('month_return', ''),
            })
    print(f" CSV追加: {fof_csv} (+{len(combis)} 行)")


def save_data(products, combis, market_annual, market_monthly, market_quarterly, benchmark_navs=None):
    """保存所有数据到 JSON + CSV（增量）"""
    from config import STRATEGY_BENCHMARK
    os.makedirs(RAW_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y%m%d')
    update_date = datetime.now().strftime('%Y-%m-%d')

    strategy_summary = build_strategy_summary(products, combis)
    fof_combis = build_fof_combis(combis)

    # 构建 navHistory（code → [[date, nav], ...]），hidden 的不进前端
    nav_history = {}
    for p in products + combis:
        if p.get('hidden'):
            continue
        code = p.get('code', '')
        raw_navs = p.get('_raw_navs', [])
        if code and raw_navs:
            sorted_navs = sorted(raw_navs, key=lambda x: x[0])
            nav_history[code] = [[d, v] for d, v in sorted_navs]

    # 主数据文件
    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy_summary': strategy_summary,
        'market_data': {
            'annual': market_annual,
            'monthly': market_monthly,
            'quarterly': market_quarterly,
        },
        'fof_combis': fof_combis,
        'nav_history': nav_history,
        'benchmark_navs': benchmark_navs or {},
        'strategy_benchmark': {str(k): v for k, v in STRATEGY_BENCHMARK.items()},
    }

    # 保存带日期版本（JSON 快照）
    dated_path = os.path.join(RAW_DIR, f'fund_asset_{today}.json')
    with open(dated_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f" JSON快照: {dated_path}")

    # 保存 latest 版本（渲染用，覆盖）
    latest_path = os.path.join(DATA_DIR, 'fund_asset_latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f" JSON最新: {latest_path}")

    # JSONL 增量追加（一行一天，方便程序读取历史）
    jsonl_path = os.path.join(DATA_DIR, 'fund_asset_history.jsonl')
    with open(jsonl_path, 'a', encoding='utf-8') as f:
        compact = {
            'date': update_date,
            'update_time': output['update_time'],
            'products': [{k: v for k, v in item.items() if k != '_raw_navs'}
                         for group in strategy_summary for item in group.get('items', [])],
            'fof_combis': [{k: v for k, v in fc.items() if k not in ('nav_data', 'dd_data', 'monthly_returns')}
                           for fc in fof_combis],
        }
        f.write(json.dumps(compact, ensure_ascii=False) + '\n')
    print(f" JSONL追加: {jsonl_path}")

    # CSV 增量追加
    save_csv_incremental(products, combis, update_date)

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

    # 4. 基准指数净值
    benchmark_navs = fetch_benchmark_indices()

    # 5. 保存
    output = save_data(products, combis, annual, monthly, quarterly, benchmark_navs)

    # 统计
    ok_count = sum(1 for p in products + combis if p.get('status') == '正常')
    total = len(products) + len(combis)
    print(f"\n 完成: {ok_count}/{total} 只产品有数据")

    return output


if __name__ == '__main__':
    main()
