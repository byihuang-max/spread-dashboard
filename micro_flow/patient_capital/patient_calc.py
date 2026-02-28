#!/usr/bin/env python3
"""耐心资本 - 计算模块
基线分离 → 买卖判定 → 滚动成本 → 输出 CSV + JSON
"""
import json, csv, os, sys
from pathlib import Path
from collections import defaultdict
from statistics import median

import requests

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / 'raw_15min'
CSV_OUT = BASE_DIR / 'patient_capital.csv'
JSON_OUT = BASE_DIR / 'patient_capital.json'

# Tushare 配置
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TS_API = 'http://api.tushare.pro'

# 和 patient_data.py 保持一致
INDEX_ETFS = {
    '沪深300':   ['510300.SH', '159919.SZ'],
    '上证50':    ['510050.SH'],
    '创业板指':   ['159915.SZ'],
    '科创50':    ['588080.SH'],
    '创业板50':   ['159949.SZ'],
    '中证1000':  ['512100.SH', '159845.SZ', '560010.SH'],
    '中证500':   ['510500.SH', '512500.SH'],
    '中证A500':  ['159338.SZ', '159352.SZ', '159353.SZ', '560530.SH',
                  '159339.SZ', '563800.SH', '512050.SH', '159361.SZ'],
}

BASELINE_WINDOW = 20  # 基线窗口：20个交易日
ABNORMAL_THRESHOLD = 1.5  # 超过基线1.5倍视为异常

# 指数名称 → Tushare 指数代码（用于拉日线算折算系数）
INDEX_TS_CODE = {
    '沪深300':  '399300.SZ',
    '上证50':   '000016.SH',
    '创业板指':  '399006.SZ',
    '科创50':   '000688.SH',
    '创业板50':  '399673.SZ',
    '中证1000': '000852.SH',
    '中证500':  '000905.SH',
    '中证A500': '932000.CSI',
}


def fetch_index_daily(ts_code, start_date='20230701'):
    """从 Tushare 拉取指数日线收盘价"""
    print(f"  拉取指数日线 {ts_code}...", end='', flush=True)
    resp = requests.post(TS_API, json={
        'api_name': 'index_daily',
        'token': TS_TOKEN,
        'params': {'ts_code': ts_code, 'start_date': start_date, 'fields': 'trade_date,close'},
    }, timeout=30)
    data = resp.json()
    items = data.get('data', {}).get('items', [])
    fields = data.get('data', {}).get('fields', [])
    if not items:
        print(f" 无数据")
        return {}
    di = {f: i for i, f in enumerate(fields)}
    result = {}
    for row in items:
        result[row[di['trade_date']]] = row[di['close']]
    print(f" {len(result)}天")
    return result


def fetch_all_index_daily():
    """拉取所有跟踪指数的日线数据"""
    all_idx = {}
    for name, ts_code in INDEX_TS_CODE.items():
        all_idx[name] = fetch_index_daily(ts_code)
    return all_idx


def load_all_cache():
    """加载所有缓存的15min数据，按日期排序"""
    all_data = {}
    for f in sorted(CACHE_DIR.glob('*.json')):
        date_str = f.stem
        with open(f) as fh:
            all_data[date_str] = json.load(fh)
    return all_data


def aggregate_index_bars(day_data, index_name, etf_codes):
    """
    将同一指数下多只ETF的15min bar按时间聚合。
    返回: [{time, open, close, vol, amount}, ...] 按时间排序
    """
    # 收集所有bar，按时间分组
    time_buckets = defaultdict(lambda: {'vol': 0.0, 'amount': 0.0, 'opens': [], 'closes': []})

    for code in etf_codes:
        bars = day_data.get(code, [])
        for bar in bars:
            t = bar['trade_time']
            b = time_buckets[t]
            b['vol'] += bar.get('vol', 0) or 0
            b['amount'] += bar.get('amount', 0) or 0
            if bar.get('open'):
                b['opens'].append(bar['open'])
            if bar.get('close'):
                b['closes'].append(bar['close'])

    # 转换为列表
    result = []
    for t in sorted(time_buckets.keys()):
        b = time_buckets[t]
        if not b['opens'] or not b['closes']:
            continue
        result.append({
            'time': t,
            'open': sum(b['opens']) / len(b['opens']),    # 均价（用于方向判断）
            'close': sum(b['closes']) / len(b['closes']),
            'vol': b['vol'],
            'amount': b['amount'],
        })
    return result


def extract_time_slot(trade_time):
    """提取时间段标识，如 '09:45' """
    return trade_time.split(' ')[1][:5]


