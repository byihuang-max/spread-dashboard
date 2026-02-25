#!/usr/bin/env python3
"""
强势股情绪指标数据脚本（CSV增量模式）
从 Tushare limit_list_d 拉取涨跌停数据，增量追加到 CSV
CSV 包含：基础数据列 + 计算指标列 + 计算公式列

增量策略：
- momentum_raw.csv 存基础数据（每日涨跌停原始统计）
- momentum_sentiment.csv 存完整数据（基础+计算指标+公式）
- 每次只拉 CSV 中没有的新日期
- 最后仍输出 momentum_sentiment.json（供 inject_momentum.py 使用）
"""

import requests, json, time, os, sys, csv
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/momentum_stock'
OUTPUT_JSON = os.path.join(BASE_DIR, 'momentum_sentiment.json')
RAW_CSV = os.path.join(BASE_DIR, 'momentum_raw.csv')
FULL_CSV = os.path.join(BASE_DIR, 'momentum_sentiment.csv')
CACHE_DIR = os.path.join(BASE_DIR, '_cache')
LOOKBACK_DAYS = 120

os.makedirs(CACHE_DIR, exist_ok=True)

def log(msg):
    print(msg, flush=True)


# ═══ Tushare API ═══

def tushare_call(api_name, params, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': ''
            }, timeout=20)
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return [dict(zip(cols, row)) for row in data['data']['items']]
            return []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return []


def get_trade_dates(n_days=LOOKBACK_DAYS):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=n_days * 2)).strftime('%Y%m%d')
    data = tushare_call('trade_cal', {
        'exchange': 'SSE', 'start_date': start,
        'end_date': end, 'is_open': '1'
    })
    if not data:
        return []
    return sorted([d['cal_date'] for d in data])[-n_days:]


# ═══ CSV 工具 ═══

RAW_HEADERS = [
    'date', 'up_count', 'down_count', 'zha_count', 'max_height',
    'lianban_count', 'shouban_count', 'seal_zero_count'
]

FULL_HEADERS = [
    # 基础数据
    'date', 'up_count', 'down_count', 'zha_count', 'max_height',
    'lianban_count', 'shouban_count', 'seal_zero_count',
    # 计算指标
    'promotion_rate', 'rate_1to2', 'zha_rate', 'ud_ratio', 'seal_quality',
    'h_norm', 'p_norm', 'z_norm', 'u_norm', 's_norm',
    'sentiment', 'cycle_label',
    # 计算公式
    'formula_promotion_rate', 'formula_rate_1to2', 'formula_zha_rate',
    'formula_ud_ratio', 'formula_seal_quality', 'formula_sentiment',
    'formula_cycle_label'
]

def read_csv_dates(path):
    """读取CSV中已有的日期集合"""
    if not os.path.exists(path):
        return set()
    with open(path, 'r', newline='', encoding='gb18030') as f:
        reader = csv.DictReader(f)
        return set(row['date'] for row in reader)

def read_raw_csv():
    """读取原始CSV，返回按日期排序的列表"""
    if not os.path.exists(RAW_CSV):
        return []
    with open(RAW_CSV, 'r', newline='', encoding='gb18030') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # 转数值
    for r in rows:
        for k in RAW_HEADERS[1:]:
            r[k] = int(r[k]) if r.get(k, '') != '' else 0
    return sorted(rows, key=lambda x: x['date'])

