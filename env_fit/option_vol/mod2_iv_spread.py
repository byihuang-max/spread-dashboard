#!/usr/bin/env python3
"""
模块2：IV-RV Spread（商品期权双卖核心赔率层）

数据源：
- Tushare 公有 API：opt_basic / opt_daily / fut_daily
- 本地输出：mod2_iv_spread.json

逻辑：
1. 对可选商品池（当前默认：成交额前 + 有期权的品种）定位近月主力期权
2. 选取最接近平值（ATM）的 call / put
3. 用 Black-76 反推 ATM IV（call 与 put 均值）
4. 与 mod1 的 20日 RV 比较，得到 IV-RV spread
5. 输出 spread 分位数和卖方赔率评分
"""

import csv
import json
import math
import os
from datetime import datetime

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
MOD1_JSON = os.path.join(BASE, 'mod1_rv_regime.json')
OUT_JSON = os.path.join(BASE, 'mod2_iv_spread.json')

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
RISK_FREE_RATE = 0.015

# 先做这些有期权且流动性好的品种
TARGET_SYMBOLS = ['AU', 'AG', 'CU', 'SC', 'SA', 'RU', 'NI', 'FG', 'RB']
EXCHANGE_MAP = {
    'AU': 'SHFE', 'AG': 'SHFE', 'CU': 'SHFE', 'SC': 'INE', 'SA': 'ZCE',
    'RU': 'SHFE', 'NI': 'SHFE', 'FG': 'ZCE', 'RB': 'SHFE'
}


