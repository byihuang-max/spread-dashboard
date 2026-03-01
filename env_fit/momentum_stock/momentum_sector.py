#!/usr/bin/env python3
"""
板块微观结构分析脚本（CSV增量模式）
按申万一级行业聚合统计：涨跌家数比、成交额、平均涨幅、大市值涨停、产业链传导

增量策略：
- momentum_sector.csv 存历史数据（每行=日期+行业）
- momentum_sector.json 同步输出（供前端/其他模块读取）
- _cache/sector/ 缓存每日聚合原始数据
- _cache/stock_industry.json 缓存行业映射（不用每次拉）
"""

import requests, json, time, os, sys, csv
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(BASE_DIR, 'momentum_sector.csv')
OUTPUT_JSON = os.path.join(BASE_DIR, 'momentum_sector.json')
CACHE_DIR = os.path.join(BASE_DIR, '_cache', 'sector')
INDUSTRY_CACHE = os.path.join(BASE_DIR, '_cache', 'stock_industry.json')
CHAIN_MAP_FILE = os.path.join(BASE_DIR, 'sector_chain_map.json')
MOMENTUM_CACHE_DIR = os.path.join(BASE_DIR, '_cache')
LOOKBACK_DAYS = 120

os.makedirs(CACHE_DIR, exist_ok=True)

CSV_HEADERS = [
    'date', 'industry', 'up_count', 'down_count', 'ud_ratio',
    'amount_yi', 'avg_pct_chg', 'big_cap_up', 'mega_cap_up'
]

def log(msg):
    print(msg, flush=True)


# ═══ Tushare API ═══

def tushare_call(api_name, params, fields='', retries=5):
    for attempt in range(retries):
        try:
            body = {
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': fields
            }
            resp = requests.post(TUSHARE_URL, json=body, timeout=20)
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return [dict(zip(cols, row)) for row in data['data']['items']]
            if data.get('code') != 0:
                log(f"  API error ({api_name}): {data.get('msg', 'unknown')}")
            return []
        except Exception as e:
            log(f"  Retry {attempt+1}/{retries} for {api_name}: {e}")
            if attempt < retries - 1:
                time.sleep(3)
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


# ═══ 行业映射 ═══