def compute_patient_capital(all_data, index_name, etf_codes, index_daily=None):
    """
    计算单个指数的耐心资本持仓。
    index_daily: {date_str: index_close} 对应指数的日线收盘价
    返回日级别列表: [{date, buy, sell, net, cum, cost, close, pnl, bars, idx_close, cost_idx}, ...]
    """
    dates = sorted(all_data.keys())

    # 第一步：构建每日的聚合bar数据
    daily_bars = {}
    for d in dates:
        bars = aggregate_index_bars(all_data[d], index_name, etf_codes)
        if bars:
            daily_bars[d] = bars

    if not daily_bars:
        return []

    # 第二步：构建基线（滚动20日同时段成交额中位数）
    sorted_dates = sorted(daily_bars.keys())

    # 收集每个时段的历史成交额
    slot_history = defaultdict(list)  # slot -> [(date, amount)]

    # 第三步：逐日计算
    cum_buy_amount = 0.0    # 累计买入金额
    cum_buy_shares = 0.0    # 累计买入股数
    cum_sell_shares = 0.0   # 累计卖出股数
    cum_net_amount = 0.0    # 累计净持仓额
    cost_price = 0.0        # 持仓成本

    results = []

    for di, date in enumerate(sorted_dates):
        bars = daily_bars[date]
        day_buy = 0.0
        day_sell = 0.0
        abnormal_count = 0

        for bar in bars:
            slot = extract_time_slot(bar['time'])
            amount = bar['amount']

            # 计算该时段基线
            history = slot_history.get(slot, [])
            # 取最近BASELINE_WINDOW天的数据
            recent = [h[1] for h in history[-BASELINE_WINDOW:]]

            if len(recent) >= 5:  # 至少5天数据才计算基线
                baseline = median(recent)
                excess = amount - baseline * ABNORMAL_THRESHOLD

                if excess > 0:
                    abnormal_count += 1
                    # 用bar的均价估算
                    avg_price = (bar['open'] + bar['close']) / 2
                    excess_shares = excess / avg_price if avg_price > 0 else 0

                    if bar['close'] >= bar['open']:
                        # 阳线 → 买入
                        day_buy += excess
                        cum_buy_amount += excess
                        cum_buy_shares += excess_shares
                    else:
                        # 阴线 → 卖出
                        day_sell += excess
                        cum_sell_shares += excess_shares

            # 更新历史（无论是否异常）
            slot_history[slot].append((date, amount))

        # 计算持仓成本（均价法）
        net_shares = cum_buy_shares - cum_sell_shares
        if net_shares > 0 and cum_buy_shares > 0:
            cost_price = cum_buy_amount / cum_buy_shares  # 买入均价
        elif net_shares <= 0:
            cost_price = 0
            net_shares = 0

        # 当日收盘价（用最后一根bar的close均价）
        close_price = bars[-1]['close'] if bars else 0

        # 累计净持仓额 = 净股数 × 当日收盘价
        cum_position = net_shares * close_price

        # 浮盈亏
        pnl = ((close_price - cost_price) / cost_price * 100) if cost_price > 0 else 0

        day_net = day_buy - day_sell

        # 折算指数点位
        idx_close = None
        cost_idx = None
        if index_daily and date in index_daily and close_price > 0:
            idx_close = index_daily[date]
            ratio = idx_close / close_price  # 折算系数
            if cost_price > 0:
                cost_idx = round(cost_price * ratio, 2)

        results.append({
            'date': date,
            'buy': round(day_buy / 1e8, 4),       # 亿
            'sell': round(day_sell / 1e8, 4),
            'net': round(day_net / 1e8, 4),
            'cum': round(cum_position / 1e8, 2),   # 亿
            'cost': round(cost_price, 4),
            'close': round(close_price, 4),
            'pnl': round(pnl, 2),
            'bars': abnormal_count,
            'idx_close': round(idx_close, 2) if idx_close else None,
            'cost_idx': cost_idx,
        })

    return results


def run():
    """主计算流程"""
    print("加载缓存数据...")
    all_data = load_all_cache()
    if not all_data:
        print("[ERR] 无缓存数据，请先运行 patient_data.py", file=sys.stderr)
        sys.exit(1)

    print(f"已加载 {len(all_data)} 个交易日")

    print("\n拉取指数日线（用于折算指数点位）...")
    all_index_daily = fetch_all_index_daily()

    all_results = {}
    for index_name, etf_codes in INDEX_ETFS.items():
        print(f"  计算 {index_name} ({len(etf_codes)} ETFs)...", end='', flush=True)
        idx_daily = all_index_daily.get(index_name, {})
        results = compute_patient_capital(all_data, index_name, etf_codes, idx_daily)
        if results:
            all_results[index_name] = results
            latest = results[-1]
            cost_idx_str = f", 成本指数位: {latest['cost_idx']}" if latest.get('cost_idx') else ""
            print(f" {len(results)} 天, 最新累计: {latest['cum']}亿, 成本: {latest['cost']}{cost_idx_str}, 浮盈: {latest['pnl']}%")
        else:
            print(" 无数据")

    # ═══ 输出 CSV ═══
    print(f"\n写入 CSV: {CSV_OUT}")
    with open(CSV_OUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'index_name', 'daily_buy_amt', 'daily_sell_amt',
                         'daily_net_amt', 'cum_position', 'cost_price', 'close_price',
                         'pnl_pct', 'abnormal_bars', 'idx_close', 'cost_idx'])
        for index_name, results in all_results.items():
            for r in results:
                writer.writerow([
                    r['date'], index_name, r['buy'], r['sell'], r['net'],
                    r['cum'], r['cost'], r['close'], r['pnl'], r['bars'],
                    r.get('idx_close', ''), r.get('cost_idx', '')
                ])

    # ═══ 输出 JSON ═══
    print(f"写入 JSON: {JSON_OUT}")
    from datetime import datetime
    json_data = {
        'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'indices': {}
    }
    for index_name, results in all_results.items():
        json_data['indices'][index_name] = {
            'etfs': INDEX_ETFS[index_name],
            'daily': results,
            'latest': results[-1] if results else None,
        }

    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("完成！")


if __name__ == '__main__':
    run()
