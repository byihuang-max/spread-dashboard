#!/usr/bin/env python3
"""
宽基量化股票指标 — 数据脚本 v3（CSV增量模式）
拉取4个子指标的近一年数据，输出 JSON 供 FOF 看板使用

增量策略：
- qs_index_daily.csv 存所有指数日线（ts_code, trade_date, close, amount）
- qs_fut_daily.csv 存股指期货日线（ts_code, trade_date, close）
- 每次只拉 CSV 中没有的新日期
- 最后从 CSV 计算4个指标，输出 quant_stock_data.json（格式不变）

指标1: 全市场成交额时序（中证全指 amount）
指标2: 宽基成交额占比时序（300/500/1000/2000/科创+创业板 各占全A比例）
指标3: IF/IC/IM 年化基差时序（主力连续合约 vs 现货指数）
指标4: 因子表现时序（用可获取的指数近似）
"""

import requests, json, time, os, sys, csv
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 配置 ============
TS_URL  = 'http://lianghua.nanyangqiankun.top'
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'

LOOKBACK_DAYS = 400
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDX_CSV = os.path.join(BASE_DIR, 'qs_index_daily.csv')
FUT_CSV = os.path.join(BASE_DIR, 'qs_fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'quant_stock_data.json')

# 需要拉的指数
INDEX_CODES = [
    ('000985.CSI', '全A'),
    ('000300.SH',  '沪深300'),
    ('000905.SH',  '中证500'),
    ('000852.SH',  '中证1000'),
    ('932000.CSI', '中证2000'),
    ('000688.SH',  '科创50'),
    ('399006.SZ',  '创业板指'),
    ('399371.SZ',  '价值'),
    ('399370.SZ',  '成长'),
    ('000922.CSI', '红利'),
]

# 股指期货连续合约
FUT_CODES = ['IF.CFX', 'IC.CFX', 'IM.CFX']

# 期货对应的现货指数
SPOT_MAP = {'IF': '000300.SH', 'IC': '000905.SH', 'IM': '000852.SH'}

IDX_HEADERS = ['ts_code', 'trade_date', 'close', 'amount']
FUT_HEADERS = ['ts_code', 'trade_date', 'close']

def log(msg):
    print(msg, flush=True)


# ============ Tushare 封装 ============
_last_call = 0

def ts_api(api_name, params, fields=None):
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)

    body = {'api_name': api_name, 'token': TS_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields

    for attempt in range(3):
        try:
            _last_call = time.time()
            r = requests.post(TS_URL, json=body, timeout=60)
            if not r.text:
                log(f'    [空响应, retry {attempt+1}]')
                time.sleep(3)
                continue
            data = r.json()
            if data.get('code') == 0 and data.get('data', {}).get('items'):
                cols = data['data']['fields']
                rows = data['data']['items']
                return [dict(zip(cols, row)) for row in rows]
            elif data.get('code') == -2001:
                log(f'    [限流, 等10s...]')
                time.sleep(10)
                continue
            else:
                msg = data.get('msg', '')
                if msg:
                    log(f'    [API: {msg}]')
                return []
        except Exception as e:
            log(f'    [异常: {e}, retry {attempt+1}]')
            time.sleep(3)
    return []


def get_trade_dates():
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=LOOKBACK_DAYS * 2)).strftime('%Y%m%d')
    rows = ts_api('trade_cal', {
        'exchange': 'SSE', 'start_date': start,
        'end_date': end, 'is_open': '1'
    }, fields='cal_date')
    if not rows:
        return []
    return sorted([r['cal_date'] for r in rows])[-LOOKBACK_DAYS:]


# ============ CSV 工具 ============

def read_csv_data(path):
    """读取CSV，返回行列表"""
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='gb18030') as f:
        return list(csv.DictReader(f))

def get_csv_dates(path, code_col='ts_code', date_col='trade_date', code_filter=None):
    """获取CSV中某个代码已有的日期集合"""
    rows = read_csv_data(path)
    if code_filter:
        return set(r[date_col] for r in rows if r.get(code_col) == code_filter)
    # 返回所有代码共有的日期（取任意一个代码的日期集合）
    if not rows:
        return set()
    codes = set(r[code_col] for r in rows)
    if not codes:
        return set()
    first_code = next(iter(codes))
    return set(r[date_col] for r in rows if r[code_col] == first_code)

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


# ============ 从已有 JSON 迁移到 CSV ============

