#!/usr/bin/env python3
"""
模块1：商品期权双卖环境（MVP）

目标：
- 基于商品期货日线，计算成交额前10品种的20日已实现波动率（RV）
- 用历史分位数识别“波动率极值”
- 结合 commodity_cta 的 PCA 环境类型，区分：
  - 恐慌性高波动（双卖机会）
  - 趋势性高波动（双卖危险）

说明：
- 这是 MVP 版本，不依赖期权 IV 数据
- 后续接入 iFinD 后，再补 mod2_iv_spread / mod3_skew
"""

import csv
import json
import math
import os
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CTA_DIR = os.path.join(os.path.dirname(BASE), 'commodity_cta')
FUT_CSV = os.path.join(CTA_DIR, 'fut_daily.csv')
PCA_JSON = os.path.join(CTA_DIR, 'mod1b_pca_engine.json')
OUT_JSON = os.path.join(BASE, 'mod1_rv_regime.json')

TOP_N = 10
RV_WINDOW = 20
PCTILE_WINDOW = 120
MIN_HISTORY = 60
TRADING_DAYS = 244

OPTIONABLE_SYMBOLS = {
    'AU', 'AG', 'CU', 'AL', 'ZN', 'RU', 'SC', 'I', 'PG', 'MA', 'CF', 'SR',
    'PP', 'TA', 'RM', 'OI', 'PK', 'SA', 'FG', 'RB', 'NI', 'SN', 'LU', 'BC',
    'SI', 'BR', 'AO', 'LC', 'EC'
}

SECTOR_MAP = {
    'AU': '贵金属', 'AG': '贵金属',
    'CU': '有色金属', 'AL': '有色金属', 'ZN': '有色金属', 'NI': '有色金属', 'SN': '有色金属', 'AO': '有色金属', 'BC': '有色金属', 'SI': '有色金属',
    'JM': '黑色系', 'RB': '黑色系', 'I': '黑色系',
    'SC': '能源化工', 'RU': '能源化工', 'FG': '能源化工', 'SA': '能源化工', 'TA': '能源化工', 'MA': '能源化工', 'PP': '能源化工', 'PG': '能源化工', 'LU': '能源化工', 'BR': '能源化工',
    'P': '农产品', 'CF': '农产品', 'SR': '农产品', 'RM': '农产品', 'OI': '农产品', 'PK': '农产品'
}


def load_fut_daily():
    series = defaultdict(list)
    with open(FUT_CSV, 'r', encoding='gb18030', newline='') as f:
        for row in csv.DictReader(f):
            sym = (row.get('symbol') or '').strip()
            close = row.get('close') or ''
            trade_date = row.get('trade_date') or ''
            amount = row.get('amount') or '0'
            if not sym or not trade_date or not close:
                continue
            try:
                close_f = float(close)
                amount_f = float(amount)
            except ValueError:
                continue
            series[sym].append({
                'date': trade_date,
                'close': close_f,
                'amount': amount_f,
            })
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


def get_top_optionable_symbols(series, top_n=TOP_N):
    ranking = []
    for sym, rows in series.items():
        if sym not in OPTIONABLE_SYMBOLS:
            continue
        amts = [r['amount'] for r in rows if r['amount'] > 0]
        if len(amts) < MIN_HISTORY:
            continue
        avg_amt = sum(amts) / len(amts)
        ranking.append((sym, avg_amt, len(rows)))
    ranking.sort(key=lambda x: x[1], reverse=True)
    return ranking[:top_n]


def calc_returns(rows):
    out = []
    for i in range(1, len(rows)):
        prev_close = rows[i - 1]['close']
        cur_close = rows[i]['close']
        if prev_close <= 0 or cur_close <= 0:
            continue
        ret = cur_close / prev_close - 1
        out.append({'date': rows[i]['date'], 'ret': ret})
    return out


def rolling_rv(returns, window=RV_WINDOW):
    rv_series = []
    for i in range(window - 1, len(returns)):
        block = [x['ret'] for x in returns[i - window + 1:i + 1]]
        if not block:
            continue
        mean = sum(block) / len(block)
        var = sum((x - mean) ** 2 for x in block) / len(block)
        rv = math.sqrt(var * TRADING_DAYS)
        rv_series.append({'date': returns[i]['date'], 'rv': rv})
    return rv_series


def add_pctile(rv_series, pctile_window=PCTILE_WINDOW):
    out = []
    for i, row in enumerate(rv_series):
        start = max(0, i - pctile_window + 1)
        hist = [x['rv'] for x in rv_series[start:i + 1]]
        if len(hist) < 20:
            pctile = None
        else:
            pctile = sum(1 for x in hist if x <= row['rv']) / len(hist)
        out.append({
            'date': row['date'],
            'rv': row['rv'],
            'rv_pctile': pctile,
        })
    return out


