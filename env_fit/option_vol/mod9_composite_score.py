#!/usr/bin/env python3
"""
模块9：综合评分

把 mod1(RV + PCA) 和 mod2(IV-RV spread) 合并成更接近交易决策的总分。
"""

import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
MOD1_JSON = os.path.join(BASE, 'mod1_rv_regime.json')
MOD2_JSON = os.path.join(BASE, 'mod2_iv_spread.json')
MOD3_JSON = os.path.join(BASE, 'mod3_skew_term.json')
OUT_JSON = os.path.join(BASE, 'mod9_composite_score.json')


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def liquidity_score(row):
    vol = (row.get('call_vol') or 0) + (row.get('put_vol') or 0)
    oi = (row.get('call_oi') or 0) + (row.get('put_oi') or 0)

    if vol >= 5000:
        vol_score = 95
    elif vol >= 1000:
        vol_score = 80
    elif vol >= 200:
        vol_score = 60
    elif vol >= 50:
        vol_score = 40
    else:
        vol_score = 20

    if oi >= 5000:
        oi_score = 95
    elif oi >= 1000:
        oi_score = 80
    elif oi >= 300:
        oi_score = 60
    elif oi >= 100:
        oi_score = 40
    else:
        oi_score = 20

    return round(vol_score * 0.6 + oi_score * 0.4)


def expiry_score(days):
    if days is None:
        return 50
    if 15 <= days <= 45:
        return 90
    if 8 <= days < 15 or 46 <= days <= 60:
        return 70
    if 5 <= days < 8:
        return 45
    return 30


def regime_from_rows(rows):
    sellable = [r for r in rows if r['composite_score'] >= 65]
    avg_score = round(sum(r['composite_score'] for r in rows) / len(rows), 1) if rows else 0
    breadth = len(set(r['sector'] for r in sellable))

    if len(sellable) >= 4 and avg_score >= 70 and breadth >= 2:
        label = 'STRONG_SELL_VOL'
        desc = '赔率与环境共振，系统性双卖窗口'
    elif len(sellable) >= 2 and avg_score >= 60:
        label = 'SELECTIVE_SELL'
        desc = '部分品种赔率合适，精选双卖'
    elif len(sellable) >= 1 or avg_score >= 50:
        label = 'NEUTRAL'
        desc = '局部可做，谨慎参与'
    else:
        label = 'AVOID_SELLING'
        desc = '赔率不足或真实波动偏强，不宜卖波'

    return {
        'label': label,
        'description': desc,
        'avg_composite_score': avg_score,
        'n_sellable': len(sellable),
        'sector_breadth': breadth,
        'top3': [{'symbol': r['symbol'], 'cn_name': r.get('cn_name', r['symbol']), 'score': r['composite_score']} for r in rows[:3]],
    }


def signal_label(score):
    if score >= 80:
        return '🟢', '强烈双卖窗口'
    if score >= 65:
        return '🟡', '可考虑双卖'
    if score >= 50:
        return '⚪', '观望'
    return '🔴', '不宜双卖'


