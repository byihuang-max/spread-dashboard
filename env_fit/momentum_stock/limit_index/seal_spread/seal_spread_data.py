#!/usr/bin/env python3
"""
涨跌停封单额每日轧差 (Seal Spread)
─────────────────────────────────────────────
逻辑：
  每日统计全市场涨停封单额合计 vs 跌停封单额合计，
  轧差 = 涨停封单额 − 跌停封单额。

核心指标：
  1. seal_spread — 轧差（亿元），正=多头强，负=空头强
  2. seal_ratio  — 涨停封单额占总封单额比例 (0~1)
  3. spread_ma5 / spread_ma20 — 轧差均线
  4. spread_pct_1y — 近250个交易日轧差的分位数
  5. signal — 极度恐慌 / 偏空 / 均衡 / 偏多 / 极度亢奋

抄底逻辑：
  轧差大幅为负 + 分位数 <5% → 恐慌到极致 → 底部信号

增量策略：
  - seal_spread.csv 存完整历史
  - 每次只计算 CSV 中没有的新日期
  - 最后输出 seal_spread.json（供前端注入）

数据源：
  - ../../_cache/{date}.json → U(涨停) / D(跌停) 的 fd_amount
"""

import json
import os
import csv
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIMIT_INDEX_DIR = os.path.dirname(BASE_DIR)        # limit_index/
MOMENTUM_DIR = os.path.dirname(LIMIT_INDEX_DIR)     # momentum_stock/
CACHE_DIR = os.path.join(MOMENTUM_DIR, '_cache')     # 涨停/跌停缓存

OUTPUT_CSV = os.path.join(BASE_DIR, 'seal_spread.csv')
OUTPUT_JSON = os.path.join(BASE_DIR, 'seal_spread.json')

YUAN_TO_YI = 1e8  # 元 → 亿

CSV_HEADERS = [
    'date',
    'up_count', 'up_seal_total',
    'down_count', 'down_seal_total',
    'seal_spread', 'seal_ratio',
    'spread_ma5', 'spread_ma20',
    'spread_pct_1y',
    'signal',
]

PCT_WINDOW = 250   # 分位数滚动窗口（约1年交易日）
MA5 = 5
MA20 = 20

# 信号阈值
SIGNAL_THRESHOLDS = [
    (0.05, '🟢 极度恐慌'),
    (0.20, '🔵 偏空'),
    (0.80, '⚪ 均衡'),
    (0.95, '🟡 偏多'),
    (1.01, '🔴 极度亢奋'),
]


def log(msg):
    print(msg, flush=True)


def get_signal(pct):
    """根据分位数返回信号标签"""
    if pct is None:
        return '⚪ 均衡'
    for threshold, label in SIGNAL_THRESHOLDS:
        if pct < threshold:
            return label
    return '🔴 极度亢奋'


def calc_ma(values, period):
    """计算最近 period 个值的简单均值"""
    n = min(len(values), period)
    if n == 0:
        return None
    return sum(values[-n:]) / n


def calc_percentile(values, current, window):
    """current 在 values 最近 window 个值中的分位数"""
    recent = values[-window:] if len(values) >= window else values
    if len(recent) < 10:  # 样本太少不算分位
        return None
    count_below = sum(1 for v in recent if v < current)
    return count_below / len(recent)


def load_cache(trade_date):
    """读取某日涨跌停缓存 → (up_list, down_list)"""
    fp = os.path.join(CACHE_DIR, f'{trade_date}.json')
    if not os.path.exists(fp):
        return None, None
    with open(fp) as f:
        data = json.load(f)
    return data.get('U', []), data.get('D', [])


def sum_fd_amount(stocks):
    """求和封单额（元），过滤 None"""
    total = 0
    count = 0
    for s in stocks:
        fd = s.get('fd_amount')
        if fd is not None and fd > 0:
            total += fd
            count += 1
    return count, total


# ═══ CSV 读写 ═══

def read_existing_csv():
    if not os.path.exists(OUTPUT_CSV):
        return [], set()

    records = []
    dates = set()
    with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 整数字段
            for k in ['up_count', 'down_count']:
                row[k] = int(row[k]) if row.get(k) else 0
            # 浮点字段
            for k in ['up_seal_total', 'down_seal_total', 'seal_spread', 'seal_ratio',
                       'spread_ma5', 'spread_ma20', 'spread_pct_1y']:
                if row.get(k) and row[k] != '':
                    row[k] = float(row[k])
                else:
                    row[k] = None
            records.append(row)
            dates.add(row['date'])

    return records, dates


def write_csv(records):
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, '') if r.get(k) is not None else '' for k in CSV_HEADERS})


