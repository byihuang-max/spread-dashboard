#!/usr/bin/env python3
"""
昨日涨停指数 & 昨日首板指数（CSV增量模式）
─────────────────────────────────────────────
逻辑：
  假设 T-1 日收盘时等权买入所有涨停（或首板）股票，
  T 日收盘卖出，计算当日组合收益率，逐日累计成净值曲线。

核心指标：
  1. 净值曲线（长期应斜向上，正期望）
  2. 乖离率 BIAS = (净值 - MA) / MA × 100
     → 过高 = 涨停股被过度追捧，拥挤警告
     → 过低 = 情绪冰点，潜在反转
  3. 高低开 = 组合平均 (open - pre_close) / pre_close × 100
     → 隔夜溢价/折价，反映市场对涨停股的预期

增量策略：
  - limit_index.csv 存完整历史
  - 每次只计算 CSV 中没有的新日期
  - 从已有 CSV 读取最新净值继续累计
  - 最后输出 limit_index.json（供前端注入）

数据源：
  - ../_cache/{date}.json → T-1 日涨停/首板股票代码
  - Tushare daily API → T 日的 open / close / pre_close
"""

import json
import os
import sys
import csv
import time
import requests
from datetime import datetime

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)  # momentum_stock/
LIMIT_CACHE_DIR = os.path.join(PARENT_DIR, '_cache')  # 涨停缓存（上级目录）
OUTPUT_JSON = os.path.join(BASE_DIR, 'limit_index.json')
OUTPUT_CSV = os.path.join(BASE_DIR, 'limit_index.csv')
DAILY_CACHE_DIR = os.path.join(BASE_DIR, '_cache_daily')  # 全市场日线缓存

os.makedirs(DAILY_CACHE_DIR, exist_ok=True)

MA_PERIOD = 20   # 乖离率均线周期

CSV_HEADERS = [
    'date', 'limit_date',
    'all_count', 'all_valid', 'all_return', 'all_gap', 'all_nav', 'all_bias',
    'first_count', 'first_valid', 'first_return', 'first_gap', 'first_nav', 'first_bias',
]


def log(msg):
    print(msg, flush=True)


# ═══ Tushare API ═══

def tushare_call(api_name, params, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': ''
            }, timeout=30, proxies={'http': None, 'https': None})
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return [dict(zip(cols, row)) for row in data['data']['items']]
            if data.get('code') == -2002:
                log(f"  ⏳ Tushare 限频，等待 10s...")
                time.sleep(10)
                continue
            return []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
            else:
                log(f"  ❌ API失败: {e}")
    return []