def migrate_from_json():
    """首次迁移：从 quant_stock_data.json 导入到 CSV"""
    if not os.path.exists(OUT_JSON):
        return False
    if os.path.exists(IDX_CSV) and os.path.getsize(IDX_CSV) > 100:
        return True  # 已迁移

    log("  从 quant_stock_data.json 迁移到 CSV...")
    with open(OUT_JSON, encoding='utf-8') as f:
        data = json.load(f)

    # 指标1 total_amount → 全A 的 amount
    # 指标2 index_share → 各指数的 amount（需要反算）
    # 指标3 basis → 期货 close
    # 指标4 factor → 各因子指数的 close

    # 我们没有原始 close/amount 数据在 JSON 里（JSON 只存了计算结果）
    # 所以迁移只能标记为"需要全量拉取"
    log("    JSON 中没有原始行情数据，需要全量拉取一次")
    return False


# ============ 增量拉取 ============

def fetch_index_incremental(new_dates):
    """增量拉取指数日线"""
    if not new_dates:
        return
    start_date = min(new_dates)
    end_date = max(new_dates)
    new_dates_set = set(new_dates)
    new_rows = []

    for code, name in INDEX_CODES:
        log(f'  拉取 {name}({code}) {start_date}~{end_date}...')
        rows = ts_api('index_daily',
                      {'ts_code': code, 'start_date': start_date, 'end_date': end_date},
                      'ts_code,trade_date,close,amount')
        if not rows:
            log(f'    ⚠️ 无数据')
            continue
        for r in rows:
            if r['trade_date'] in new_dates_set:
                new_rows.append({
                    'ts_code': r['ts_code'],
                    'trade_date': r['trade_date'],
                    'close': r.get('close', ''),
                    'amount': r.get('amount', ''),
                })
        log(f'    {len(rows)} 条')

    if new_rows:
        append_csv(IDX_CSV, IDX_HEADERS, new_rows)
    log(f'  新增 {len(new_rows)} 行指数数据')


def fetch_fut_incremental(new_dates):
    """增量拉取股指期货日线"""
    if not new_dates:
        return
    start_date = min(new_dates)
    end_date = max(new_dates)
    new_dates_set = set(new_dates)
    new_rows = []

    for code in FUT_CODES:
        log(f'  拉取 {code} {start_date}~{end_date}...')
        rows = ts_api('fut_daily',
                      {'ts_code': code, 'start_date': start_date, 'end_date': end_date},
                      'ts_code,trade_date,close')
        if not rows:
            log(f'    ⚠️ 无数据')
            continue
        for r in rows:
            if r['trade_date'] in new_dates_set:
                new_rows.append({
                    'ts_code': r['ts_code'],
                    'trade_date': r['trade_date'],
                    'close': r.get('close', ''),
                })
        log(f'    {len(rows)} 条')

    if new_rows:
        append_csv(FUT_CSV, FUT_HEADERS, new_rows)
    log(f'  新增 {len(new_rows)} 行期货数据')


# ============ 从 CSV 计算指标 ============

