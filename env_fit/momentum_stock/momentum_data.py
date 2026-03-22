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

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
            }, timeout=20, proxies={'http': None, 'https': None})
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
    'lianban_count', 'shouban_count', 'seal_zero_count',
    'big_cap_up', 'mega_cap_up', 'mega_cap_names'
]

FULL_HEADERS = [
    # 基础数据
    'date', 'up_count', 'down_count', 'zha_count', 'max_height',
    'lianban_count', 'shouban_count', 'seal_zero_count',
    'big_cap_up', 'mega_cap_up', 'mega_cap_names',
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
            if k == 'mega_cap_names':
                r[k] = r.get(k, '')
            else:
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
            'big_cap_up': 0,
            'mega_cap_up': 0,
            'mega_cap_names': '',
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


def fetch_daily_basic(trade_date, retries=3):
    """拉取某日 daily_basic 获取总市值，返回 {ts_code: total_mv} 字典"""
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': 'daily_basic', 'token': TUSHARE_TOKEN,
                'params': {'trade_date': trade_date},
                'fields': 'ts_code,total_mv'
            }, timeout=20, proxies={'http': None, 'https': None})
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return {row[cols.index('ts_code')]: row[cols.index('total_mv')]
                        for row in data['data']['items'] if row[cols.index('total_mv')]}
            return {}
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return {}


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

    # 市值标注
    big_cap_up = 0
    mega_cap_up = 0
    mega_cap_names = []
    if ups:
        mv_map = fetch_daily_basic(trade_date)
        time.sleep(0.2)
        for u in ups:
            ts_code = u.get('ts_code', '')
            mv = mv_map.get(ts_code)
            if mv and mv >= 1000000:  # >=100亿
                big_cap_up += 1
            if mv and mv >= 3000000:  # >=300亿
                mega_cap_up += 1
                name = u.get('name', ts_code)
                mega_cap_names.append(name)

    return {
        'date': trade_date,
        'up_count': len(ups),
        'down_count': len(downs),
        'zha_count': len(zhas),
        'max_height': max_height,
        'lianban_count': lianban_count,
        'shouban_count': shouban_count,
        'seal_zero_count': seal_zero_count,
        'big_cap_up': big_cap_up,
        'mega_cap_up': mega_cap_up,
        'mega_cap_names': '|'.join(mega_cap_names),
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
        # 涨跌停比 = 涨停数 / 跌停数（clip到20防极端值）
        ud_ratio = min(up_count / max(down_count, 1), 20)
        # 封板质量 = 大市值涨停占比（100亿+涨停数/总涨停数），反映资金级别
        # 旧版用一字板(open_times=0)占比，但一字板=买不到≠资金质量
        big_cap = r.get('big_cap_up', 0)
        mega_cap = r.get('mega_cap_up', 0)
        seal_quality = (big_cap + 2 * mega_cap) / max(up_count, 1) * 100

        full_rows.append({
            'date': dt,
            'up_count': up_count,
            'down_count': down_count,
            'zha_count': zha_count,
            'max_height': max_height,
            'lianban_count': r['lianban_count'],
            'shouban_count': r['shouban_count'],
            'seal_zero_count': seal_zero_count,
            'big_cap_up': r.get('big_cap_up', 0),
            'mega_cap_up': r.get('mega_cap_up', 0),
            'mega_cap_names': r.get('mega_cap_names', ''),
            'promotion_rate': round(promotion_rate, 2),
            'rate_1to2': round(rate_1to2, 2),
            'zha_rate': round(zha_rate, 2),
            'ud_ratio': round(ud_ratio, 2),
            'seal_quality': round(seal_quality, 2),
            # 公式列
            'formula_promotion_rate': '今日涨停∩昨日涨停 / 昨日涨停总数 × 100',
            'formula_rate_1to2': '昨日首板∩今日连板(limit_times≥2) / 昨日首板数 × 100',
            'formula_zha_rate': 'zha_count / (up_count + zha_count) × 100',
            'formula_ud_ratio': 'min(up_count / max(down_count, 1), 20)，clip防极端值',
            'formula_seal_quality': '(big_cap_up + 2*mega_cap_up) / up_count × 100，大市值涨停加权占比',
        })

        prev_up_codes = current_up_codes
        prev_up_by_height = current_up_by_height

    # 标准化 + 合成情绪指数（需要全量数据）
    compute_sentiment(full_rows)

    return full_rows


def percentile_rank(values, window=120):
    """120日滚动分位数排名（0-100），替代60日min-max标准化。
    
    优势：有绝对锚点，冰点期里的"相对高"不会被误判为加速。
    当窗口内数据不足时，用已有数据计算。
    """
    result = []
    for i, v in enumerate(values):
        w = values[max(0, i - window + 1):i + 1]
        if len(w) <= 1:
            result.append(50.0)
            continue
        # 分位数：小于当前值的占比
        below = sum(1 for x in w if x < v)
        equal = sum(1 for x in w if x == v)
        # 中位数法分位：(below + 0.5*equal) / total
        rank = (below + 0.5 * equal) / len(w) * 100
        result.append(round(rank, 2))
    return result


def compute_sentiment(full_rows):
    """在 full_rows 上原地添加标准化因子、合成情绪、周期标签。
    
    v2 优化（2026-03-01）：
    ① 封板质量改为大市值涨停占比（big_cap+2*mega_cap / up_count）
    ② 标准化改为120日分位数排名（替代60日min-max，有绝对锚）
    ③ 涨跌停比clip到20（防跌停=0时极端值）
    ④ 加交互修正项：
       - 高度×质量交互：连板高但封板质量低（全小票）→ 打折
       - 赚亏对冲：晋级率高但炸板率也高（分歧期）→ 打折
    ⑤ 权重调整：空间高度0.20 晋级率0.25 反炸板率0.20 涨跌停比0.10 封板质量0.25
    """
    h = percentile_rank([r['max_height'] for r in full_rows])
    p = percentile_rank([r['promotion_rate'] for r in full_rows])
    z = percentile_rank([100 - r['zha_rate'] for r in full_rows])
    u = percentile_rank([r['ud_ratio'] for r in full_rows])
    s = percentile_rank([r['seal_quality'] for r in full_rows])

    sentiment = []
    for i in range(len(full_rows)):
        # 基础加权：提升封板质量权重（资金级别），降低涨跌停比权重（易极端）
        base = 0.20*h[i] + 0.25*p[i] + 0.20*z[i] + 0.10*u[i] + 0.25*s[i]
        
        # 交互修正1：高度×质量 — 连板高但封板质量低，说明全是小票在玩，打折
        # h高s低 → 扣分；h高s也高 → 不扣
        if h[i] > 70 and s[i] < 30:
            base *= 0.85  # 打85折
        
        # 交互修正2：赚亏对冲 — 晋级率高但炸板率也高=分歧期，不是真的好
        # p高z低（z是反炸板率，低=炸板率高）
        if p[i] > 60 and z[i] < 30:
            base *= 0.90  # 打9折
        
        sentiment.append(round(min(max(base, 0), 100), 2))

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
        r['formula_sentiment'] = 'v2: 0.20*h + 0.25*p + 0.20*z + 0.10*u + 0.25*s (120日分位数排名) × 交互修正(高度×质量, 赚亏对冲)'
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
            'big_cap_up': r.get('big_cap_up', 0),
            'mega_cap_up': r.get('mega_cap_up', 0),
            'mega_cap_names': r.get('mega_cap_names', ''),
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

        # 即使 trade_cal 失败，也尽量补齐 _cache，避免下游 limit_index / seal_spread / sector 卡住
        missing_cache_dates = [d for d in dates if not os.path.exists(os.path.join(CACHE_DIR, f'{d}.json'))]
        if missing_cache_dates:
            log(f"  检测到 {len(missing_cache_dates)} 个缺失缓存，尝试补齐 _cache...")
            for i, dt in enumerate(missing_cache_dates):
                log(f"    [{i+1}/{len(missing_cache_dates)}] 补缓存 {dt}")
                try:
                    fetch_day_cached(dt)
                except Exception as e:
                    log(f"    ⚠️ 补缓存失败 {dt}: {e}")
        else:
            log("  _cache 完整，无需补齐")

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
            log(f"    U={row['up_count']} D={row['down_count']} Z={row['zha_count']} H={row['max_height']} BigCap={row['big_cap_up']} MegaCap={row['mega_cap_up']}")

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

    # 5. 写完整 CSV（含重写 raw CSV 以确保新字段列头一致）
    write_csv(RAW_CSV, RAW_HEADERS, raw_rows)
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
