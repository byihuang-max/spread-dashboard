#!/usr/bin/env python3
"""仪表盘概览 - 汇总各模块信号生成 overview.json（分组版）"""
import os, json
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(BASE, "server", "overview.json")


def read_json(path):
    try:
        return json.load(open(path))
    except:
        return None


def get_mtime(path):
    """返回文件修改时间字符串"""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%m-%d %H:%M')
    except:
        return '-'


def get_mtime_ts(path):
    """返回文件修改时间戳（用于组内取最新）"""
    try:
        return os.path.getmtime(path)
    except:
        return 0


# ── 分组信号提取函数 ──

def _style_spread_signal():
    """风格轧差：周期热点 + 拥挤行业"""
    d = read_json(f'{BASE}/size_spread/style_spread_signals.json')
    if not d:
        return [], '-', False
    sigs = d.get('signals', [])[:2]
    updated = get_mtime(f'{BASE}/size_spread/style_spread_signals.json')
    return sigs, updated, True


def _env_fit_signal():
    """策略环境适配度：各策略评分"""
    d = read_json(f'{BASE}/env_fit/env_fit_signals.json')
    if not d:
        return [], '-', False
    sigs = d.get('signals', [])[:3]
    updated = d.get('update_time', get_mtime(f'{BASE}/env_fit/env_fit_signals.json'))
    return sigs, updated, True


def _fund_flow_signal():
    """资金流与微观结构：耐心资本 + 拥挤度 + 期权IV"""
    sigs = []
    files = []
    any_on = False

    # 耐心资本
    pc = read_json(f'{BASE}/micro_flow/patient_capital/patient_capital.json')
    if pc:
        any_on = True
        files.append(f'{BASE}/micro_flow/patient_capital/patient_capital.json')
        indices = pc.get('indices', {})
        # 取前2个指数的浮盈
        for name, info in list(indices.items())[:2]:
            lt = info.get('latest', {})
            pnl = lt.get('pnl')
            if pnl is not None:
                emoji = '🟢' if pnl > 0 else '🔴'
                sigs.append(f'{name}浮盈{pnl:+.1f}%{emoji}')

    # 拥挤度
    cr = read_json(f'{BASE}/micro_flow/crowding/crowding.json')
    if cr:
        any_on = True
        files.append(f'{BASE}/micro_flow/crowding/crowding.json')
        cs = cr.get('crowding_signal', {})
        consensus = cs.get('consensus', '')
        if consensus:
            sigs.append(f'拥挤度:{consensus}')
        else:
            # 从 three_flows 提取
            tf = cr.get('three_flows', {})
            tf_con = tf.get('consensus', '')
            if tf_con:
                sigs.append(f'三路资金:{tf_con}')

    # 期权情绪
    op = read_json(f'{BASE}/micro_flow/option_sentiment/option_sentiment.json')
    if op:
        any_on = True
        files.append(f'{BASE}/micro_flow/option_sentiment/option_sentiment.json')
        underlyings = op.get('underlyings', [])
        for u in underlyings[:2]:
            name = u.get('name', '')
            summary = u.get('summary', {})
            iv_pct = summary.get('iv_percentile')
            atm_iv = summary.get('atm_iv')
            if iv_pct is not None:
                sigs.append(f'{name}IV分位{iv_pct:.0f}%')
            elif atm_iv is not None:
                sigs.append(f'{name}IV{atm_iv:.1f}%')
        # fallback: global_signals
        if not any(s for s in sigs if 'IV' in s):
            gsigs = op.get('global_signals', [])
            for g in gsigs[:1]:
                sigs.append(g)

    # 最新时间
    updated = '-'
    if files:
        latest_ts = max(get_mtime_ts(f) for f in files)
        if latest_ts > 0:
            updated = datetime.fromtimestamp(latest_ts).strftime('%m-%d %H:%M')

    return sigs[:3], updated, any_on


