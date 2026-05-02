#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略分类月度累计收益曲线构造器
=================================
数据来源：火富牛 /market/category API（type=2 月度）
原理：
  1. 对每个月末日期调用 API，获取 16 个策略分类的月度收益均值（mean）
  2. 拉取对应基准指数的月末收盘价，计算月度收益率
  3. 将月度收益串成累计收益曲线（策略 / 基准 / 超额）
  4. 输出 strategy_curves.json，供 render_html.py 注入前端弹窗

输出格式：
  {
    "update_time": "2026-04-28 15:00",
    "curves": {
      "8": {  // 策略分类 id（字符串）
        "name": "300指增",
        "benchmark_name": "沪深300",
        "dates": ["2024-04-01", "2024-04-30", ...],  // 首项为起始零点
        "strategy_return": [0.0, 2.3, ...],           // 累计收益率 %
        "benchmark_return": [0.0, 1.5, ...],          // 基准累计收益率 %（无基准时为 null）
        "excess": [0.0, 0.8, ...],                    // 超额 %（无基准时为 null）
        "total_return": 44.2,
        "index_return": 23.5,
        "excess_return": 20.7
      }, ...
    }
  }

使用方式：
  python3 fetch_strategy_curves.py
  （通常由 update_all.py 在 fetch_data.py 之后调用）
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from mall_sdk.fof99 import MarketCategory
from mall_sdk.fof99.requests.indexrequest import IndexPrice
from config import APP_ID, APP_KEY

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
OUTPUT = os.path.join(DATA_DIR, 'strategy_curves.json')

# ========== 策略分类 → 基准指数映射 ==========
# id 对应火富牛 /market/category 的策略分类 id
# benchmark=None 表示该策略只展示绝对收益，不比基准
STRATEGY_BENCHMARKS = {
    8:  {'benchmark': '000300', 'benchmark_name': '沪深300'},    # 300指增
    9:  {'benchmark': '000905', 'benchmark_name': '中证500'},    # 500指增
    10: {'benchmark': '000852', 'benchmark_name': '中证1000'},   # 1000指增
    7:  {'benchmark': '000300', 'benchmark_name': '沪深300'},    # 主观多头
    6:  {'benchmark': '000300', 'benchmark_name': '沪深300'},    # 股票多头
    16: {'benchmark': '000832', 'benchmark_name': '中证转债'},   # 可转债多头
    5:  {'benchmark': None,     'benchmark_name': None},         # 股票市场中性（绝对收益）
    4:  {'benchmark': None,     'benchmark_name': None},         # 股票对冲（绝对收益）
    11: {'benchmark': None,     'benchmark_name': None},         # 套利策略（绝对收益）
    12: {'benchmark': None,     'benchmark_name': None},         # 期权策略（绝对收益）
    15: {'benchmark': 'H11001', 'benchmark_name': '中证全债'},   # 债券策略
    2:  {'benchmark': 'NHCI',   'benchmark_name': '南华商品'},   # 量化期货
    3:  {'benchmark': 'NHCI',   'benchmark_name': '南华商品'},   # 主观期货
    13: {'benchmark': None,     'benchmark_name': None},         # 多资产策略（绝对收益）
    14: {'benchmark': None,     'benchmark_name': None},         # 组合策略（绝对收益）
}

# ========== 月末日期列表 ==========
# 往前拉 24 个月，覆盖 2 年完整周期
# 注意：火富牛 API 的 end_date 参数决定返回哪个月的数据
END_DATES = [
    '2024-04-30','2024-05-31','2024-06-30','2024-07-31','2024-08-31','2024-09-30',
    '2024-10-31','2024-11-30','2024-12-31',
    '2025-01-31','2025-02-28','2025-03-31','2025-04-30','2025-05-31','2025-06-30',
    '2025-07-31','2025-08-31','2025-09-30','2025-10-31','2025-11-30','2025-12-31',
    '2026-01-31','2026-02-28','2026-03-31',
]


def fetch_monthly_returns():
    """
    拉取所有 16 个策略分类的月度收益均值。
    对每个 end_date 调用一次 API（type=2 表示月度），
    返回 {strategy_id: {name, months: [{trade_date, mean}]}}
    """
    all_ids = ','.join(str(i) for i in STRATEGY_BENCHMARKS.keys())
    results = {}  # {strategy_id: {name, months: [{trade_date, mean}]}}

    print(f" 拉取 {len(END_DATES)} 个月的策略月度收益...")
    for ed in END_DATES:
        req = MarketCategory(APP_ID, APP_KEY)
        req.set_params(ids=all_ids, _type=2, end_date=ed)
        data = req.do_request()
        if data:
            for item in data:
                sid = item['id']
                ret = item.get('return', {})
                td = ret.get('trade_date', '')
                mean = ret.get('mean', 0)
                if sid not in results:
                    results[sid] = {'name': item['name'], 'months': []}
                # Deduplicate by trade_date
                existing = {m['trade_date'] for m in results[sid]['months']}
                if td and td not in existing:
                    results[sid]['months'].append({'trade_date': td, 'mean': mean or 0})
        time.sleep(0.3)

    for sid in results:
        results[sid]['months'].sort(key=lambda x: x['trade_date'])
        print(f"  {results[sid]['name']} (id={sid}): {len(results[sid]['months'])} 个月")

    return results