def load_pca_env():
    if not os.path.exists(PCA_JSON):
        return None
    with open(PCA_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    rolling = data.get('rolling', [])
    if not rolling:
        return None
    latest = rolling[-1]
    loading_map = {}
    latest_loadings = data.get('latest_loadings', {}).get('loadings', [])
    for item in latest_loadings:
        loading_map[item['symbol']] = abs(item.get('pc1_loading', 0))
    return {
        'date': latest.get('date'),
        'env_type': latest.get('env_type'),
        'momentum_signal': latest.get('momentum_signal'),
        'pc1_ratio': latest.get('pc1_ratio'),
        'pca_friendly': latest.get('pca_friendly'),
        'loading_map': loading_map,
    }


def rv_accel(rv_series):
    if len(rv_series) < 6:
        return None
    recent = [x['rv'] for x in rv_series[-5:]]
    base = [x['rv'] for x in rv_series[-20:]] if len(rv_series) >= 20 else [x['rv'] for x in rv_series]
    if not recent or not base:
        return None
    recent_avg = sum(recent) / len(recent)
    base_avg = sum(base) / len(base)
    if base_avg <= 0:
        return None
    return recent_avg / base_avg


def score_symbol(latest_rv_pctile, accel, env_type, loading_abs):
    odds_score = 0
    if latest_rv_pctile is not None:
        odds_score = max(0, min(100, round(latest_rv_pctile * 100)))

    env_score_map = {
        '全市场震荡': 90,
        '温和趋势': 65,
        '双阵营对抗': 55,
        '单一趋势主导': 20,
    }
    env_score = env_score_map.get(env_type, 50)

    if accel is None:
        accel_score = 50
    elif accel < 0.9:
        accel_score = 90
    elif accel < 1.0:
        accel_score = 75
    elif accel < 1.15:
        accel_score = 55
    elif accel < 1.3:
        accel_score = 35
    else:
        accel_score = 15

    loading_abs = loading_abs or 0
    loading_score = max(0, min(100, round((1 - min(loading_abs, 0.4) / 0.4) * 100)))

    tail_risk_score = round(env_score * 0.5 + accel_score * 0.3 + loading_score * 0.2)
    sell_score = round(odds_score * 0.55 + tail_risk_score * 0.45)

    if sell_score >= 80:
        signal = '🟢'
        label = '强烈双卖窗口'
    elif sell_score >= 60:
        signal = '🟡'
        label = '可考虑双卖'
    elif sell_score >= 40:
        signal = '⚪'
        label = '观望'
    else:
        signal = '🔴'
        label = '不宜双卖'

    return {
        'sell_score': sell_score,
        'signal': signal,
        'label': label,
        'breakdown': {
            'odds_score': odds_score,
            'tail_risk_score': tail_risk_score,
            'env_score': env_score,
            'accel_score': accel_score,
            'loading_score': loading_score,
        }
    }


def build_regime(symbol_rows):
    sellable = [x for x in symbol_rows if x['sell_score'] >= 60]
    avg_score = round(sum(x['sell_score'] for x in symbol_rows) / len(symbol_rows), 1) if symbol_rows else 0
    breadth = len(set(x['sector'] for x in sellable))

    if len(sellable) >= 5 and avg_score >= 70 and breadth >= 3:
        label = 'STRONG_SELL_VOL'
        desc = '系统性恐慌溢价，全面双卖窗口'
    elif len(sellable) >= 3 and avg_score >= 60:
        label = 'SELECTIVE_SELL'
        desc = '部分品种有机会，精选双卖'
    elif len(sellable) >= 1 or avg_score >= 45:
        label = 'NEUTRAL'
        desc = '局部有溢价，保持观察'
    else:
        label = 'AVOID_SELLING'
        desc = '趋势性波动或溢价不足，不宜双卖'

    top3 = sorted(symbol_rows, key=lambda x: x['sell_score'], reverse=True)[:3]
    return {
        'label': label,
        'description': desc,
        'avg_sell_score': avg_score,
        'n_sellable': len(sellable),
        'sector_breadth': breadth,
        'top3_symbols': [{'symbol': x['symbol'], 'sell_score': x['sell_score']} for x in top3]
    }


def main():
    os.makedirs(BASE, exist_ok=True)
    series = load_fut_daily()
    top_symbols = get_top_optionable_symbols(series, TOP_N)
    pca = load_pca_env() or {}
    loading_map = pca.get('loading_map', {})

    symbol_rows = []
    for sym, avg_amt, n_days in top_symbols:
        returns = calc_returns(series[sym])
        rv_series = add_pctile(rolling_rv(returns, RV_WINDOW), PCTILE_WINDOW)
        if not rv_series:
            continue
        latest = rv_series[-1]
        accel = rv_accel(rv_series)
        scored = score_symbol(
            latest.get('rv_pctile'),
            accel,
            pca.get('env_type'),
            loading_map.get(sym, 0),
        )
        symbol_rows.append({
            'symbol': sym,
            'sector': SECTOR_MAP.get(sym, '其他'),
            'avg_amount_wan': round(avg_amt, 1),
            'n_days': n_days,
            'rv_20d': round(latest['rv'], 4),
            'rv_pctile_120d': round(latest['rv_pctile'], 4) if latest.get('rv_pctile') is not None else None,
            'rv_accel': round(accel, 4) if accel is not None else None,
            'pca_env': pca.get('env_type'),
            'pc1_loading_abs': round(loading_map.get(sym, 0), 4),
            **scored,
        })

    symbol_rows.sort(key=lambda x: x['sell_score'], reverse=True)
    regime = build_regime(symbol_rows)

    result = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'module': 'option_vol.mod1_rv_regime',
            'version': 'mvp',
            'top_n': TOP_N,
            'rv_window': RV_WINDOW,
            'pctile_window': PCTILE_WINDOW,
            'data_source': 'commodity_cta/fut_daily.csv + commodity_cta/mod1b_pca_engine.json',
        },
        'regime': regime,
        'pca_context': {
            'date': pca.get('date'),
            'env_type': pca.get('env_type'),
            'momentum_signal': pca.get('momentum_signal'),
            'pc1_ratio': pca.get('pc1_ratio'),
            'pca_friendly': pca.get('pca_friendly'),
        },
        'symbols': symbol_rows,
    }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'输出: {OUT_JSON}')
    print(f"Regime: {regime['label']} | avg={regime['avg_sell_score']} | n_sellable={regime['n_sellable']}")
    for row in symbol_rows[:5]:
        print(f"  {row['symbol']:>4s} {row['signal']} score={row['sell_score']} rv_pct={row['rv_pctile_120d']} env={row['pca_env']}")


if __name__ == '__main__':
    main()