def _macro_signal():
    """宏观与流动性：美林时钟 + DR007 + 中美利差/汇率"""
    sigs = []
    files = []
    any_on = False

    # 基本面 → 美林时钟
    fund = read_json(f'{BASE}/macro/fundamentals/fundamentals.json')
    if fund:
        any_on = True
        files.append(f'{BASE}/macro/fundamentals/fundamentals.json')
        clock = fund.get('merrill_clock', {})
        if clock:
            phase = clock.get('phase', '')
            pmi = clock.get('pmi', '')
            if phase:
                sigs.append(f"{clock.get('emoji','')} {phase} PMI={pmi}")

    # 流动性 → DR007 / Shibor
    liq = read_json(f'{BASE}/macro/liquidity/liquidity.json')
    if liq:
        any_on = True
        files.append(f'{BASE}/macro/liquidity/liquidity.json')
        # DR007: 数组取最新
        dr_list = liq.get('dr007', [])
        if isinstance(dr_list, list) and dr_list:
            latest_dr = dr_list[-1]
            if isinstance(latest_dr, dict):
                v = latest_dr.get('dr007')
                if v is not None:
                    sigs.append(f'DR007 {v}%')
        elif isinstance(dr_list, dict):
            v = dr_list.get('latest')
            if v is not None:
                sigs.append(f'DR007 {v}%')

    # 利率汇率 → 汇率
    rates = read_json(f'{BASE}/macro/rates/rates.json')
    if rates:
        any_on = True
        files.append(f'{BASE}/macro/rates/rates.json')
        fx = rates.get('fx', {})
        usdcny = fx.get('USDCNY.FX', {})
        if isinstance(usdcny, list) and usdcny:
            latest_fx = usdcny[-1]
            if isinstance(latest_fx, dict):
                v = latest_fx.get('value') or latest_fx.get('close')
                if v:
                    sigs.append(f'USDCNY {v}')
        elif isinstance(usdcny, dict):
            v = usdcny.get('latest') or usdcny.get('value')
            if v:
                sigs.append(f'USDCNY {v}')
        # fallback: fx_spread
        spread = rates.get('fx_spread')
        if spread and not any('USDCNY' in s for s in sigs):
            sigs.append(f'离岸价差 {spread}')

    # 最新时间
    updated = '-'
    if files:
        latest_ts = max(get_mtime_ts(f) for f in files)
        if latest_ts > 0:
            updated = datetime.fromtimestamp(latest_ts).strftime('%m-%d %H:%M')

    return sigs[:3], updated, any_on


def _meso_signal():
    """中观景气：产业链景气摘要"""
    d = read_json(f'{BASE}/meso/chain_prosperity/chain_prosperity.json')
    if not d:
        return [], '-', False
    sigs = d.get('signals', [])
    # 过滤空信号
    sigs = [s for s in sigs if s and not s.endswith(': ')]
    if not sigs:
        chains = d.get('chains', d.get('summary', {}))
        if isinstance(chains, dict):
            for k, v in list(chains.items())[:3]:
                if isinstance(v, dict):
                    sig = v.get('signal', '')
                    if sig:
                        sigs.append(f'{k}: {sig}')
    updated = get_mtime(f'{BASE}/meso/chain_prosperity/chain_prosperity.json')
    return sigs[:3], updated, True


def _alerts_signal():
    """红灯预警：综合评分 + 级别"""
    d = read_json(f'{BASE}/alerts/alerts.json')
    if not d:
        return [], '-', False
    score = d.get('composite_score', 0)
    level = d.get('composite_level', '')
    alerts_list = d.get('alerts', [])
    sigs = [f"综合{score:.0f}分 {level}"]
    if alerts_list:
        sigs.append(alerts_list[0])
    updated = get_mtime(f'{BASE}/alerts/alerts.json')
    return sigs[:2], updated, True


