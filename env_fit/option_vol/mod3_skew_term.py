#!/usr/bin/env python3
"""
模块3：Skew + Term Structure

目标：
- 估算近月与次近月的 ATM IV
- 估算近月 OTM put / OTM call 的 IV
- 构造：
  1) put skew = OTM put IV - ATM IV
  2) call skew = OTM call IV - ATM IV
  3) term slope = near IV - next IV

说明：
- 用 Black-76 从期权价格反推 IV
- 优先使用 near / next 两个月份
- 选择最接近 ATM 的 call/put，以及近似 5% OTM 的 put/call
"""

import json
import math
import os
from datetime import datetime

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
MOD2_JSON = os.path.join(BASE, 'mod2_iv_spread.json')
OUT_JSON = os.path.join(BASE, 'mod3_skew_term.json')

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
RISK_FREE_RATE = 0.015
TARGET_SYMBOLS = ['AU', 'AG', 'CU', 'SC', 'SA', 'RU', 'NI', 'FG', 'RB']
EXCHANGE_MAP = {
    'AU': 'SHFE', 'AG': 'SHFE', 'CU': 'SHFE', 'SC': 'INE', 'SA': 'ZCE',
    'RU': 'SHFE', 'NI': 'SHFE', 'FG': 'ZCE', 'RB': 'SHFE'
}