def write_csv(path, headers, rows):
    with open(path, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

def append_csv(path, headers, rows):
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, 'a', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


# ═══ 从已有 JSON 迁移到 CSV ═══

def migrate_from_json():
    """首次迁移：从 momentum_sentiment.json 导入到 raw CSV"""
    if not os.path.exists(OUTPUT_JSON):
        return False
    if os.path.exists(RAW_CSV) and os.path.getsize(RAW_CSV) > 100:
        return True  # 已迁移过

    log("  从 momentum_sentiment.json 迁移到 CSV...")
    with open(OUTPUT_JSON) as f:
        data = json.load(f)

    raw_rows = []
    for d in data.get('daily', []):
        raw_rows.append({
            'date': d['date'],
            'up_count': d['up_count'],
            'down_count': d['down_count'],
            'zha_count': d['zha_count'],
            'max_height': d['max_height'],
            'lianban_count': d['lianban_count'],
            'shouban_count': d['shouban_count'],
            'seal_zero_count': round(d['seal_quality'] / 100 * max(d['up_count'], 1)),
        })
    write_csv(RAW_CSV, RAW_HEADERS, raw_rows)
    log(f"    momentum_raw.csv: {len(raw_rows)} 行")
    return True


# ═══ 拉取单日数据 ═══

def fetch_day_cached(trade_date):
    """拉取某日 U/D/Z 数据，有缓存直接读"""
    cache_file = os.path.join(CACHE_DIR, f'{trade_date}.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    ups = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'U'})
    time.sleep(0.2)
    downs = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'D'})
    time.sleep(0.2)
    zhas = tushare_call('limit_list_d', {'trade_date': trade_date, 'limit_type': 'Z'})
    time.sleep(0.2)

    result = {'U': ups, 'D': downs, 'Z': zhas}
    with open(cache_file, 'w') as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def compute_raw_day(trade_date):
    """拉取并计算单日基础数据"""
    data = fetch_day_cached(trade_date)
    ups, downs, zhas = data['U'], data['D'], data['Z']

    seal_zero_count = 0
    max_height = 0
    lianban_count = shouban_count = 0

    for u in ups:
        lt = u.get('limit_times') or 1
        ot = u.get('open_times') or 0
        if lt > max_height:
            max_height = lt
        if lt > 1:
            lianban_count += 1
        else:
            shouban_count += 1
        if ot == 0:
            seal_zero_count += 1

    return {
        'date': trade_date,
        'up_count': len(ups),
        'down_count': len(downs),
        'zha_count': len(zhas),
        'max_height': max_height,
        'lianban_count': lianban_count,
        'shouban_count': shouban_count,
        'seal_zero_count': seal_zero_count,
    }


# ═══ 计算指标（需要前后文） ═══

def compute_all_metrics(raw_rows):
    """从原始数据计算所有指标，返回完整行列表"""
    # 需要从 cache 读取每日涨停代码来算晋级率
    prev_up_codes = set()
    prev_up_by_height = defaultdict(set)

    full_rows = []

    for i, r in enumerate(raw_rows):
        dt = r['date']
        up_count = r['up_count']
        down_count = r['down_count']
        zha_count = r['zha_count']
        max_height = r['max_height']
        seal_zero_count = r['seal_zero_count']

        # 从 cache 读取涨停代码（用于晋级率计算）
        cache_file = os.path.join(CACHE_DIR, f'{dt}.json')
        current_up_codes = set()
        current_up_by_height = defaultdict(set)

        if os.path.exists(cache_file):
            with open(cache_file) as f:
                day_data = json.load(f)
            for u in day_data.get('U', []):
                ts_code = u.get('ts_code', '')
                lt = u.get('limit_times') or 1
                current_up_codes.add(ts_code)
                current_up_by_height[lt].add(ts_code)

        # 晋级率 = 今日涨停中昨日也涨停的 / 昨日涨停总数
        promotion_rate = 0
        if prev_up_codes:
            continued = current_up_codes & prev_up_codes
            promotion_rate = len(continued) / len(prev_up_codes) * 100

        # 1进2率 = 昨日首板今日连板的 / 昨日首板总数
        rate_1to2 = 0
        if prev_up_by_height.get(1):
            prev_sb = prev_up_by_height[1]
            today_lb = {u for u in current_up_codes
                       if any(current_up_by_height[h] for h in current_up_by_height if h >= 2)
                       and u in current_up_codes}
            # 更准确：从 cache 直接取 limit_times >= 2 的
            today_lb = set()
            if os.path.exists(cache_file):
                for u in day_data.get('U', []):
                    if (u.get('limit_times') or 1) >= 2:
                        today_lb.add(u.get('ts_code', ''))
            promoted = prev_sb & today_lb
            rate_1to2 = len(promoted) / len(prev_sb) * 100 if prev_sb else 0

        # 炸板率 = 炸板数 / (涨停数 + 炸板数)
        zha_rate = zha_count / max(up_count + zha_count, 1) * 100
        # 涨跌停比 = 涨停数 / 跌停数
        ud_ratio = up_count / max(down_count, 1)
        # 封板质量 = 一字/秒板(open_times=0)占比
        seal_quality = seal_zero_count / max(up_count, 1) * 100

        full_rows.append({
            'date': dt,
            'up_count': up_count,
            'down_count': down_count,
            'zha_count': zha_count,
            'max_height': max_height,
            'lianban_count': r['lianban_count'],
            'shouban_count': r['shouban_count'],
            'seal_zero_count': seal_zero_count,
            'promotion_rate': round(promotion_rate, 2),
            'rate_1to2': round(rate_1to2, 2),
            'zha_rate': round(zha_rate, 2),
            'ud_ratio': round(ud_ratio, 2),
            'seal_quality': round(seal_quality, 2),
            # 公式列
            'formula_promotion_rate': '今日涨停∩昨日涨停 / 昨日涨停总数 × 100',
            'formula_rate_1to2': '昨日首板∩今日连板(limit_times≥2) / 昨日首板数 × 100',
            'formula_zha_rate': 'zha_count / (up_count + zha_count) × 100',
            'formula_ud_ratio': 'up_count / max(down_count, 1)',
            'formula_seal_quality': 'seal_zero_count(open_times=0) / up_count × 100',
        })

        prev_up_codes = current_up_codes
        prev_up_by_height = current_up_by_height

    # 标准化 + 合成情绪指数（需要全量数据）
    compute_sentiment(full_rows)

    return full_rows