def main():
    mod1 = load_json(MOD1_JSON)
    mod2 = load_json(MOD2_JSON)
    mod3 = load_json(MOD3_JSON)

    rv_map = {x['symbol']: x for x in mod1.get('symbols', [])}
    iv_map = {x['symbol']: x for x in mod2.get('symbols', []) if 'error' not in x}
    skew_map = {x['symbol']: x for x in mod3.get('symbols', []) if 'error' not in x}

    rows = []
    for symbol, rv in rv_map.items():
        iv = iv_map.get(symbol)
        skew = skew_map.get(symbol)
        rv_score = rv.get('sell_score', 0)
        iv_score = iv.get('odds_score_iv') if iv else None
        liq_score = liquidity_score(iv) if iv else 35
        exp_score = expiry_score(iv.get('days_to_expiry')) if iv else 50
        skew_score = skew.get('skew_score') if skew else None
        term_score = skew.get('term_score') if skew else None

        # 完整版：RV + IV + skew + term + liquidity + expiry
        if iv_score is not None and skew_score is not None and term_score is not None:
            composite = round(
                rv_score * 0.30 + iv_score * 0.28 +
                skew_score * 0.18 + term_score * 0.12 +
                liq_score * 0.07 + exp_score * 0.05
            )
        elif iv_score is not None:
            composite = round(rv_score * 0.45 + iv_score * 0.35 + liq_score * 0.12 + exp_score * 0.08)
        else:
            composite = round(rv_score * 0.75 + liq_score * 0.15 + exp_score * 0.10)

        signal, label = signal_label(composite)
        reason_parts = []
        if iv_score is not None and (iv.get('iv_rv_spread') is not None):
            spread = iv.get('iv_rv_spread')
            if spread >= 0.08:
                reason_parts.append('IV显著高于RV，保险费偏贵')
            elif spread >= 0.03:
                reason_parts.append('IV高于RV，赔率尚可')
            elif spread < 0:
                reason_parts.append('IV低于RV，保险费不算贵')
        if skew_score is not None:
            if skew_score >= 60:
                reason_parts.append('尾部保险费有一定溢价')
            elif skew_score <= 40:
                reason_parts.append('尾部保险费不够肥')
        if term_score is not None:
            if term_score >= 60:
                reason_parts.append('近月比远月更贵，偏短期恐慌')
            elif term_score <= 40:
                reason_parts.append('期限结构偏平/偏弱，近月溢价一般')
        if liq_score >= 80:
            reason_parts.append('流动性较好')
        elif liq_score <= 40:
            reason_parts.append('流动性一般，执行要谨慎')
        if exp_score >= 90:
            reason_parts.append('到期结构合适')
        elif exp_score <= 45:
            reason_parts.append('离到期偏近，Gamma风险更高')
        reason_text = '；'.join(reason_parts) if reason_parts else '当前主要由RV环境分驱动，期权侧信息仍需继续补强'

        rows.append({
            'symbol': symbol,
            'cn_name': rv.get('cn_name', symbol),
            'sector': rv.get('sector', '其他'),
            'composite_score': composite,
            'signal': signal,
            'label': label,
            'rv_score': rv_score,
            'iv_score': iv_score,
            'liquidity_score': liq_score,
            'expiry_score': exp_score,
            'rv_20d': rv.get('rv_20d'),
            'rv_pctile_120d': rv.get('rv_pctile_120d'),
            'pca_env': rv.get('pca_env'),
            'iv_rv_spread': iv.get('iv_rv_spread') if iv else None,
            'atm_iv': iv.get('atm_iv') if iv else None,
            'days_to_expiry': iv.get('days_to_expiry') if iv else None,
            'call_vol': iv.get('call_vol') if iv else None,
            'put_vol': iv.get('put_vol') if iv else None,
            'call_oi': iv.get('call_oi') if iv else None,
            'put_oi': iv.get('put_oi') if iv else None,
            'put_skew': skew.get('put_skew') if skew else None,
            'call_skew': skew.get('call_skew') if skew else None,
            'term_slope': skew.get('term_slope') if skew else None,
            'skew_score': skew_score,
            'term_score': term_score,
            'reason_text': reason_text,
        })

    rows.sort(key=lambda x: x['composite_score'], reverse=True)
    regime = regime_from_rows(rows)

    out = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'module': 'option_vol.mod9_composite_score',
            'formula': '0.30*rv + 0.28*iv + 0.18*skew + 0.12*term + 0.07*liq + 0.05*exp (full); fallback if missing layers',
        },
        'regime': regime,
        'symbols': rows,
    }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f'输出: {OUT_JSON}')
    print(f"Regime: {regime['label']} avg={regime['avg_composite_score']} n={regime['n_sellable']}")
    for row in rows[:5]:
        print(f"  {row['symbol']:>4s} {row['signal']} score={row['composite_score']} iv_spread={row.get('iv_rv_spread')}")


if __name__ == '__main__':
    main()