def tushare_call(api_name, params, fields):
    r = requests.post(
        TUSHARE_URL,
        json={
            'api_name': api_name,
            'token': TUSHARE_TOKEN,
            'params': params,
            'fields': fields,
        },
        timeout=30,
        proxies={'http': None, 'https': None},
    )
    d = r.json()
    if d.get('code') != 0:
        raise RuntimeError(f'{api_name} failed: {d.get("msg")}')
    fields_out = d['data']['fields']
    items = d['data']['items']
    return [dict(zip(fields_out, row)) for row in items]


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76_price(F, K, T, r, sigma, opt_type):
    intrinsic = math.exp(-r * T) * max(F - K, 0.0) if opt_type == 'C' else math.exp(-r * T) * max(K - F, 0.0)
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return intrinsic
    vol_sqrt = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / vol_sqrt
    d2 = d1 - vol_sqrt
    if opt_type == 'C':
        return math.exp(-r * T) * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return math.exp(-r * T) * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def implied_vol(price, F, K, T, r, opt_type):
    if price is None or price <= 0 or F <= 0 or K <= 0 or T <= 0:
        return None
    lo, hi = 1e-4, 3.0
    for _ in range(100):
        mid = (lo + hi) / 2
        val = black76_price(F, K, T, r, mid, opt_type)
        if abs(val - price) < 1e-7:
            return mid
        if val > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def load_mod1():
    with open(MOD1_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_latest_trade_date(symbol):
    exchange = EXCHANGE_MAP[symbol]
    rows = tushare_call('opt_basic', {'exchange': exchange}, 'ts_code,name,call_put,exercise_price,list_date,delist_date,exchange')
    dates = sorted({r['list_date'] for r in rows if str(r['ts_code']).startswith(symbol)})
    return dates[-1] if dates else None


def pick_atm_options(symbol):
    exchange = EXCHANGE_MAP[symbol]
    rows = tushare_call('opt_basic', {'exchange': exchange}, 'ts_code,name,call_put,exercise_price,list_date,delist_date,exchange')
    rows = [r for r in rows if str(r['ts_code']).startswith(symbol)]
    if not rows:
        return None

    # 用全市场最新交易日作为当前日期锚点
    cal_rows = tushare_call('trade_cal', {'start_date': '20260301', 'end_date': '20260331'}, 'cal_date,is_open')
    open_dates = [r['cal_date'] for r in cal_rows if int(r['is_open']) == 1]
    if not open_dates:
        return None
    trade_date = open_dates[-1]

    # 仅保留未到期合约，优先最近到期月
    alive_rows = [r for r in rows if r['delist_date'] >= trade_date]
    if not alive_rows:
        return None
    alive_rows = sorted(alive_rows, key=lambda x: (x['delist_date'], float(x['exercise_price'])))
    target_date = alive_rows[0]['delist_date']
    same_month = [r for r in alive_rows if r['delist_date'] == target_date]

    # 用合约代码反推对应期货月份，例如 AU2606C920 -> AU2606.SHF
    sample_code = same_month[0]['ts_code']
    underlying = sample_code.split('.')[0]
    idx = max(underlying.rfind('C'), underlying.rfind('P'))
    fut_code = underlying[:idx] + '.' + sample_code.split('.')[1]

    fut_rows = tushare_call('fut_daily', {'ts_code': fut_code, 'start_date': trade_date, 'end_date': trade_date}, 'ts_code,trade_date,close,settle')
    if not fut_rows:
        return None
    latest_fut = fut_rows[0]
    F = float(latest_fut['close'])

    calls = [r for r in same_month if r['call_put'] == 'C']
    puts = [r for r in same_month if r['call_put'] == 'P']
    if not calls or not puts:
        return None

    calls.sort(key=lambda x: abs(float(x['exercise_price']) - F))
    puts.sort(key=lambda x: abs(float(x['exercise_price']) - F))
    call = calls[0]
    put = puts[0]
    return {
        'trade_date': trade_date,
        'fut_code': fut_code,
        'fut_price': F,
        'call': call,
        'put': put,
        'delist_date': call['delist_date'],
    }


def get_option_price(ts_code, trade_date):
    rows = tushare_call('opt_daily', {'ts_code': ts_code, 'start_date': trade_date, 'end_date': trade_date}, 'ts_code,trade_date,close,settle,vol,amount,oi')
    if not rows:
        return None
    row = rows[0]
    price = row.get('close') or row.get('settle')
    return {
        'price': float(price) if price not in (None, '') else None,
        'vol': float(row.get('vol') or 0),
        'oi': float(row.get('oi') or 0),
        'amount': float(row.get('amount') or 0),
    }


def days_to_expiry(trade_date, delist_date):
    d0 = datetime.strptime(trade_date, '%Y%m%d')
    d1 = datetime.strptime(delist_date, '%Y%m%d')
    return max((d1 - d0).days, 1)


def main():
    mod1 = load_mod1()
    rv_map = {x['symbol']: x for x in mod1.get('symbols', [])}
    output_rows = []

    for symbol in TARGET_SYMBOLS:
        if symbol not in rv_map:
            continue
        try:
            picked = pick_atm_options(symbol)
            if not picked:
                continue
            trade_date = picked['trade_date']
            T = days_to_expiry(trade_date, picked['delist_date']) / 365.0
            F = picked['fut_price']

            call_meta = picked['call']
            put_meta = picked['put']
            Kc = float(call_meta['exercise_price'])
            Kp = float(put_meta['exercise_price'])

            call_px = get_option_price(call_meta['ts_code'], trade_date)
            put_px = get_option_price(put_meta['ts_code'], trade_date)
            if not call_px or not put_px:
                continue

            iv_call = implied_vol(call_px['price'], F, Kc, T, RISK_FREE_RATE, 'C')
            iv_put = implied_vol(put_px['price'], F, Kp, T, RISK_FREE_RATE, 'P')
            ivs = [x for x in [iv_call, iv_put] if x is not None]
            if not ivs:
                continue
            atm_iv = sum(ivs) / len(ivs)

            rv_20d = rv_map[symbol].get('rv_20d')
            spread = atm_iv - rv_20d if rv_20d is not None else None
            odds_score = None
            if spread is not None:
                # 简单映射：spread 0.00→50, 0.05→70, 0.10→90
                odds_score = max(0, min(100, round(50 + spread * 400)))

            output_rows.append({
                'symbol': symbol,
                'trade_date': trade_date,
                'fut_code': picked['fut_code'],
                'fut_price': round(F, 4),
                'days_to_expiry': round(T * 365),
                'atm_call': call_meta['ts_code'],
                'atm_put': put_meta['ts_code'],
                'call_strike': Kc,
                'put_strike': Kp,
                'call_price': call_px['price'],
                'put_price': put_px['price'],
                'iv_call': round(iv_call, 4) if iv_call is not None else None,
                'iv_put': round(iv_put, 4) if iv_put is not None else None,
                'atm_iv': round(atm_iv, 4),
                'rv_20d': rv_20d,
                'iv_rv_spread': round(spread, 4) if spread is not None else None,
                'odds_score_iv': odds_score,
                'call_vol': call_px['vol'],
                'put_vol': put_px['vol'],
                'call_oi': call_px['oi'],
                'put_oi': put_px['oi'],
            })
        except Exception as e:
            output_rows.append({
                'symbol': symbol,
                'error': str(e),
            })

    output_rows.sort(key=lambda x: x.get('odds_score_iv', -1), reverse=True)
    result = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'module': 'option_vol.mod2_iv_spread',
            'source': 'tushare public + Black76',
            'risk_free_rate': RISK_FREE_RATE,
        },
        'symbols': output_rows,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'输出: {OUT_JSON}')
    for row in output_rows[:5]:
        if 'error' in row:
            print(f"  {row['symbol']}: error={row['error']}")
        else:
            print(f"  {row['symbol']}: IV={row['atm_iv']:.4f} RV={row['rv_20d']:.4f} spread={row['iv_rv_spread']:+.4f}")


if __name__ == '__main__':
    main()