def tushare_call(api_name, params, fields):
    r = requests.post(
        TUSHARE_URL,
        json={'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params, 'fields': fields},
        timeout=30,
        proxies={'http': None, 'https': None},
    )
    d = r.json()
    if d.get('code') != 0:
        raise RuntimeError(f'{api_name} failed: {d.get("msg")}')
    fs = d['data']['fields']
    return [dict(zip(fs, row)) for row in d['data']['items']]


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


def load_mod2():
    if not os.path.exists(MOD2_JSON):
        return {}
    with open(MOD2_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_trade_date():
    cal_rows = tushare_call('trade_cal', {'start_date': '20260301', 'end_date': '20260331'}, 'cal_date,is_open')
    opens = [r['cal_date'] for r in cal_rows if int(r['is_open']) == 1]
    return opens[-1]


def get_live_options(symbol, trade_date):
    exchange = EXCHANGE_MAP[symbol]
    rows = tushare_call('opt_basic', {'exchange': exchange}, 'ts_code,name,call_put,exercise_price,list_date,delist_date,exchange')
    rows = [r for r in rows if str(r['ts_code']).startswith(symbol) and r['delist_date'] >= trade_date]
    rows.sort(key=lambda x: (x['delist_date'], float(x['exercise_price'])))
    return rows


def fut_code_from_opt(ts_code):
    raw = ts_code.split('.')[0]
    idx = max(raw.rfind('C'), raw.rfind('P'))
    return raw[:idx] + '.' + ts_code.split('.')[1]


def get_fut_price(fut_code, trade_date):
    rows = tushare_call('fut_daily', {'ts_code': fut_code, 'start_date': trade_date, 'end_date': trade_date}, 'ts_code,trade_date,close,settle')
    if not rows:
        return None
    return float(rows[0]['close'])


def get_opt_px(ts_code, trade_date):
    rows = tushare_call('opt_daily', {'ts_code': ts_code, 'start_date': trade_date, 'end_date': trade_date}, 'ts_code,trade_date,close,settle,vol,amount,oi')
    if not rows:
        return None
    row = rows[0]
    px = row.get('close') or row.get('settle')
    if px in (None, ''):
        return None
    return {
        'price': float(px),
        'vol': float(row.get('vol') or 0),
        'oi': float(row.get('oi') or 0),
    }


def pick_month_groups(rows):
    delists = sorted(list({r['delist_date'] for r in rows}))
    if not delists:
        return None, None
    near = [r for r in rows if r['delist_date'] == delists[0]]
    nextm = [r for r in rows if len(delists) > 1 and r['delist_date'] == delists[1]]
    return near, nextm


def days_to_expiry(trade_date, delist_date):
    d0 = datetime.strptime(trade_date, '%Y%m%d')
    d1 = datetime.strptime(delist_date, '%Y%m%d')
    return max((d1 - d0).days, 1)


def pick_by_target(options, F, opt_type, target):
    subset = [r for r in options if r['call_put'] == opt_type]
    if not subset:
        return None
    subset.sort(key=lambda x: abs(float(x['exercise_price']) - target))
    return subset[0]


def iv_for_contract(contract, F, trade_date):
    px = get_opt_px(contract['ts_code'], trade_date)
    if not px:
        return None, None
    K = float(contract['exercise_price'])
    T = days_to_expiry(trade_date, contract['delist_date']) / 365.0
    iv = implied_vol(px['price'], F, K, T, RISK_FREE_RATE, contract['call_put'])
    return iv, px


def score_skew_term(put_skew, call_skew, term_slope):
    # put skew 越高越适合卖 put；term_slope > 0 代表近月更贵，偏短期恐慌
    skew_score = 50
    if put_skew is not None:
        skew_score = max(0, min(100, round(50 + put_skew * 400)))
    term_score = 50
    if term_slope is not None:
        term_score = max(0, min(100, round(50 + term_slope * 300)))
    return skew_score, term_score


def main():
    trade_date = get_trade_date()
    rows_out = []

    for symbol in TARGET_SYMBOLS:
        try:
            rows = get_live_options(symbol, trade_date)
            if not rows:
                continue
            near, nextm = pick_month_groups(rows)
            if not near:
                continue

            fut_code = fut_code_from_opt(near[0]['ts_code'])
            F = get_fut_price(fut_code, trade_date)
            if not F:
                continue

            # near month ATM / OTM
            near_atm_call = pick_by_target(near, F, 'C', F)
            near_atm_put = pick_by_target(near, F, 'P', F)
            near_otm_put = pick_by_target(near, F, 'P', F * 0.95)
            near_otm_call = pick_by_target(near, F, 'C', F * 1.05)

            iv_atm_call, px_atm_call = iv_for_contract(near_atm_call, F, trade_date) if near_atm_call else (None, None)
            iv_atm_put, px_atm_put = iv_for_contract(near_atm_put, F, trade_date) if near_atm_put else (None, None)
            atm_list = [x for x in [iv_atm_call, iv_atm_put] if x is not None]
            near_atm_iv = sum(atm_list) / len(atm_list) if atm_list else None

            iv_otm_put, px_otm_put = iv_for_contract(near_otm_put, F, trade_date) if near_otm_put else (None, None)
            iv_otm_call, px_otm_call = iv_for_contract(near_otm_call, F, trade_date) if near_otm_call else (None, None)

            put_skew = (iv_otm_put - near_atm_iv) if (iv_otm_put is not None and near_atm_iv is not None) else None
            call_skew = (iv_otm_call - near_atm_iv) if (iv_otm_call is not None and near_atm_iv is not None) else None

            next_atm_iv = None
            next_fut_code = None
            term_slope = None
            if nextm:
                next_fut_code = fut_code_from_opt(nextm[0]['ts_code'])
                F2 = get_fut_price(next_fut_code, trade_date)
                if F2:
                    next_atm_call = pick_by_target(nextm, F2, 'C', F2)
                    next_atm_put = pick_by_target(nextm, F2, 'P', F2)
                    iv2c, _ = iv_for_contract(next_atm_call, F2, trade_date) if next_atm_call else (None, None)
                    iv2p, _ = iv_for_contract(next_atm_put, F2, trade_date) if next_atm_put else (None, None)
                    iv2s = [x for x in [iv2c, iv2p] if x is not None]
                    if iv2s:
                        next_atm_iv = sum(iv2s) / len(iv2s)
            if near_atm_iv is not None and next_atm_iv is not None:
                term_slope = near_atm_iv - next_atm_iv

            skew_score, term_score = score_skew_term(put_skew, call_skew, term_slope)
            rows_out.append({
                'symbol': symbol,
                'trade_date': trade_date,
                'fut_code_near': fut_code,
                'fut_price_near': round(F, 4),
                'near_atm_iv': round(near_atm_iv, 4) if near_atm_iv is not None else None,
                'next_atm_iv': round(next_atm_iv, 4) if next_atm_iv is not None else None,
                'term_slope': round(term_slope, 4) if term_slope is not None else None,
                'put_skew': round(put_skew, 4) if put_skew is not None else None,
                'call_skew': round(call_skew, 4) if call_skew is not None else None,
                'skew_score': skew_score,
                'term_score': term_score,
                'near_atm_call': near_atm_call['ts_code'] if near_atm_call else None,
                'near_atm_put': near_atm_put['ts_code'] if near_atm_put else None,
                'near_otm_put': near_otm_put['ts_code'] if near_otm_put else None,
                'near_otm_call': near_otm_call['ts_code'] if near_otm_call else None,
            })
        except Exception as e:
            rows_out.append({'symbol': symbol, 'error': str(e)})

    rows_out.sort(key=lambda x: x.get('skew_score', -1), reverse=True)
    out = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'module': 'option_vol.mod3_skew_term',
            'source': 'tushare public + Black76',
        },
        'symbols': rows_out,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f'输出: {OUT_JSON}')
    for row in rows_out[:5]:
        if 'error' in row:
            print(f"  {row['symbol']}: error={row['error']}")
        else:
            print(f"  {row['symbol']}: put_skew={row['put_skew']} term={row['term_slope']} skew_score={row['skew_score']}")


if __name__ == '__main__':
    main()
