#!/usr/bin/env python3
"""
模块三：期权套利（波动率监控）
用 opt_basic 获取 Call/Put 映射，再从 opt_daily 拉全市场期权数据，计算：
- PCR（Put-Call Ratio，成交量/持仓量）
- HV20（20日历史波动率，基于沪深300指数）
- 成交量/持仓量趋势
输出：mod3_option_arb.json + mod3_option_arb.csv（近30个交易日）
"""

import requests, json, time, os, sys, csv, math
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 配置 ============
TS_URL = 'http://lianghua.nanyangqiankun.top'
TS_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, 'mod3_option_arb.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod3_option_arb.csv')
CP_CACHE = os.path.join(BASE_DIR, '_opt_cp_map.json')

LOOKBACK_DAYS = 30
HV_EXTRA_DAYS = 30

# 用沪深300指数算 HV
HV_INDEX = '000300.SH'


def log(msg):
    print(msg, flush=True)


# ============ Tushare API ============
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
                return []
        except Exception as e:
            log(f'    [异常: {e}, retry {attempt+1}]')
            time.sleep(3)
    return []


def get_trade_dates(n_days):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=n_days * 3)).strftime('%Y%m%d')
    rows = ts_api('trade_cal', {
        'exchange': 'SSE', 'start_date': start,
        'end_date': end, 'is_open': '1'
    }, fields='cal_date')
    if not rows:
        return []
    return sorted([r['cal_date'] for r in rows])[-n_days:]


# ============ Call/Put 映射 ============

def load_cp_map():
    """加载或构建 ts_code → C/P 映射"""
    # 先尝试缓存
    if os.path.exists(CP_CACHE):
        age_hours = (time.time() - os.path.getmtime(CP_CACHE)) / 3600
        if age_hours < 24 * 7:  # 7天内有效
            with open(CP_CACHE) as f:
                cp_map = json.load(f)
            log(f'  从缓存加载 C/P 映射: {len(cp_map)} 合约')
            return cp_map

    # 从 API 拉
    log('  从 API 构建 C/P 映射...')
    cp_map = {}
    for cp in ['C', 'P']:
        rows = ts_api('opt_basic', {
            'exchange': 'SSE', 'call_put': cp
        }, fields='ts_code,call_put')
        if rows:
            for r in rows:
                cp_map[r['ts_code']] = r['call_put']
            log(f'    {cp}: {len(rows)} 合约')
        time.sleep(2)

    if cp_map:
        with open(CP_CACHE, 'w') as f:
            json.dump(cp_map, f)
        log(f'  映射已缓存: {len(cp_map)} 合约')

    return cp_map


# ============ 计算 ============

def compute_hv(closes, window=20):
    """计算历史波动率（年化，百分比）"""
    if len(closes) < window + 1:
        return None
    rets = []
    for i in range(len(closes) - window, len(closes)):
        if closes[i-1] > 0:
            rets.append(math.log(closes[i] / closes[i-1]))
    if len(rets) < window:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean)**2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252) * 100


# ============ 输出 ============

def write_output(series, dates):
    """输出 JSON + CSV"""

    # === JSON ===
    json_out = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'date_range': f'{dates[0]} ~ {dates[-1]}' if dates else '',
        'n_days': len(dates),
        'exchange': 'SSE',
        'description': '上交所全市场ETF期权（含300ETF/50ETF等）',
        'series': series,
        'summary': {},
    }

    if series:
        latest = series[-1]
        pcr_vols = [s['pcr_vol'] for s in series if s.get('pcr_vol') is not None]
        pcr_ois = [s['pcr_oi'] for s in series if s.get('pcr_oi') is not None]
        hvs = [s['hv_20'] for s in series if s.get('hv_20') is not None]

        summary = {
            'latest_date': latest['date'],
            'latest_pcr_vol': latest.get('pcr_vol'),
            'latest_pcr_oi': latest.get('pcr_oi'),
            'latest_hv_20': latest.get('hv_20'),
            'latest_total_vol': latest.get('total_vol', 0),
            'latest_total_amount': latest.get('total_amount', 0),
        }
        if pcr_vols:
            summary['avg_pcr_vol'] = round(sum(pcr_vols) / len(pcr_vols), 4)
            summary['max_pcr_vol'] = round(max(pcr_vols), 4)
            summary['min_pcr_vol'] = round(min(pcr_vols), 4)
            # PCR 分位数
            sorted_pcr = sorted(pcr_vols)
            latest_pcr = latest.get('pcr_vol', 0)
            pctile = sum(1 for x in sorted_pcr if x <= latest_pcr) / len(sorted_pcr)
            summary['pcr_vol_pctile'] = round(pctile, 4)
        if pcr_ois:
            summary['avg_pcr_oi'] = round(sum(pcr_ois) / len(pcr_ois), 4)
        if hvs:
            summary['avg_hv_20'] = round(sum(hvs) / len(hvs), 2)
            summary['max_hv_20'] = round(max(hvs), 2)
            summary['min_hv_20'] = round(min(hvs), 2)

        json_out['summary'] = summary

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)

    # === CSV ===
    csv_headers = [
        'date', 'call_vol', 'put_vol', 'total_vol', 'total_amount',
        'call_oi', 'put_oi', 'pcr_vol', 'pcr_oi', 'hv_20',
    ]
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for row in series:
            writer.writerow({h: row.get(h, '') for h in csv_headers})