def build_json_from_csv(dates):
    """从 CSV 计算4个指标，输出 JSON"""
    date_set = set(dates)

    # 读取指数数据
    idx_rows = read_csv_data(IDX_CSV)
    # {ts_code: {date: {close, amount}}}
    idx_map = defaultdict(dict)
    for r in idx_rows:
        if r['trade_date'] not in date_set:
            continue
        idx_map[r['ts_code']][r['trade_date']] = {
            'close': float(r['close']) if r.get('close') else None,
            'amount': float(r['amount']) if r.get('amount') else None,
        }

    # 读取期货数据
    fut_rows = read_csv_data(FUT_CSV)
    fut_map = defaultdict(dict)
    for r in fut_rows:
        if r['trade_date'] not in date_set:
            continue
        fut_map[r['ts_code']][r['trade_date']] = {
            'close': float(r['close']) if r.get('close') else None,
        }

    # ── 指标1: 全市场成交额 ──
    total_amount = []
    quanA = idx_map.get('000985.CSI', {})
    for d in sorted(dates):
        v = quanA.get(d, {})
        amt = v.get('amount')
        if amt is not None:
            total_amount.append({'date': d, 'amount_yi': round(amt / 100000, 2)})

    # ── 指标2: 宽基成交额占比 ──
    share_codes = [
        ('000300.SH', '沪深300'), ('000905.SH', '中证500'),
        ('000852.SH', '中证1000'), ('932000.CSI', '中证2000'),
    ]
    index_share = []
    for d in sorted(dates):
        tot = quanA.get(d, {}).get('amount')
        if not tot or tot <= 0:
            continue
        row = {'date': d}
        for code, name in share_codes:
            a = idx_map.get(code, {}).get(d, {}).get('amount', 0) or 0
            row[name] = round(a / tot * 100, 2)
        kc = idx_map.get('000688.SH', {}).get(d, {}).get('amount', 0) or 0
        cy = idx_map.get('399006.SZ', {}).get(d, {}).get('amount', 0) or 0
        row['科创+创业板'] = round((kc + cy) / tot * 100, 2)
        index_share.append(row)

    # ── 指标3: 股指期货年化基差 ──
    basis = []
    for d in sorted(dates):
        row = {'date': d}
        has_data = False
        for prefix in ['IF', 'IC', 'IM']:
            spot_code = SPOT_MAP[prefix]
            fut_code = f'{prefix}.CFX'
            spot = idx_map.get(spot_code, {}).get(d, {}).get('close')
            fut = fut_map.get(fut_code, {}).get(d, {}).get('close')
            if spot and fut and spot > 0:
                row[prefix] = round((fut - spot) / spot * 12 * 100, 2)
                has_data = True
        if has_data:
            basis.append(row)

    # ── 指标4: 因子超额收益 ──
    factor_codes_map = {
        '基准': '000985.CSI', '价值': '399371.SZ',
        '成长': '399370.SZ', '红利': '000922.CSI', '小盘': '932000.CSI',
    }
    factor_names = ['价值', '成长', '红利', '小盘']
    factor = []
    nav = {n: 1.0 for n in factor_names}
    prev = {}

    for i, d in enumerate(sorted(dates)):
        if i == 0:
            prev = {n: idx_map.get(c, {}).get(d, {}).get('close')
                    for n, c in factor_codes_map.items()}
            row = {'date': d}
            for n in factor_names:
                row[n] = 1.0
            factor.append(row)
            continue

        bench_code = factor_codes_map['基准']
        bench_close = idx_map.get(bench_code, {}).get(d, {}).get('close')
        bench_prev = prev.get('基准')
        if not bench_close or not bench_prev or bench_prev == 0:
            prev = {n: idx_map.get(c, {}).get(d, {}).get('close') or prev.get(n)
                    for n, c in factor_codes_map.items()}
            continue

        bench_ret = (bench_close - bench_prev) / bench_prev
        row = {'date': d}
        for n in factor_names:
            c = factor_codes_map[n]
            cur = idx_map.get(c, {}).get(d, {}).get('close')
            prv = prev.get(n)
            if cur and prv and prv > 0:
                factor_ret = (cur - prv) / prv
                excess = factor_ret - bench_ret
                nav[n] *= (1 + excess)
            row[n] = round(nav[n], 4)
        factor.append(row)
        prev = {n: idx_map.get(c, {}).get(d, {}).get('close') or prev.get(n)
                for n, c in factor_codes_map.items()}

    # 输出 JSON
    output = {
        'total_amount': total_amount,
        'index_share': index_share,
        'basis': basis,
        'factor': factor,
        'factor_names': factor_names,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f'\n✅ 输出: {OUT_JSON}')
    log(f'   total_amount: {len(total_amount)} 天')
    log(f'   index_share:  {len(index_share)} 天')
    log(f'   basis:        {len(basis)} 天')
    log(f'   factor:       {len(factor)} 天')


# ============ 主流程 ============
def main():
    log('=' * 50)
    log('宽基量化股票指标 数据拉取 v3（CSV增量模式）')
    log('=' * 50)

    # 0. 迁移
    log('\n[0] 检查CSV / 迁移...')
    migrate_from_json()

    # 1. 交易日
    log('\n[1] 获取交易日...')
    dates = get_trade_dates()

    if not dates:
        log('  ⚠️ Tushare 连不上，使用已有CSV数据')
        idx_rows = read_csv_data(IDX_CSV)
        if not idx_rows:
            log('  ERROR: 无交易日且无CSV数据')
            sys.exit(1)
        dates = sorted(set(r['trade_date'] for r in idx_rows
                          if r['ts_code'] == '000985.CSI'))
        log(f'  从CSV恢复: {len(dates)} 天: {dates[0]} ~ {dates[-1]}')
        build_json_from_csv(dates)
        return

    log(f'  {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}')

    # 2. 找出需要增量拉取的日期
    existing_dates = get_csv_dates(IDX_CSV, code_filter='000985.CSI')
    new_dates = sorted(set(dates) - existing_dates)

    if not new_dates:
        log(f'\n  所有 {len(dates)} 天数据已在CSV中，无需拉取')
    else:
        log(f'\n  需要增量拉取: {len(new_dates)} 天 ({new_dates[0]} ~ {new_dates[-1]})')

    # 3. 增量拉取
    if new_dates:
        log('\n[2] 拉取指数数据（增量）...')
        fetch_index_incremental(new_dates)

        log('\n[3] 拉取期货数据（增量）...')
        fetch_fut_incremental(new_dates)
    else:
        log('\n[2-3] 跳过拉取（数据已完整）')

    # 4. 从 CSV 计算指标，输出 JSON
    log('\n[4] 从CSV计算指标...')
    build_json_from_csv(dates)

    log(f'\n   区间: {dates[0]} ~ {dates[-1]} ({len(dates)}天)')


if __name__ == '__main__':
    main()