def fetch_index_monthly(code, dates):
    """
    拉取基准指数的日频净值，提取月末收盘价，计算月度收益率。
    由于月末可能非交易日，会往前找最近 7 天的交易日数据。
    返回 [{trade_date, return}] 或 None
    """
    if not code:
        return None

    req = IndexPrice(APP_ID, APP_KEY)
    start = dates[0][:8] + '01'  # 从第一个月初开始
    req.set_params(reg_code=code, start_date=start)
    data = req.do_request()
    if not data:
        return None

    # Build date→nav map
    nav_map = {r['price_date']: r['nav'] for r in data}

    # For each month-end date, find closest nav
    monthly_navs = []
    for td in dates:
        nav = nav_map.get(td)
        if not nav:
            from datetime import datetime, timedelta
            dt = datetime.strptime(td, '%Y-%m-%d')
            for offset in range(1, 8):
                prev = (dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                if prev in nav_map:
                    nav = nav_map[prev]
                    break
        if nav:
            monthly_navs.append({'trade_date': td, 'nav': float(nav)})

    if len(monthly_navs) < 2:
        return None

    # Calculate monthly returns
    returns = []
    for i in range(1, len(monthly_navs)):
        prev = monthly_navs[i-1]['nav']
        curr = monthly_navs[i]['nav']
        ret = (curr / prev) - 1
        returns.append({'trade_date': monthly_navs[i]['trade_date'], 'return': ret})

    return returns


def build_curves(strategy_returns, index_returns_cache):
    """
    构造累计收益曲线。
    策略累计收益 = 连乘月度收益均值（从 1.0 开始）
    基准累计收益 = 连乘基准月度收益率
    超额 = 策略累计 - 基准累计（百分比差值）
    dates 首项为起始零点（第一个月的月初），后续为各月末
    """
    curves = {}

    for sid, sdata in strategy_returns.items():
        months = sdata['months']
        if len(months) < 2:
            continue

        bm = STRATEGY_BENCHMARKS.get(sid, {})
        bm_code = bm.get('benchmark')
        bm_name = bm.get('benchmark_name')

        # Strategy cumulative return
        dates = [m['trade_date'] for m in months]
        strat_cum = [0.0]  # start at 0%
        nav = 1.0
        for m in months:
            nav *= (1 + m['mean'])
            strat_cum.append((nav - 1) * 100)

        # Benchmark cumulative return
        bm_cum = None
        if bm_code and bm_code in index_returns_cache:
            idx_rets = index_returns_cache[bm_code]
            idx_map = {r['trade_date']: r['return'] for r in idx_rets}
            bm_nav = 1.0
            bm_cum = [0.0]
            for m in months:
                td = m['trade_date']
                idx_ret = idx_map.get(td, 0)
                bm_nav *= (1 + idx_ret)
                bm_cum.append((bm_nav - 1) * 100)

        # Excess
        excess = None
        if bm_cum and len(bm_cum) == len(strat_cum):
            excess = [round(s - b, 4) for s, b in zip(strat_cum, bm_cum)]

        # Dates: prepend a "start" date (one month before first)
        from datetime import datetime
        first_dt = datetime.strptime(dates[0], '%Y-%m-%d')
        start_label = (first_dt.replace(day=1)).strftime('%Y-%m-%d')
        all_dates = [start_label] + dates

        curves[str(sid)] = {
            'name': sdata['name'],
            'benchmark_name': bm_name,
            'dates': all_dates,
            'strategy_return': [round(v, 2) for v in strat_cum],
            'benchmark_return': [round(v, 2) for v in bm_cum] if bm_cum else None,
            'excess': [round(v, 2) for v in excess] if excess else None,
            'total_return': round(strat_cum[-1], 2),
            'index_return': round(bm_cum[-1], 2) if bm_cum else None,
            'excess_return': round(excess[-1], 2) if excess else None,
        }

    return curves


def main():
    # 1. Fetch strategy monthly returns
    strategy_returns = fetch_monthly_returns()

    # 2. Fetch benchmark index monthly returns
    all_dates = set()
    for sdata in strategy_returns.values():
        for m in sdata['months']:
            all_dates.add(m['trade_date'])
    all_dates = sorted(all_dates)

    bm_codes = set()
    for bm in STRATEGY_BENCHMARKS.values():
        if bm.get('benchmark'):
            bm_codes.add(bm['benchmark'])

    print(f"\n 拉取 {len(bm_codes)} 只基准指数...")
    index_cache = {}
    for code in sorted(bm_codes):
        rets = fetch_index_monthly(code, all_dates)
        if rets:
            index_cache[code] = rets
            print(f"   {code}: {len(rets)} 个月")
        else:
            print(f"  ⚠ {code}: 无数据")
        time.sleep(0.3)

    # 3. Build curves
    curves = build_curves(strategy_returns, index_cache)

    # 4. Save
    output = {
        'update_time': time.strftime('%Y-%m-%d %H:%M'),
        'curves': curves,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"\n 输出: {OUTPUT}")
    for sid, c in sorted(curves.items(), key=lambda x: int(x[0])):
        ex = f"超额{c['excess_return']:+.1f}%" if c['excess_return'] is not None else "无基准"
        print(f"  {c['name']:10s} 策略{c['total_return']:+.1f}% {ex} ({len(c['dates'])}点)")


if __name__ == '__main__':
    main()
