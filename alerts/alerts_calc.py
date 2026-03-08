#!/usr/bin/env python3
"""
红灯预警 - 计算5维风险 + 综合评分
复用: liquidity/rates/crowding/option_sentiment 的cache/json
自有: valuation + limit_stats + market_amount
"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'alerts.json')

BASE = os.path.dirname(SCRIPT_DIR)  # gamt-dashboard
LIQUIDITY_CACHE = os.path.join(BASE, 'macro', 'liquidity', 'cache')
RATES_JSON = os.path.join(BASE, 'macro', 'rates', 'rates.json')
CROWDING_JSON = os.path.join(BASE, 'micro_flow', 'crowding', 'crowding.json')
OPTION_JSON = os.path.join(BASE, 'micro_flow', 'option_sentiment', 'option_sentiment.json')


def load_csv(directory, name):
    path = os.path.join(directory, name)
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def percentile_rank(series, value):
    """计算value在series中的分位数(0-100)"""
    if len(series) == 0 or value is None:
        return None
    return round(float((series < value).sum() / len(series) * 100), 1)


def calc():
    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'dimensions': {},
        'composite_score': 0,
        'composite_level': '',
        'alerts': [],  # 文字预警
    }

    scores = {}  # 每维度0-100 (100=最危险)

    # ═══════ 1. 流动性风险 ═══════
    liq = {'name': '💧 流动性风险', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    dr_df = load_csv(LIQUIDITY_CACHE, 'dr007.csv')
    shibor_df = load_csv(LIQUIDITY_CACHE, 'shibor.csv')

    if not dr_df.empty:
        dr_df['close'] = pd.to_numeric(dr_df['close'], errors='coerce')
        dr_df = dr_df.dropna(subset=['close']).sort_values('trade_date')
        latest_dr = float(dr_df.iloc[-1]['close'])
        ma20 = float(dr_df['close'].tail(20).mean())
        deviation = (latest_dr - ma20) / ma20 * 100

        liq['items'].append(f"DR007: {latest_dr:.2f}% (MA20: {ma20:.2f}%)")
        liq['trend'] = [{'date': str(int(r['trade_date']))[:4]+'-'+str(int(r['trade_date']))[4:6]+'-'+str(int(r['trade_date']))[6:8], 'value': round(float(r['close']), 3)}
                        for _, r in dr_df.iterrows()]

        # R-D价差
        if 'r007_close' in dr_df.columns:
            dr_df['r007_close'] = pd.to_numeric(dr_df['r007_close'], errors='coerce')
            latest_r = dr_df.dropna(subset=['r007_close']).iloc[-1]['r007_close'] if dr_df['r007_close'].notna().any() else None
            if latest_r is not None:
                spread = float(latest_r) - latest_dr
                liq['items'].append(f"R007-DR007价差: {spread*100:.0f}bp")
                if spread > 1.0:
                    liq['score'] += 30

        # 评分
        if latest_dr > 2.5:
            liq['score'] += 70
        elif latest_dr > 2.0:
            liq['score'] += 40
        elif deviation > 15:
            liq['score'] += 30

    if not shibor_df.empty:
        shibor_df['on'] = pd.to_numeric(shibor_df['on'], errors='coerce')
        latest_on = float(shibor_df.dropna(subset=['on']).iloc[-1]['on'])
        liq['items'].append(f"Shibor隔夜: {latest_on:.3f}%")
        if latest_on > 2.5:
            liq['score'] += 20

    liq['score'] = min(liq['score'], 100)
    scores['liquidity'] = liq['score']
    if liq['score'] >= 60:
        liq['level'] = '🔴'
        result['alerts'].append('💧 资金面紧张，DR007显著偏高')
    elif liq['score'] >= 30:
        liq['level'] = '🟡'
    result['dimensions']['liquidity'] = liq

    # ═══════ 2. 估值泡沫 ═══════
    val = {'name': '📊 估值泡沫', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    for code, name in [('000001', '上证'), ('000300', '沪深300'), ('399006', '创业板')]:
        df = load_csv(CACHE_DIR, f'valuation_{code}.csv')
        if not df.empty:
            df['pe_ttm'] = pd.to_numeric(df['pe_ttm'], errors='coerce')
            df = df.dropna(subset=['pe_ttm']).sort_values('trade_date')
            latest_pe = float(df.iloc[-1]['pe_ttm'])
            pct = percentile_rank(df['pe_ttm'], latest_pe)
            val['items'].append(f"{name} PE(TTM): {latest_pe:.1f} (分位: {pct:.0f}%)")

            if code == '000001':
                val['trend'] = [{'date': str(int(r['trade_date']))[:4]+'-'+str(int(r['trade_date']))[4:6]+'-'+str(int(r['trade_date']))[6:8], 'value': round(float(r['pe_ttm']), 1)}
                                for _, r in df.iterrows()]

            # 评分
            if pct is not None:
                if code == '000001':
                    if pct > 90: val['score'] += 40
                    elif pct > 75: val['score'] += 20
                elif code == '399006':
                    if pct > 90: val['score'] += 30
                    elif pct > 75: val['score'] += 15

    # 股债性价比 (EP - 10Y国债)
    rates_data = load_json(RATES_JSON)
    cn10y_list = rates_data.get('cn10y', [])
    if cn10y_list:
        cn10y_val = cn10y_list[-1]['value']
        sh_df = load_csv(CACHE_DIR, 'valuation_000001.csv')
        if not sh_df.empty:
            sh_df['pe_ttm'] = pd.to_numeric(sh_df['pe_ttm'], errors='coerce')
            latest_pe = float(sh_df.dropna(subset=['pe_ttm']).iloc[-1]['pe_ttm'])
            ep = 100 / latest_pe  # 盈利收益率
            equity_bond = round(ep - cn10y_val, 2)
            val['items'].append(f"股债性价比(EP-10Y): {equity_bond:.2f}%")
            if equity_bond < 0:
                val['score'] += 30
                result['alerts'].append('📊 股债性价比为负，股票相对债券无吸引力')
            elif equity_bond < 1:
                val['score'] += 15

    val['score'] = min(val['score'], 100)
    scores['valuation'] = val['score']
    if val['score'] >= 60:
        val['level'] = '🔴'
        result['alerts'].append('📊 市场估值处于历史高位区间')
    elif val['score'] >= 30:
        val['level'] = '🟡'
    result['dimensions']['valuation'] = val

    # ═══════ 3. 情绪过热 ═══════
    senti = {'name': '🔥 情绪过热', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 成交额
    amt_df = load_csv(CACHE_DIR, 'market_amount.csv')
    if not amt_df.empty:
        amt_df['amount'] = pd.to_numeric(amt_df['amount'], errors='coerce')
        amt_df = amt_df.dropna(subset=['amount']).sort_values('trade_date')
        latest_amt = float(amt_df.iloc[-1]['amount'])
        ma20_amt = float(amt_df['amount'].tail(20).mean())
        ratio = latest_amt / ma20_amt if ma20_amt > 0 else 1
        senti['items'].append(f"上证成交额/MA20: {ratio:.2f}x")
        senti['trend'] = [{'date': str(int(r['trade_date']))[:4]+'-'+str(int(r['trade_date']))[4:6]+'-'+str(int(r['trade_date']))[6:8], 'value': round(float(r['amount']) / 1e8, 1)}
                          for _, r in amt_df.iterrows()]

        if ratio > 1.8:
            senti['score'] += 40
        elif ratio > 1.5:
            senti['score'] += 20

    # 涨跌停
    limit_df = load_csv(CACHE_DIR, 'limit_stats.csv')
    if not limit_df.empty:
        limit_df = limit_df.sort_values('trade_date')
        latest_up = int(limit_df.iloc[-1]['up_limit'])
        latest_down = int(limit_df.iloc[-1]['down_limit'])
        senti['items'].append(f"涨停: {latest_up}只 | 跌停: {latest_down}只")

        if latest_up > 80:
            senti['score'] += 25
        if latest_down > 50:
            senti['score'] += 20
            result['alerts'].append(f'🔥 跌停{latest_down}只，恐慌情绪蔓延')

    # 融资买入占比（复用crowding）
    margin_df = load_csv(os.path.join(BASE, 'micro_flow', 'crowding', 'cache'), 'margin.csv')
    if not margin_df.empty:
        margin_df['rzye'] = pd.to_numeric(margin_df.get('rzye', pd.Series()), errors='coerce')
        if 'rzye' in margin_df.columns and margin_df['rzye'].notna().any():
            latest_rz = float(margin_df.sort_values('trade_date').iloc[-1]['rzye'])
            senti['items'].append(f"融资余额: {latest_rz/1e8:.0f}亿")

    senti['score'] = min(senti['score'], 100)
    scores['sentiment'] = senti['score']
    if senti['score'] >= 60:
        senti['level'] = '🔴'
        result['alerts'].append('🔥 市场情绪过热，成交放量+涨停家数异常')
    elif senti['score'] >= 30:
        senti['level'] = '🟡'
    result['dimensions']['sentiment'] = senti

    # ═══════ 4. 外部冲击 ═══════
    ext = {'name': '🌍 外部冲击', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 中美利差
    rates = load_json(RATES_JSON)
    spread_list = rates.get('spread', [])
    if spread_list:
        latest_spread = spread_list[-1]['spread']
        ext['items'].append(f"中美利差: {latest_spread:+.2f}%")
        ext['trend'] = spread_list[-30:]  # 最近30天

        if latest_spread < -2.0:
            ext['score'] += 40
            result['alerts'].append(f'🌍 中美利差{latest_spread:+.2f}%，资金外流压力大')
        elif latest_spread < -1.5:
            ext['score'] += 20

        # 周度变化
        if len(spread_list) >= 6:
            week_ago = spread_list[-6]['spread']
            weekly_chg = latest_spread - week_ago
            if abs(weekly_chg) > 0.3:
                ext['items'].append(f"利差周变化: {weekly_chg:+.2f}%")
                ext['score'] += 15

    # 汇率
    fx = rates.get('fx', {})
    cnh = fx.get('USDCNH.FX', {})
    if cnh.get('latest'):
        ext['items'].append(f"USDCNH: {cnh['latest']:.4f}")
        if cnh.get('change') and abs(cnh['change']) > 0.05:
            ext['score'] += 20
            result['alerts'].append(f"🌍 USDCNH日波动{cnh['change']:+.4f}，汇率异动")

    # A股版VIX：用期权IV分位代替
    opt_data = load_json(OPTION_JSON)
    if opt_data:
        for underlying in opt_data.get('underlyings', []):
            if underlying.get('code') in ('000300', '510300'):
                summary = underlying.get('summary', {})
                iv_pct = summary.get('atm_iv_pct')
                if iv_pct is not None:
                    ext['items'].append(f"300期权IV分位: {iv_pct:.0f}%")
                    if iv_pct > 80:
                        ext['score'] += 25
                        result['alerts'].append(f'🌍 300期权IV分位{iv_pct:.0f}%，隐含波动率偏高')
                break

    ext['score'] = min(ext['score'], 100)
    scores['external'] = ext['score']
    if ext['score'] >= 60:
        ext['level'] = '🔴'
    elif ext['score'] >= 30:
        ext['level'] = '🟡'
    result['dimensions']['external'] = ext

    # ═══════ 5. 微观恶化 ═══════
    micro = {'name': '🏃 微观恶化', 'level': '🟢', 'score': 0, 'items': [], 'trend': []}

    # 北向资金
    nb_df = load_csv(os.path.join(BASE, 'micro_flow', 'crowding', 'cache'), 'northbound.csv')
    if not nb_df.empty:
        for col in nb_df.columns:
            if col != 'trade_date':
                nb_df[col] = pd.to_numeric(nb_df[col], errors='coerce')
        nb_df = nb_df.sort_values('trade_date')

        # 找净买入列
        buy_col = None
        for c in ['buy_amount', 'north_money', 'net_amount']:
            if c in nb_df.columns:
                buy_col = c
                break

        if buy_col:
            recent5 = nb_df[buy_col].tail(5)
            consecutive_out = int((recent5 < 0).sum())
            micro['items'].append(f"北向近5日净流出天数: {consecutive_out}")
            micro['trend'] = [{'date': str(int(r['trade_date']))[:4]+'-'+str(int(r['trade_date']))[4:6]+'-'+str(int(r['trade_date']))[6:8],
                              'value': round(float(r[buy_col]) / 1e4, 2) if pd.notna(r[buy_col]) else None}
                             for _, r in nb_df.tail(30).iterrows()]

            if consecutive_out >= 5:
                micro['score'] += 40
                result['alerts'].append(f'🏃 北向连续{consecutive_out}日净流出')
            elif consecutive_out >= 3:
                micro['score'] += 20

    # 期权PCR
    if opt_data:
        for underlying in opt_data.get('underlyings', []):
            if underlying.get('code') in ('000300', '510300'):
                summary = underlying.get('summary', {})
                pcr = summary.get('pcr_oi')
                if pcr is not None:
                    micro['items'].append(f"300期权PCR(OI): {pcr:.2f}")
                    if pcr > 1.3:
                        micro['score'] += 30
                        result['alerts'].append(f'🏃 300期权PCR {pcr:.2f}，看空力量极重')
                    elif pcr > 1.0:
                        micro['score'] += 15
                break

    micro['score'] = min(micro['score'], 100)
    scores['micro'] = micro['score']
    if micro['score'] >= 60:
        micro['level'] = '🔴'
    elif micro['score'] >= 30:
        micro['level'] = '🟡'
    result['dimensions']['micro'] = micro

    # ═══════ 综合评分 ═══════
    weights = {'liquidity': 0.2, 'valuation': 0.25, 'sentiment': 0.2, 'external': 0.2, 'micro': 0.15}
    total = sum(scores.get(k, 0) * w for k, w in weights.items())
    result['composite_score'] = round(total, 1)

    if total >= 60:
        result['composite_level'] = '高风险 🔴'
    elif total >= 40:
        result['composite_level'] = '中高风险 🟠'
    elif total >= 20:
        result['composite_level'] = '中低风险 🟡'
    else:
        result['composite_level'] = '低风险 🟢'

    if not result['alerts']:
        result['alerts'] = ['当前无极端风险信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n输出: {OUTPUT_JSON}")
    print(f"综合风险: {result['composite_score']:.1f}/100 - {result['composite_level']}")
    for a in result['alerts']:
        print(f"  ⚠️ {a}")


if __name__ == '__main__':
    calc()