def main():
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'modules': [],       # 保留兼容（平铺模块列表）
        'module_groups': [],  # 新：分组结构
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

    # ── 分组定义 ──
    groups = [
        {
            'name': '📈 风格轧差',
            'subs': ['经济敏感轧差', '拥挤-反身性', '风格轧差净值', '双创等权'],
            'new_subs': [],
            'signal_fn': _style_spread_signal,
        },
        {
            'name': '🎯 策略环境适配度',
            'subs': ['宽基量化', '强势股', 'CTA', '转债', '套利'],
            'new_subs': [],
            'signal_fn': _env_fit_signal,
        },
        {
            'name': '💰 资金流与微观结构',
            'subs': ['耐心资本持筹', '拥挤度监控', '期权异常值监控'],
            'new_subs': [],
            'signal_fn': _fund_flow_signal,
        },
        {
            'name': '🌍 宏观与流动性',
            'subs': ['境内流动性', '全球利率与汇率', '经济基本面', '反脆弱看板', 'HALO交易'],
            'new_subs': ['反脆弱看板', 'HALO交易'],
            'signal_fn': _macro_signal,
        },
        {
            'name': '🏭 中观景气',
            'subs': ['产业链景气'],
            'new_subs': [],
            'signal_fn': _meso_signal,
        },
        {
            'name': '🚨 红灯预警',
            'subs': ['A股风险', '美股风险'],
            'new_subs': [],
            'signal_fn': _alerts_signal,
        },
    ]

    for g in groups:
        try:
            signals, updated, is_on = g['signal_fn']()
        except Exception as e:
            signals, updated, is_on = [f'信号提取失败: {e}'], '-', False

        result['module_groups'].append({
            'name': g['name'],
            'subs': g['subs'],
            'new_subs': g['new_subs'],
            'status': 'on' if is_on else 'off',
            'updated': updated,
            'signals': signals,
        })

    # ── 兼容：平铺 modules（旧格式）──
    flat_modules = [
        ('📈 风格轧差', 'style-spread', f'{BASE}/size_spread/style_spread_signals.json', 'signals'),
        ('🎯 策略环境适配度', 'env-fit', f'{BASE}/env_fit/env_fit_signals.json', 'signals'),
        ('💰 耐心资本', 'patient-capital', f'{BASE}/micro_flow/patient_capital/patient_capital.json', None),
        ('📡 拥挤度监控', 'crowding', f'{BASE}/micro_flow/crowding/crowding.json', None),
        ('🎯 期权情绪', 'option-sentiment', f'{BASE}/micro_flow/option_sentiment/option_sentiment.json', None),
        ('💧 境内流动性', 'liquidity', f'{BASE}/macro/liquidity/liquidity.json', None),
        ('🌍 利率汇率', 'rates', f'{BASE}/macro/rates/rates.json', None),
        ('📊 经济基本面', 'fundamentals', f'{BASE}/macro/fundamentals/fundamentals.json', None),
        ('🏭 产业链景气', 'chain-prosperity', f'{BASE}/meso/chain_prosperity/chain_prosperity.json', None),
        ('🚨 红灯预警', 'alerts', f'{BASE}/alerts/alerts.json', None),
    ]
    for name, key, jp, sig_key in flat_modules:
        d = read_json(jp)
        updated = get_mtime(jp) if os.path.exists(jp) else '-'
        status = 'on' if d else 'off'
        signals = []
        if d and sig_key:
            signals = d.get(sig_key, [])[:3]
        result['modules'].append({
            'name': name, 'key': key, 'status': status,
            'updated': updated, 'signals': signals,
        })

    # ── 顶部卡片 ──
    ss = read_json(f'{BASE}/size_spread/style_spread_signals.json')
    style_sig = (ss.get('signals', [''])[0] if ss else '数据待更新')

    fund = read_json(f'{BASE}/macro/fundamentals/fundamentals.json')
    macro_sig = ''
    if fund:
        clock = fund.get('merrill_clock', {})
        macro_sig = f"{clock.get('phase', '?')} PMI={clock.get('pmi', '?')}"

    risk_text = '数据待更新'
    if alerts:
        s = alerts.get('composite_score', 0)
        risk_text = f"{s:.0f}/100 {alerts.get('composite_level', '')}"

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
    print(f"分组: {len(result['module_groups'])} 组")
    print(f"模块: {sum(1 for m in result['modules'] if m['status']=='on')}/{len(result['modules'])} 在线")


if __name__ == '__main__':
    main()