def normalize_series(values, window=60):
    result = []
    for i, v in enumerate(values):
        w = values[max(0, i - window + 1):i + 1]
        mn, mx = min(w), max(w)
        result.append(round((v - mn) / (mx - mn) * 100, 2) if mx != mn else 50.0)
    return result


def compute_sentiment(full_rows):
    """在 full_rows 上原地添加标准化因子、合成情绪、周期标签"""
    h = normalize_series([r['max_height'] for r in full_rows])
    p = normalize_series([r['promotion_rate'] for r in full_rows])
    z = normalize_series([100 - r['zha_rate'] for r in full_rows])
    u = normalize_series([r['ud_ratio'] for r in full_rows])
    s = normalize_series([r['seal_quality'] for r in full_rows])

    sentiment = [round(0.25*h[i] + 0.25*p[i] + 0.20*z[i] + 0.15*u[i] + 0.15*s[i], 2)
                 for i in range(len(full_rows))]

    # 周期标签
    labels = []
    for i, v in enumerate(sentiment):
        if i < 2:
            labels.append('—')
            continue
        prev, prev2 = sentiment[i-1], sentiment[i-2]
        d = v - prev
        d2 = prev - prev2
        if v < 20:
            labels.append('冰点')
        elif v < 35 and prev < 30 and d > 0:
            labels.append('回暖')
        elif v > 60 and d > 0:
            labels.append('加速')
        elif v > 50 and d < 0:
            labels.append('分歧')
        elif v < 40 and prev > 45 and d < 0 and d2 < 0:
            labels.append('退潮')
        elif d > 3:
            labels.append('回暖')
        elif d < -3:
            labels.append('退潮')
        else:
            labels.append('震荡')

    for i, r in enumerate(full_rows):
        r['h_norm'] = h[i]
        r['p_norm'] = p[i]
        r['z_norm'] = z[i]
        r['u_norm'] = u[i]
        r['s_norm'] = s[i]
        r['sentiment'] = sentiment[i]
        r['cycle_label'] = labels[i]
        r['formula_sentiment'] = '0.25*h_norm + 0.25*p_norm + 0.20*z_norm + 0.15*u_norm + 0.15*s_norm (各因子60日滚动min-max标准化)'
        r['formula_cycle_label'] = '冰点(<20)|回暖(<35且上升)|加速(>60且上升)|分歧(>50且下降)|退潮(<40从>45连降)|震荡(其他)'


# ═══ 输出 JSON（格式不变）═══

