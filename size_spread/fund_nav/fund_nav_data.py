#!/usr/bin/env python3
"""基金净值模块 - 拉取产品净值 + 基准指数，计算超额"""
import os, sys, json, time
sys.path.insert(0, '/tmp/fof99_pkg')

from fof99 import FundCompanyPrice, FundPrice
from fof99.requests.indexrequest import IndexPrice

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, 'cache')
OUTPUT = os.path.join(BASE, 'fund_nav.json')
os.makedirs(CACHE, exist_ok=True)

APPID = 'hfnogbr8zceiiygdkhw'
APPKEY = 'c6e941fd6aad65ceede2d780262d11ee'

# 产品配置：每个tab一只代表性产品
FUNDS = [
    {
        'tab': 'quant-stock',
        'name': '超量子中证1000增强9号A类',
        'reg_code': 'XZ916A',
        'benchmark': '000852',
        'benchmark_name': '中证1000',
        'start_date': '2024-01-01',
    },
]


def fetch_fund_nav(reg_code, start_date):
    """先试团队净值，再试平台净值"""
    req = FundCompanyPrice(APPID, APPKEY)
    req.set_params(reg_code=reg_code, start_date=start_date, order_by='price_date', order=1)
    res = req.do_request()
    if res and len(res) > 0:
        return res, 'company'
    req2 = FundPrice(APPID, APPKEY)
    req2.set_params(reg_code=reg_code, start_date=start_date, order_by='price_date', order=1)
    res2 = req2.do_request()
    return (res2 or []), 'platform'


def fetch_index(reg_code, start_date):
    req = IndexPrice(APPID, APPKEY)
    req.set_params(reg_code=reg_code, start_date=start_date, end_date='2026-12-31', order_by='price_date', order=1)
    return req.do_request() or []


def align_and_calc(fund_data, index_data):
    """对齐日期，归一化，计算超额"""
    idx_map = {r['price_date']: r['nav'] for r in index_data}

    dates = []
    fund_navs = []
    idx_navs = []

    for r in fund_data:
        d = r['price_date']
        cum = r.get('cumulative_nav') or r.get('cumulative_nav_withdrawal') or r['nav']
        # 找最近的指数日期（产品是周频，指数是日频）
        idx_val = idx_map.get(d)
        if not idx_val:
            # 往前找最近3天
            from datetime import datetime, timedelta
            dt = datetime.strptime(d, '%Y-%m-%d')
            for offset in range(1, 5):
                prev = (dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                if prev in idx_map:
                    idx_val = idx_map[prev]
                    break
        if idx_val is None:
            continue

        dates.append(d)
        fund_navs.append(float(cum))
        idx_navs.append(float(idx_val))

    if not dates:
        return None

    # 归一化到1
    f0 = fund_navs[0]
    i0 = idx_navs[0]
    fund_norm = [round(v / f0, 6) for v in fund_navs]
    idx_norm = [round(v / i0, 6) for v in idx_navs]
    excess = [round(f - i, 6) for f, i in zip(fund_norm, idx_norm)]

    return {
        'dates': dates,
        'fund_nav': fund_norm,
        'index_nav': idx_norm,
        'excess': excess,
        'fund_raw': fund_navs,
        'index_raw': idx_navs,
    }


def main():
    result = {
        'update_time': time.strftime('%Y-%m-%d %H:%M'),
        'funds': [],
    }

    for cfg in FUNDS:
        print(f"拉取 {cfg['name']} ({cfg['reg_code']})...")
        fund_data, source = fetch_fund_nav(cfg['reg_code'], cfg['start_date'])
        print(f"  产品净值: {len(fund_data)} 条 (source={source})")

        time.sleep(0.5)
        idx_data = fetch_index(cfg['benchmark'], cfg['start_date'])
        print(f"  基准指数: {len(idx_data)} 条")

        aligned = align_and_calc(fund_data, idx_data)
        if not aligned:
            print(f"  ⚠️ 对齐失败")
            continue

        latest_fund = aligned['fund_nav'][-1]
        latest_idx = aligned['index_nav'][-1]
        latest_excess = aligned['excess'][-1]
        total_ret = (latest_fund - 1) * 100
        idx_ret = (latest_idx - 1) * 100
        excess_ret = latest_excess * 100

        entry = {
            'tab': cfg['tab'],
            'name': cfg['name'],
            'reg_code': cfg['reg_code'],
            'benchmark_name': cfg['benchmark_name'],
            'source': source,
            'count': len(aligned['dates']),
            'date_range': f"{aligned['dates'][0]} ~ {aligned['dates'][-1]}",
            'total_return': round(total_ret, 2),
            'index_return': round(idx_ret, 2),
            'excess_return': round(excess_ret, 2),
            'chart': aligned,
        }
        result['funds'].append(entry)
        print(f"  ✅ 产品{total_ret:+.1f}% 基准{idx_ret:+.1f}% 超额{excess_ret:+.1f}%")

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"\n输出: {OUTPUT}")


if __name__ == '__main__':
    main()
