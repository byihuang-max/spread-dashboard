#!/usr/bin/env python3
"""
HV 长序列（独立模块）
只拉沪深300指数日收盘，算 HV20 + HV60 长序列，供套利/期权波动率看板使用。
与 mod3_option_arb.py 解耦——后者只跑最近30天（期权合约数据耗额度），
这个模块专门负责提供长窗口的波动率历史。

输出：hv_long.json（默认起点 2023-01-01）
"""
import os, json, time, math, requests
from datetime import datetime, timedelta

TS_URL = 'https://api.tushare.pro'
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, 'hv_long.json')

# 起点：覆盖 fund_nav 的数据范围（2025-01-01 起），留 60 天缓冲给 HV60
INDEX_CODE = '000300.SH'
START_DATE = '20241001'   # 往前多留 3 个月 buffer
HV_WINDOWS = [20, 60]


def log(msg):
    print(msg, flush=True)


def ts_api(api_name, params, fields=None):
    body = {'api_name': api_name, 'token': TS_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TS_URL, json=body, timeout=60,
                              proxies={'http': None, 'https': None})
            data = r.json()
            if data.get('code') == 0 and data.get('data', {}).get('items'):
                cols = data['data']['fields']
                rows = data['data']['items']
                return [dict(zip(cols, row)) for row in rows]
            elif data.get('code') == -2001:
                log('  [限流, 等10s...]')
                time.sleep(10)
                continue
            else:
                log(f'  [tushare 返回异常: {data.get("msg")}]')
                return []
        except Exception as e:
            log(f'  [异常: {e}, retry {attempt+1}]')
            time.sleep(3)
    return []


def compute_hv(closes, window):
    """返回每个交易日的 HV（年化，%）序列，长度与 closes 相同；前 window 天为 None"""
    if len(closes) < window + 1:
        return [None] * len(closes)
    log_rets = []
    for i in range(1, len(closes)):
        prev, curr = closes[i-1], closes[i]
        if prev and curr and prev > 0 and curr > 0:
            log_rets.append(math.log(curr / prev))
        else:
            log_rets.append(None)
    # 对齐：log_rets[i] 对应 closes[i+1]
    hv_series = [None] * len(closes)
    for i in range(window, len(closes)):
        window_rets = log_rets[i-window:i]
        if None in window_rets:
            continue
        mean = sum(window_rets) / len(window_rets)
        var = sum((r - mean) ** 2 for r in window_rets) / (len(window_rets) - 1)
        hv = math.sqrt(var) * math.sqrt(252) * 100
        hv_series[i] = round(hv, 2)
    return hv_series


def main():
    today = datetime.now().strftime('%Y%m%d')
    log(f'[HV long] 拉 {INDEX_CODE} 日线 {START_DATE} ~ {today}')
    rows = ts_api('index_daily', {
        'ts_code': INDEX_CODE,
        'start_date': START_DATE,
        'end_date': today,
    }, fields='trade_date,close')
    if not rows:
        log('❌ 未拉到数据')
        return

    # 按日期升序
    rows.sort(key=lambda r: r['trade_date'])
    dates = [r['trade_date'] for r in rows]
    closes = [float(r['close']) for r in rows]
    log(f'  -> {len(dates)} 个交易日 ({dates[0]} ~ {dates[-1]})')

    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'index_code': INDEX_CODE,
        'index_name': '沪深300',
        'start_date': dates[0],
        'end_date': dates[-1],
        'n_days': len(dates),
        'series': [],
    }

    hv_by_window = {w: compute_hv(closes, w) for w in HV_WINDOWS}

    for i, d in enumerate(dates):
        row = {'date': d, 'close': round(closes[i], 2)}
        for w in HV_WINDOWS:
            row[f'hv_{w}'] = hv_by_window[w][i]
        result['series'].append(row)

    # summary
    latest = result['series'][-1]
    result['summary'] = {
        'latest_date': latest['date'],
        **{f'latest_hv_{w}': latest.get(f'hv_{w}') for w in HV_WINDOWS},
    }

    # percentile of latest HV20
    hv20_vals = [r['hv_20'] for r in result['series'] if r.get('hv_20') is not None]
    if hv20_vals:
        latest_hv20 = latest.get('hv_20')
        if latest_hv20 is not None:
            rank = sum(1 for v in hv20_vals if v <= latest_hv20) / len(hv20_vals)
            result['summary']['hv_20_pct_rank'] = round(rank * 100, 1)
            result['summary']['hv_20_mean'] = round(sum(hv20_vals) / len(hv20_vals), 2)

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    log(f'✅ 输出：{OUT_JSON}')
    log(f'  最新 HV20={latest.get("hv_20")}% / HV60={latest.get("hv_60")}%  '
        f'分位数={result["summary"].get("hv_20_pct_rank")}%')


if __name__ == '__main__':
    main()