def build_json(full_rows):
    """从完整行列表生成 JSON（格式与原版一致）"""
    daily = []
    for r in full_rows:
        daily.append({
            'date': r['date'],
            'up_count': r['up_count'],
            'down_count': r['down_count'],
            'zha_count': r['zha_count'],
            'max_height': r['max_height'],
            'lianban_count': r['lianban_count'],
            'shouban_count': r['shouban_count'],
            'promotion_rate': r['promotion_rate'],
            'rate_1to2': r['rate_1to2'],
            'zha_rate': r['zha_rate'],
            'ud_ratio': r['ud_ratio'],
            'seal_quality': r['seal_quality'],
            'sentiment': r['sentiment'],
            'h_norm': r['h_norm'],
            'p_norm': r['p_norm'],
            'z_norm': r['z_norm'],
            'u_norm': r['u_norm'],
            's_norm': r['s_norm'],
            'cycle_label': r['cycle_label'],
        })

    output = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'date_range': f"{daily[0]['date']} ~ {daily[-1]['date']}",
            'count': len(daily),
            'weights': {'height': 0.25, 'promotion': 0.25, 'anti_zha': 0.20,
                       'ud_ratio': 0.15, 'seal_quality': 0.15}
        },
        'daily': daily
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    fsize = os.path.getsize(OUTPUT_JSON) / 1024
    log(f"  JSON: {OUTPUT_JSON} ({fsize:.0f} KB)")


# ═══ 主流程 ═══

def main():
    log("=" * 50)
    log("强势股情绪指标（CSV增量模式）")
    log("=" * 50)

    # 0. 首次迁移
    log("\n[0] 检查CSV / 迁移...")
    migrate_from_json()

    # 1. 获取交易日
    log("\n[1] 获取交易日...")
    dates = get_trade_dates(LOOKBACK_DAYS)

    if not dates:
        log("  ⚠️ Tushare 连不上，使用已有CSV数据")
        raw_rows = read_raw_csv()
        if not raw_rows:
            log("  ERROR: 无交易日且无CSV数据")
            sys.exit(1)
        dates = [r['date'] for r in raw_rows]
        log(f"  从CSV恢复: {len(dates)} 天: {dates[0]} ~ {dates[-1]}")
        full_rows = compute_all_metrics(raw_rows)
        write_csv(FULL_CSV, FULL_HEADERS, full_rows)
        build_json(full_rows)
        return

    log(f"  {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    # 2. 找出需要增量拉取的日期
    existing_dates = read_csv_dates(RAW_CSV)
    new_dates = sorted(set(dates) - existing_dates)

    if not new_dates:
        log(f"\n  所有 {len(dates)} 天数据已在CSV中，无需拉取")
    else:
        log(f"\n  需要增量拉取: {len(new_dates)} 天 ({new_dates[0]} ~ {new_dates[-1]})")

    # 3. 增量拉取新日期的基础数据
    if new_dates:
        log("\n[2] 拉取新日期数据...")
        new_raw_rows = []
        for i, dt in enumerate(new_dates):
            cached = os.path.exists(os.path.join(CACHE_DIR, f'{dt}.json'))
            tag = '📦' if cached else '🌐'
            log(f"  [{i+1}/{len(new_dates)}] {dt} {tag}")
            row = compute_raw_day(dt)
            new_raw_rows.append(row)
            log(f"    U={row['up_count']} D={row['down_count']} Z={row['zha_count']} H={row['max_height']}")

        # 追加到 raw CSV
        append_csv(RAW_CSV, RAW_HEADERS, new_raw_rows)
        log(f"  新增 {len(new_raw_rows)} 行到 momentum_raw.csv")
    else:
        log("\n[2] 跳过拉取（数据已完整）")

    # 4. 重新读取全量 raw 数据，计算所有指标
    log("\n[3] 计算指标...")
    raw_rows = read_raw_csv()
    # 只保留 dates 范围内的
    date_set = set(dates)
    raw_rows = [r for r in raw_rows if r['date'] in date_set]
    raw_rows.sort(key=lambda x: x['date'])

    full_rows = compute_all_metrics(raw_rows)

    # 5. 写完整 CSV
    write_csv(FULL_CSV, FULL_HEADERS, full_rows)
    log(f"  momentum_sentiment.csv: {len(full_rows)} 行")

    # 6. 输出 JSON
    log("\n[4] 输出 JSON...")
    build_json(full_rows)

    latest = full_rows[-1]
    log(f"\n✅ 完成: {len(full_rows)} 天")
    log(f"   最新: {latest['date']} 情绪={latest['sentiment']} 周期={latest['cycle_label']}")
    log(f"   CSV: momentum_raw.csv + momentum_sentiment.csv")


if __name__ == '__main__':
    main()