def load_industry_map():
    """加载 ts_code -> {name, industry(一级)} 映射，优先用缓存
    
    stock_basic 返回的 industry 是旧版分类，需通过 sector_chain_map.json 
    中的 stock_basic_to_level1 映射到申万一级行业。
    """
    # 加载一级映射表
    sb_to_l1 = {}
    if os.path.exists(CHAIN_MAP_FILE):
        with open(CHAIN_MAP_FILE, 'r', encoding='utf-8') as f:
            cm = json.load(f)
        sb_to_l1 = cm.get('stock_basic_to_level1', {})

    if os.path.exists(INDUSTRY_CACHE):
        mtime = os.path.getmtime(INDUSTRY_CACHE)
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24 * 7:  # 一周内缓存有效
            with open(INDUSTRY_CACHE, 'r', encoding='utf-8') as f:
                return json.load(f)

    log("拉取 stock_basic 行业映射...")
    data = tushare_call('stock_basic', {
        'exchange': '', 'list_status': 'L'
    }, fields='ts_code,name,industry')
    if not data:
        # fallback to cache even if stale
        if os.path.exists(INDUSTRY_CACHE):
            with open(INDUSTRY_CACHE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    mapping = {}
    for row in data:
        if row.get('ts_code') and row.get('industry'):
            raw_ind = row['industry']
            l1_ind = sb_to_l1.get(raw_ind, raw_ind)  # 映射到一级，找不到就保留原值
            mapping[row['ts_code']] = {
                'name': row.get('name', ''),
                'industry': l1_ind
            }
    with open(INDUSTRY_CACHE, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False)
    log(f"  缓存行业映射: {len(mapping)} 只股票（已映射到申万一级）")
    return mapping


# ═══ 产业链映射 ═══

def load_chain_map():
    if not os.path.exists(CHAIN_MAP_FILE):
        log(f"警告: {CHAIN_MAP_FILE} 不存在，跳过产业链分析")
        return None
    with open(CHAIN_MAP_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ═══ 涨停票列表 ═══

def get_limit_up_codes(date):
    """获取涨停股列表，优先读 momentum_data.py 的缓存"""
    # 尝试读 momentum_data 的缓存（格式: {'U': [...], 'D': [...], 'Z': [...]}）
    cache_file = os.path.join(MOMENTUM_CACHE_DIR, f'{date}.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        codes = set()
        if isinstance(cache_data, dict) and 'U' in cache_data:
            for item in cache_data['U']:
                if item.get('ts_code'):
                    codes.add(item['ts_code'])
        if codes:
            return codes

    # fallback: 调 limit_list_d
    data = tushare_call('limit_list_d', {
        'trade_date': date, 'limit_type': 'U'
    }, fields='ts_code,trade_date,limit')
    return {row['ts_code'] for row in data if row.get('ts_code')}


# ═══ 每日数据获取 ═══

def fetch_day_data(date, industry_map):
    """获取某天的行业聚合数据，带缓存"""
    cache_file = os.path.join(CACHE_DIR, f'{date}.json')
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    log(f"  拉取 {date} 数据...")

    # 拉 daily
    daily = tushare_call('daily', {
        'trade_date': date
    }, fields='ts_code,open,high,low,close,pre_close,vol,amount,pct_chg')
    time.sleep(0.3)

    # 拉 daily_basic (市值)
    basic = tushare_call('daily_basic', {
        'trade_date': date
    }, fields='ts_code,total_mv')
    time.sleep(0.3)

    mv_map = {row['ts_code']: row.get('total_mv', 0) or 0 for row in basic}

    # 涨停票
    limit_up_codes = get_limit_up_codes(date)

    # 按行业聚合
    sectors = defaultdict(lambda: {
        'up': 0, 'down': 0, 'amount': 0.0,
        'pct_chg_sum': 0.0, 'count': 0,
        'big_cap_up': 0, 'mega_cap_up': 0,
        'mega_cap_names': []
    })

    for row in daily:
        code = row.get('ts_code', '')
        info = industry_map.get(code)
        if not info:
            continue
        ind = info['industry']
        pct = row.get('pct_chg') or 0
        amt = row.get('amount') or 0  # 千元
        mv = mv_map.get(code, 0)  # 万元

        s = sectors[ind]
        if pct > 0:
            s['up'] += 1
        elif pct < 0:
            s['down'] += 1
        s['amount'] += amt
        s['pct_chg_sum'] += pct
        s['count'] += 1

        # 涨停 + 大市值
        if code in limit_up_codes:
            mv_yi = mv / 10000  # 万元 -> 亿元
            if mv_yi >= 100:
                s['big_cap_up'] += 1
            if mv_yi >= 300:
                s['mega_cap_up'] += 1
                s['mega_cap_names'].append(info.get('name', code))

    # 组装结果
    result = {}
    for ind, s in sectors.items():
        down = max(s['down'], 1)
        result[ind] = {
            'industry': ind,
            'up_count': s['up'],
            'down_count': s['down'],
            'ud_ratio': round(s['up'] / down, 2),
            'amount_yi': round(s['amount'] / 100000, 2),  # 千元 -> 亿元
            'avg_pct_chg': round(s['pct_chg_sum'] / max(s['count'], 1), 2),
            'big_cap_up': s['big_cap_up'],
            'mega_cap_up': s['mega_cap_up'],
            'mega_cap_names': s['mega_cap_names']
        }

    # 缓存
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)

    return result


# ═══ 产业链传导分析 ═══

def analyze_chains(sector_data, chain_map):
    """分析产业链传导"""
    if not chain_map:
        return []

    chains_config = chain_map.get('chains', {})
    results = []

    for chain_name, positions in chains_config.items():
        active_positions = []
        for pos_name, industries in positions.items():
            if not industries:
                continue
            # 检查该位置是否有强势表现
            strong = False
            for ind in industries:
                s = sector_data.get(ind)
                if not s:
                    continue
                if s['ud_ratio'] > 1.5 or s['big_cap_up'] > 0:
                    strong = True
                    break
            if strong:
                active_positions.append(pos_name)

        # 判断共振：所有非空位置都活跃
        non_empty = [pos for pos, inds in positions.items() if inds]
        resonance = len(active_positions) >= len(non_empty) and len(non_empty) >= 2

        results.append({
            'chain': chain_name,
            'positions_active': active_positions,
            'resonance': resonance
        })

    return results


# ═══ CSV 读写 ═══

def load_existing_csv():
    """读取已有CSV，返回已有日期集合和全部行"""
    dates = set()
    rows = []
    if not os.path.exists(OUTPUT_CSV):
        return dates, rows
    with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.add(row['date'])
            rows.append(row)
    return dates, rows


def save_csv(rows):
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, '') for k in CSV_HEADERS})


# ═══ 主逻辑 ═══