def write_json(records):
    if not records:
        return

    latest = records[-1]
    output = {
        'meta': {
            'date_range': f"{records[0]['date']} ~ {records[-1]['date']}",
            'count': len(records),
            'pct_window': PCT_WINDOW,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'latest': {
            'date': latest['date'],
            'seal_spread': latest['seal_spread'],
            'seal_ratio': latest['seal_ratio'],
            'spread_pct_1y': latest['spread_pct_1y'],
            'signal': latest['signal'],
        },
        'daily': records,
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ═══ 主逻辑 ═══

def main():
    log("=" * 60)
    log("涨跌停封单额轧差 (Seal Spread) - 增量更新")
    log("=" * 60)

    # 读取已有数据
    existing_records, existing_dates = read_existing_csv()
    log(f"📦 已有 CSV: {len(existing_records)} 条记录")

    # 获取所有有缓存的交易日
    cache_dates = sorted([
        f.replace('.json', '') for f in os.listdir(CACHE_DIR)
        if f.endswith('.json') and f[:8].isdigit()
    ])

    if not cache_dates:
        log("❌ 无涨停缓存数据")
        return

    log(f"📊 缓存范围: {cache_dates[0]} ~ {cache_dates[-1]} ({len(cache_dates)}天)")

    # 找出需要新计算的日期
    new_dates = [d for d in cache_dates if d not in existing_dates]

    if not new_dates:
        log("✅ 无新数据，跳过计算")
        if existing_records:
            write_json(existing_records)
            log("💾 JSON 已更新")
        return

    log(f"🆕 需计算 {len(new_dates)} 个新交易日")

    # 收集已有的 spread 序列（用于增量计算 MA 和分位数）
    spread_history = [r['seal_spread'] for r in existing_records if r['seal_spread'] is not None]

    new_count = 0
    for date in new_dates:
        ups, downs = load_cache(date)
        if ups is None:
            continue

        # 涨跌停都为空 → 大概率是空缓存（拉取失败或非交易日），跳过
        if not ups and not downs:
            continue

        up_count, up_seal = sum_fd_amount(ups) if ups else (0, 0)
        down_count, down_seal = sum_fd_amount(downs) if downs else (0, 0)

        # 用原始列表长度作为涨跌停家数（包含 fd_amount=null 的）
        up_total = len(ups) if ups else 0
        down_total = len(downs) if downs else 0

        # 转亿元
        up_seal_yi = up_seal / YUAN_TO_YI
        down_seal_yi = down_seal / YUAN_TO_YI

        spread = up_seal_yi - down_seal_yi
        total_seal = up_seal_yi + down_seal_yi
        ratio = up_seal_yi / total_seal if total_seal > 0 else 0.5

        spread_history.append(spread)

        ma5 = calc_ma(spread_history, MA5)
        ma20 = calc_ma(spread_history, MA20)
        pct = calc_percentile(spread_history, spread, PCT_WINDOW)
        signal = get_signal(pct)

        record = {
            'date': date,
            'up_count': up_total,
            'up_seal_total': round(up_seal_yi, 2),
            'down_count': down_total,
            'down_seal_total': round(down_seal_yi, 2),
            'seal_spread': round(spread, 2),
            'seal_ratio': round(ratio, 4),
            'spread_ma5': round(ma5, 2) if ma5 is not None else None,
            'spread_ma20': round(ma20, 2) if ma20 is not None else None,
            'spread_pct_1y': round(pct, 4) if pct is not None else None,
            'signal': signal,
        }
        existing_records.append(record)
        new_count += 1

    # 按日期排序
    existing_records.sort(key=lambda r: r['date'])

    # 如果是全量重算（非纯增量），需要重算所有 MA 和分位数
    if new_count > 20:
        log("🔄 大量新增，重算全部 MA 和分位数...")
        all_spreads = []
        for r in existing_records:
            all_spreads.append(r['seal_spread'])
            idx = len(all_spreads)
            r['spread_ma5'] = round(calc_ma(all_spreads, MA5), 2)
            r['spread_ma20'] = round(calc_ma(all_spreads, MA20), 2) if idx >= MA20 else (round(calc_ma(all_spreads, MA20), 2) if idx >= 2 else None)
            pct = calc_percentile(all_spreads, r['seal_spread'], PCT_WINDOW)
            r['spread_pct_1y'] = round(pct, 4) if pct is not None else None
            r['signal'] = get_signal(pct)

    # 写入
    write_csv(existing_records)
    write_json(existing_records)

    log(f"\n✅ 新增 {new_count} 条，总计 {len(existing_records)} 条")

    # 打印最新几天
    log(f"\n最近5天:")
    for r in existing_records[-5:]:
        pct_str = f"{r['spread_pct_1y']*100:.1f}%" if r['spread_pct_1y'] is not None else "N/A"
        log(f"  {r['date']} | 涨停{r['up_count']}只 封{r['up_seal_total']:.1f}亿 | "
            f"跌停{r['down_count']}只 封{r['down_seal_total']:.1f}亿 | "
            f"轧差{r['seal_spread']:+.1f}亿 | 分位{pct_str} | {r['signal']}")

    log(f"\n💾 CSV: {OUTPUT_CSV}")
    log(f"💾 JSON: {OUTPUT_JSON}")
    log("\n🎉 完成！")


if __name__ == '__main__':
    main()