def get_daily_market(trade_date, needed_codes=None):
    """获取某日日线数据（带缓存）→ {ts_code: {open, close, pre_close, pct_chg}}"""
    cache_file = os.path.join(DAILY_CACHE_DIR, f'{trade_date}.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    log(f"  🌐 拉取 {trade_date} 全市场日线...")
    rows = tushare_call('daily', {'trade_date': trade_date})

    if rows:
        result = {}
        for r in rows:
            result[r['ts_code']] = {
                'open': r.get('open'),
                'close': r.get('close'),
                'pre_close': r.get('pre_close'),
                'pct_chg': r.get('pct_chg'),
            }
        with open(cache_file, 'w') as f:
            json.dump(result, f)
        return result

    if not needed_codes:
        return {}

    log(f"  📦 全市场失败，逐股拉 {len(needed_codes)} 只...")
    result = {}
    for code in needed_codes:
        rows = tushare_call('daily', {
            'ts_code': code,
            'start_date': trade_date,
            'end_date': trade_date,
        })
        if rows:
            r = rows[0]
            result[r['ts_code']] = {
                'open': r.get('open'),
                'close': r.get('close'),
                'pre_close': r.get('pre_close'),
                'pct_chg': r.get('pct_chg'),
            }
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    return result


# ═══ 涨停股缓存读取 ═══

def get_limit_stocks(trade_date):
    """从上级 _cache 获取 T 日涨停股代码，区分全部涨停 vs 首板"""
    cache_file = os.path.join(LIMIT_CACHE_DIR, f'{trade_date}.json')
    if not os.path.exists(cache_file):
        return [], []

    with open(cache_file) as f:
        data = json.load(f)

    ups = data.get('U', [])
    if not ups:
        return [], []

    all_limit_codes = []
    first_board_codes = []

    for u in ups:
        code = u.get('ts_code', '')
        if not code:
            continue
        all_limit_codes.append(code)
        if u.get('limit_times', 1) == 1:
            first_board_codes.append(code)

    return all_limit_codes, first_board_codes


# ═══ 计算工具 ═══

def calc_group_return(codes, daily_market):
    """等权收益率 + 平均高低开 → (avg_return, avg_gap, valid_count, total_count)"""
    returns = []
    gaps = []

    for code in codes:
        stock = daily_market.get(code)
        if not stock:
            continue
        pct = stock.get('pct_chg')
        op = stock.get('open')
        pre = stock.get('pre_close')

        if pct is not None:
            returns.append(pct)
        if op is not None and pre is not None and pre > 0:
            gaps.append((op - pre) / pre * 100)

    if not returns:
        return None, None, 0, len(codes)

    avg_ret = sum(returns) / len(returns)
    avg_gap = sum(gaps) / len(gaps) if gaps else None
    return avg_ret, avg_gap, len(returns), len(codes)


def calc_bias(navs, period=MA_PERIOD):
    """BIAS 乖离率 = (净值 - MA) / MA × 100"""
    n = min(len(navs), period)
    ma = sum(navs[-n:]) / n
    if ma == 0:
        return 0
    return (navs[-1] - ma) / ma * 100


# ═══ CSV 读写 ═══

def read_existing_csv():
    """读取已有 CSV，返回 (records_list, existing_dates_set)"""
    if not os.path.exists(OUTPUT_CSV):
        return [], set()

    records = []
    dates = set()
    with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 数值类型转换
            for k in ['all_count', 'all_valid', 'first_count', 'first_valid']:
                if row.get(k):
                    row[k] = int(row[k])
            for k in ['all_return', 'all_gap', 'all_nav', 'all_bias',
                       'first_return', 'first_gap', 'first_nav', 'first_bias']:
                if row.get(k) and row[k] != '':
                    row[k] = float(row[k])
                else:
                    row[k] = None
            records.append(row)
            dates.add(row['date'])

    return records, dates


def write_csv(records):
    """写入完整 CSV"""
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, '') if r.get(k) is not None else '' for k in CSV_HEADERS})