def main():
    log("=== 板块微观结构分析 ===")

    # 获取交易日
    trade_dates = get_trade_dates()
    if not trade_dates:
        log("无法获取交易日历，退出")
        return
    log(f"交易日窗口: {trade_dates[0]} ~ {trade_dates[-1]} ({len(trade_dates)}天)")

    # 加载行业映射
    industry_map = load_industry_map()
    if not industry_map:
        log("无法获取行业映射，退出")
        return
    log(f"行业映射: {len(industry_map)} 只股票")

    # 加载产业链
    chain_map = load_chain_map()

    # 读已有CSV
    existing_dates, csv_rows = load_existing_csv()
    log(f"CSV已有 {len(existing_dates)} 天数据")

    # 过滤需要拉取的日期
    new_dates = [d for d in trade_dates if d not in existing_dates]
    if not new_dates:
        log("无新数据需要拉取")
    else:
        log(f"需拉取 {len(new_dates)} 天: {new_dates[0]} ~ {new_dates[-1]}")

    # 增量拉取
    all_daily_data = {}  # date -> sector_data

    # 先加载已缓存的日期数据（用于JSON输出）
    for d in trade_dates:
        if d in existing_dates:
            cache_file = os.path.join(CACHE_DIR, f'{d}.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    all_daily_data[d] = json.load(f)

    # 拉取新日期
    for i, date in enumerate(new_dates):
        log(f"[{i+1}/{len(new_dates)}] {date}")
        sector_data = fetch_day_data(date, industry_map)
        all_daily_data[date] = sector_data

        # 追加CSV行
        for ind, s in sector_data.items():
            csv_rows.append({
                'date': date,
                'industry': s['industry'],
                'up_count': s['up_count'],
                'down_count': s['down_count'],
                'ud_ratio': s['ud_ratio'],
                'amount_yi': s['amount_yi'],
                'avg_pct_chg': s['avg_pct_chg'],
                'big_cap_up': s['big_cap_up'],
                'mega_cap_up': s['mega_cap_up']
            })
        time.sleep(0.5)

    # 保存CSV
    csv_rows.sort(key=lambda r: (r['date'], r.get('industry', '')))
    save_csv(csv_rows)
    log(f"CSV 已保存: {OUTPUT_CSV}")

    # 构建JSON输出
    # 对于缓存中没有但CSV中有的日期，从CSV重建
    csv_by_date = defaultdict(list)
    for row in csv_rows:
        csv_by_date[row['date']].append(row)

    daily_list = []
    for date in sorted(trade_dates):
        # 优先用内存中的完整数据
        if date in all_daily_data:
            sector_data = all_daily_data[date]
        else:
            # 从CSV重建
            sector_data = {}
            for row in csv_by_date.get(date, []):
                ind = row['industry']
                sector_data[ind] = {
                    'industry': ind,
                    'up_count': int(row.get('up_count', 0)),
                    'down_count': int(row.get('down_count', 0)),
                    'ud_ratio': float(row.get('ud_ratio', 0)),
                    'amount_yi': float(row.get('amount_yi', 0)),
                    'avg_pct_chg': float(row.get('avg_pct_chg', 0)),
                    'big_cap_up': int(row.get('big_cap_up', 0)),
                    'mega_cap_up': int(row.get('mega_cap_up', 0))
                }

        if not sector_data:
            continue

        # 排序行业列表
        sectors_list = sorted(sector_data.values(), key=lambda x: x.get('mega_cap_up', 0), reverse=True)
        # 清理 mega_cap_names（不输出到JSON的sectors中）
        clean_sectors = []
        for s in sectors_list:
            clean_sectors.append({
                'industry': s['industry'],
                'up_count': s['up_count'],
                'down_count': s['down_count'],
                'ud_ratio': s['ud_ratio'],
                'amount_yi': s['amount_yi'],
                'avg_pct_chg': s['avg_pct_chg'],
                'big_cap_up': s['big_cap_up'],
                'mega_cap_up': s['mega_cap_up']
            })

        # 主攻行业：300亿+涨停最多的前3
        top_sectors = sorted(sectors_list, key=lambda x: x.get('mega_cap_up', 0), reverse=True)
        top_names = [s['industry'] for s in top_sectors if s.get('mega_cap_up', 0) > 0][:3]

        # 产业链分析
        chain_analysis = analyze_chains(sector_data, chain_map)

        day_entry = {
            'date': date,
            'sectors': clean_sectors,
            'top_sectors': top_names,
            'chain_analysis': chain_analysis
        }
        daily_list.append(day_entry)

    output = {
        'updated': datetime.now().strftime('%Y-%m-%d'),
        'daily': daily_list
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"JSON 已保存: {OUTPUT_JSON}")
    log("=== 完成 ===")


if __name__ == '__main__':
    main()
