#!/usr/bin/env python3
"""仪表盘概览 - 汇总各模块信号生成 overview.json"""
import os, json, glob
from datetime import datetime

BASE = os.path.expanduser("~/Desktop/gamt-dashboard")
OUTPUT = os.path.join(BASE, "server", "overview.json")


def read_json(path):
    try:
        return json.load(open(path))
    except:
        return None


def get_mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%m-%d %H:%M')
    except:
        return '-'


def main():
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'modules': [],
        'top_cards': [],
        'risk_score': None,
    }

    # ── 红灯预警（综合风险）
    alerts = read_json(f'{BASE}/alerts/alerts.json')
    if alerts:
        result['risk_score'] = {
            'score': alerts.get('composite_score', 0),
            'level': alerts.get('composite_level', ''),
            'alerts': alerts.get('alerts', []),
        }

    # ── 各模块状态
    modules = [
        {
            'name': '📈 风格轧差', 'key': 'style-spread',
            'json': f'{BASE}/size_spread/style_spread_signals.json',
            'signal_key': 'signals',
        },
        {
            'name': '🎯 策略环境适配度', 'key': 'env-fit',
            'json': f'{BASE}/env_fit/env_fit_signals.json',
            'signal_key': 'signals',
        },
        {
            'name': '💰 耐心资本', 'key': 'patient-capital',
            'json': f'{BASE}/micro_flow/patient_capital/patient_capital.json',
            'signal_fn': lambda d: _patient_signal(d),
        },
        {
            'name': '📡 拥挤度监控', 'key': 'crowding',
            'json': f'{BASE}/micro_flow/crowding/crowding.json',
            'signal_fn': lambda d: _crowding_signal(d),
        },
        {
            'name': '🎯 期权情绪', 'key': 'option-sentiment',
            'json': f'{BASE}/micro_flow/option_sentiment/option_sentiment.json',
            'signal_fn': lambda d: _option_signal(d),
        },
        {
            'name': '💧 境内流动性', 'key': 'liquidity',
            'json': f'{BASE}/macro/liquidity/liquidity.json',
            'signal_fn': lambda d: _liquidity_signal(d),
        },
        {
            'name': '🌍 利率汇率', 'key': 'rates',
            'json': f'{BASE}/macro/rates/rates.json',
            'signal_fn': lambda d: _rates_signal(d),
        },
        {
            'name': '📊 经济基本面', 'key': 'fundamentals',
            'json': f'{BASE}/macro/fundamentals/fundamentals.json',
            'signal_fn': lambda d: _fundamentals_signal(d),
        },
        {
            'name': '🏭 产业链景气', 'key': 'chain-prosperity',
            'json': f'{BASE}/meso/chain_prosperity/chain_prosperity.json',
            'signal_fn': lambda d: _chain_signal(d),
        },
        {
            'name': '🚨 红灯预警', 'key': 'alerts',
            'json': f'{BASE}/alerts/alerts.json',
            'signal_fn': lambda d: [f"综合{d.get('composite_score',0):.0f}分 {d.get('composite_level','')}"],
        },
    ]

    for m in modules:
        jp = m['json']
        d = read_json(jp)
        updated = get_mtime(jp) if os.path.exists(jp) else '-'
        signals = []
        status = 'off'

        if d:
            status = 'on'
            if 'signal_key' in m:
                signals = d.get(m['signal_key'], [])[:3]
            elif 'signal_fn' in m:
                try:
                    signals = m['signal_fn'](d) or []
                except:
                    signals = []

        result['modules'].append({
            'name': m['name'],
            'key': m['key'],
            'status': status,
            'updated': updated,
            'signals': signals[:3],
        })

    # ── 顶部卡片
    # 市场风格
    ss = read_json(f'{BASE}/size_spread/style_spread_signals.json')
    style_sig = (ss.get('signals', [''])[0] if ss else '数据待更新')

    # 宏观
    fund = read_json(f'{BASE}/macro/fundamentals/fundamentals.json')
    macro_sig = ''
    if fund:
        clock = fund.get('merrill_clock', {})
        macro_sig = f"{clock.get('phase', '?')} PMI={clock.get('pmi', '?')}"

    # 综合风险
    risk_text = '数据待更新'
    if alerts:
        s = alerts.get('composite_score', 0)
        risk_text = f"{s:.0f}/100 {alerts.get('composite_level', '')}"

    # 转债环境
    cb = read_json(f'{BASE}/env_fit/cb_env/cb_env.json')
    cb_text = f"转债{cb['score']:.0f}分" if cb and cb.get('score') else '-'

    result['top_cards'] = [
        {'label': '风格倾向', 'value': style_sig, 'color': 'blue'},
        {'label': '宏观周期', 'value': macro_sig, 'color': 'green'},
        {'label': '综合风险', 'value': risk_text, 'color': 'amber' if alerts and alerts.get('composite_score', 0) < 40 else 'red'},
        {'label': '转债环境', 'value': cb_text, 'color': 'green' if cb and cb.get('score', 0) >= 60 else 'slate'},
    ]

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT}")
    print(f"模块: {sum(1 for m in result['modules'] if m['status']=='on')}/{len(result['modules'])} 在线")


def _patient_signal(d):
    indices = d.get('indices', {})
    sigs = []
    for name, info in list(indices.items())[:3]:
        lt = info.get('latest', {})
        pnl = lt.get('pnl')
        if pnl is not None:
            emoji = '🟢' if pnl > 0 else '🔴'
            sigs.append(f'{name} 耐心资本浮盈{pnl:+.1f}% {emoji}')
    return sigs


def _crowding_signal(d):
    sig = d.get('signal', d.get('signals', {}))
    if isinstance(sig, dict):
        return [f"{k}: {v}" for k, v in list(sig.items())[:2]]
    if isinstance(sig, list):
        return sig[:2]
    return []


def _option_signal(d):
    sigs = []
    for underlying in d.get('underlyings', d.get('data', {}).keys()) if isinstance(d, dict) else []:
        info = d.get('data', d).get(underlying, {}) if isinstance(d.get('data', d), dict) else {}
        iv_pct = info.get('iv_percentile') or info.get('atm_iv_pct')
        if iv_pct is not None:
            sigs.append(f'{underlying} IV分位 {iv_pct:.0f}%')
    return sigs[:2] if sigs else ['期权数据已更新']


def _liquidity_signal(d):
    sigs = []
    dr = d.get('dr007', {})
    if isinstance(dr, dict):
        latest = dr.get('latest')
        if latest:
            sigs.append(f"DR007 {latest}%")
    shibor = d.get('shibor_on', {})
    if isinstance(shibor, dict):
        latest = shibor.get('latest')
        if latest:
            sigs.append(f"Shibor O/N {latest}%")
    return sigs if sigs else ['流动性数据已更新']


def _rates_signal(d):
    spread = d.get('spread', {})
    if isinstance(spread, dict):
        latest = spread.get('latest')
        if latest is not None:
            return [f'中美利差 {latest}%']
    return ['利率数据已更新']


def _fundamentals_signal(d):
    clock = d.get('merrill_clock', {})
    if clock:
        return [f"{clock.get('phase','?')} PMI={clock.get('pmi','?')} CPI={clock.get('cpi','?')}"]
    return ['基本面数据已更新']


def _chain_signal(d):
    chains = d.get('chains', d.get('summary', {}))
    if isinstance(chains, dict):
        return [f"{k}: {v.get('signal','')}" for k, v in list(chains.items())[:3] if isinstance(v, dict)]
    return ['产业链数据已更新']


if __name__ == '__main__':
    main()