# ============ 主流程 ============

def main():
    log('=' * 50)
    log('模块三：期权套利（波动率监控）')
    log('=' * 50)

    # 1. 交易日
    log('\n[1] 获取交易日...')
    all_dates = get_trade_dates(LOOKBACK_DAYS + HV_EXTRA_DAYS)
    if not all_dates:
        log('  ⚠️ 无法获取交易日')
        return

    dates = all_dates[-LOOKBACK_DAYS:]
    start_date = all_dates[0]
    end_date = dates[-1]
    log(f'  分析区间: {dates[0]} ~ {end_date} ({len(dates)} 天)')

    # 2. C/P 映射
    log('\n[2] 加载 Call/Put 映射...')
    cp_map = load_cp_map()
    if not cp_map:
        log('  ⚠️ 无法获取 C/P 映射')
        return

    # 3. 指数日线（用于 HV）
    log('\n[3] 拉取指数日线（HV 计算）...')
    idx_rows = ts_api('index_daily', {
        'ts_code': HV_INDEX,
        'start_date': start_date,
        'end_date': end_date,
    }, fields='ts_code,trade_date,close')

    idx_map = {}
    for r in (idx_rows or []):
        idx_map[r['trade_date']] = r.get('close')
    log(f'  {HV_INDEX}: {len(idx_map)} 天')

    # 构建 close 序列
    index_closes = []
    for d in all_dates:
        c = idx_map.get(d)
        if c:
            index_closes.append(c)
        elif index_closes:
            index_closes.append(index_closes[-1])

    # 4. 逐日拉期权数据
    log('\n[4] 拉取期权日线...')
    series = []

    for i, d in enumerate(dates):
        rows = ts_api('opt_daily', {
            'exchange': 'SSE', 'trade_date': d
        }, fields='ts_code,trade_date,close,vol,amount,oi')

        if not rows:
            if i < 3 or i >= len(dates) - 3:
                log(f'  {d}: 无数据')
            continue

        call_vol = 0
        put_vol = 0
        call_oi = 0
        put_oi = 0
        call_amount = 0
        put_amount = 0

        for r in rows:
            code = r.get('ts_code', '')
            cp = cp_map.get(code)
            vol = r.get('vol', 0) or 0
            oi = r.get('oi', 0) or 0
            amount = r.get('amount', 0) or 0

            if cp == 'C':
                call_vol += vol
                call_oi += oi
                call_amount += amount
            elif cp == 'P':
                put_vol += vol
                put_oi += oi
                put_amount += amount

        pcr_vol = round(put_vol / call_vol, 4) if call_vol > 0 else None
        pcr_oi = round(put_oi / call_oi, 4) if call_oi > 0 else None

        # HV
        idx_pos = HV_EXTRA_DAYS + i
        hv_20 = compute_hv(index_closes[:idx_pos+1], 20) if idx_pos < len(index_closes) else None

        total_vol = call_vol + put_vol
        total_amount = round(call_amount + put_amount, 2)

        row = {
            'date': d,
            'call_vol': int(call_vol),
            'put_vol': int(put_vol),
            'total_vol': int(total_vol),
            'total_amount': total_amount,
            'call_oi': int(call_oi),
            'put_oi': int(put_oi),
            'pcr_vol': pcr_vol,
            'pcr_oi': pcr_oi,
            'hv_20': round(hv_20, 2) if hv_20 is not None else None,
        }
        series.append(row)

        if i == 0 or i == len(dates) - 1:
            log(f'  {d}: {len(rows)} 合约, PCR(量)={pcr_vol}, PCR(仓)={pcr_oi}, HV20={row["hv_20"]}%')

    log(f'  有效天数: {len(series)}')

    # 5. 输出
    log('\n[5] 输出...')
    write_output(series, dates)

    log(f'\n✅ 模块三完成')
    log(f'  JSON: {OUT_JSON}')
    log(f'  CSV:  {OUT_CSV}')

    # 打印汇总
    if series:
        latest = series[-1]
        pcr_vols = [s['pcr_vol'] for s in series if s.get('pcr_vol') is not None]
        avg_pcr = sum(pcr_vols) / len(pcr_vols) if pcr_vols else 0

        log(f'\n{"─"*55}')
        log(f'📊 期权套利汇总 ({end_date})')
        log(f'{"─"*55}')
        log(f'  PCR(成交量): {latest.get("pcr_vol", "N/A")}  (30日均值: {avg_pcr:.4f})')
        log(f'  PCR(持仓量): {latest.get("pcr_oi", "N/A")}')
        log(f'  HV20(300):   {latest.get("hv_20", "N/A")}%')
        log(f'  总成交量:    {latest.get("total_vol", 0):,.0f}')
        log(f'  总成交额:    {latest.get("total_amount", 0):,.0f} 万')


if __name__ == '__main__':
    main()