def write_json(records):
    """写入 JSON（供前端用）"""
    if not records:
        return

    latest = records[-1]
    output = {
        'meta': {
            'date_range': f"{records[0]['date']} ~ {records[-1]['date']}",
            'count': len(records),
            'ma_period': MA_PERIOD,
            'final_nav_all': latest['all_nav'],
            'final_nav_first': latest['first_nav'],
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'daily': records,
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ═══ 主逻辑 ═══

def main():
    log("=" * 60)
    log("昨日涨停/首板指数 - 增量更新")
    log("=" * 60)

    # 读取已有数据
    existing_records, existing_dates = read_existing_csv()
    log(f"📦 已有 CSV: {len(existing_records)} 条记录")

    # 获取所有有涨停缓存的交易日
    cache_dates = sorted([
        f.replace('.json', '') for f in os.listdir(LIMIT_CACHE_DIR)
        if f.endswith('.json') and f[:8].isdigit()
    ])

    if len(cache_dates) < 2:
        log("❌ 涨停缓存不足，至少需要2个交易日")
        return

    log(f"📊 涨停缓存: {cache_dates[0]} ~ {cache_dates[-1]} ({len(cache_dates)}天)")

    # 找出需要新计算的日期对 (t_minus_1, t_day)
    # t_day 是收益计算日，也是 CSV 中的 date 字段
    pairs_to_calc = []
    for i in range(len(cache_dates) - 1):
        t_day = cache_dates[i + 1]
        if t_day not in existing_dates:
            pairs_to_calc.append((cache_dates[i], t_day))

    if not pairs_to_calc:
        log("✅ 无新数据，跳过计算")
        # 仍然输出 JSON（可能 JSON 不存在）
        if existing_records:
            write_json(existing_records)
            log(f"💾 JSON 已更新")
        return

    log(f"🆕 需计算 {len(pairs_to_calc)} 个新交易日")

    # 从已有记录恢复净值状态
    if existing_records:
        nav_all = existing_records[-1]['all_nav']
        nav_first = existing_records[-1]['first_nav']
        nav_all_list = [r['all_nav'] for r in existing_records]
        nav_first_list = [r['first_nav'] for r in existing_records]
    else:
        nav_all = 1.0
        nav_first = 1.0
        nav_all_list = []
        nav_first_list = []

    new_count = 0
    for t_minus_1, t_day in pairs_to_calc:
        all_codes, first_codes = get_limit_stocks(t_minus_1)
        if not all_codes:
            continue

        needed = list(set(all_codes))
        daily_market = get_daily_market(t_day, needed_codes=needed)
        if not daily_market:
            log(f"  ⚠️ {t_day} 无行情数据，跳过")
            continue

        time.sleep(0.3)

        all_ret, all_gap, all_valid, all_total = calc_group_return(all_codes, daily_market)
        first_ret, first_gap, first_valid, first_total = calc_group_return(first_codes, daily_market)

        if all_ret is None:
            continue

        nav_all *= (1 + all_ret / 100)
        nav_first *= (1 + (first_ret or 0) / 100) if first_ret is not None else 1.0

        nav_all_list.append(nav_all)
        nav_first_list.append(nav_first)

        bias_all = calc_bias(nav_all_list) if len(nav_all_list) >= 2 else 0
        bias_first = calc_bias(nav_first_list) if len(nav_first_list) >= 2 else 0

        record = {
            'date': t_day,
            'limit_date': t_minus_1,
            'all_count': all_total,
            'all_valid': all_valid,
            'all_return': round(all_ret, 4),
            'all_gap': round(all_gap, 4) if all_gap is not None else None,
            'all_nav': round(nav_all, 6),
            'all_bias': round(bias_all, 2),
            'first_count': first_total,
            'first_valid': first_valid,
            'first_return': round(first_ret, 4) if first_ret is not None else None,
            'first_gap': round(first_gap, 4) if first_gap is not None else None,
            'first_nav': round(nav_first, 6),
            'first_bias': round(bias_first, 2),
        }
        existing_records.append(record)
        new_count += 1

    # 按日期排序（防止乱序）
    existing_records.sort(key=lambda r: r['date'])

    # 写入 CSV + JSON
    write_csv(existing_records)
    write_json(existing_records)

    log(f"\n✅ 新增 {new_count} 条，总计 {len(existing_records)} 条")
    log(f"📈 全涨停净值: {nav_all:.4f} ({(nav_all-1)*100:+.2f}%)")
    log(f"📈 首板净值:   {nav_first:.4f} ({(nav_first-1)*100:+.2f}%)")

    latest = existing_records[-1]
    log(f"\n最新 ({latest['date']}):")
    log(f"  全涨停: 收益={latest['all_return']:.2f}%, 高低开={latest['all_gap']:.2f}%, BIAS={latest['all_bias']:.2f}%")
    if latest['first_return'] is not None:
        log(f"  首板:   收益={latest['first_return']:.2f}%, 高低开={latest['first_gap']:.2f}%, BIAS={latest['first_bias']:.2f}%")

    log(f"\n💾 CSV: {OUTPUT_CSV}")
    log(f"💾 JSON: {OUTPUT_JSON}")
    log("\n🎉 完成！")


if __name__ == '__main__':
    main()
