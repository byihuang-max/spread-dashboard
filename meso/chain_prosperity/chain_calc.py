#!/usr/bin/env python3
"""
中观景气度 - 计算 + 生成JSON (v2: 4个Tab + 时序数据)
"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'chain_prosperity.json')

ETF_NAMES = {
    '512480.SH': '芯片ETF', '159732.SZ': '消费电子ETF', '588000.SH': '科创50ETF',
    '159992.SZ': '创新药ETF', '512010.SH': '医药ETF',
    '516950.SH': '基建ETF', '512200.SH': '房地产ETF',
    '512690.SH': '白酒ETF', '159928.SZ': '消费ETF',
}

FUTURES_NAMES = {
    'CU.SHF': '铜', 'AL.SHF': '铝', 'I.DCE': '铁矿石', 'ZC.ZCE': '煤炭',
    'RB.SHF': '螺纹钢', 'FG.ZCE': '玻璃', 'SA.ZCE': '纯碱',
    'LH.DCE': '生猪', 'A.DCE': '大豆', 'P.DCE': '棕榈油',
}


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def pct_n(series, n):
    if len(series) < n + 1:
        return None
    return round((series.iloc[-1] / series.iloc[-(n+1)] - 1) * 100, 2)


def normalize_series(dates, values):
    """归一化为首日=100的序列"""
    if not values or values[0] is None or values[0] == 0:
        return []
    base = values[0]
    return [{'date': d, 'value': round(v / base * 100, 2) if v is not None else None}
            for d, v in zip(dates, values)]


def get_etf_ts(etf_price, code):
    """获取ETF时序 (dates, closes)"""
    df = etf_price[etf_price['ts_code'] == code].copy()
    if df.empty:
        return [], []
    df['trade_date'] = df['trade_date'].astype(int).astype(str)
    df = df.sort_values('trade_date')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    dates = [d[4:6]+'-'+d[6:8] for d in df['trade_date']]
    return dates, df['close'].tolist()


def get_etf_share_ts(etf_share, code):
    """获取ETF份额时序 + 日度变化"""
    df = etf_share[etf_share['ts_code'] == code].copy()
    if df.empty:
        return [], [], []
    df['trade_date'] = df['trade_date'].astype(int).astype(str)
    df = df.sort_values('trade_date')
    df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
    dates = [d[4:6]+'-'+d[6:8] for d in df['trade_date']]
    shares = df['fd_share'].tolist()
    # 日度变化(万份)
    changes = [None] + [round(shares[i] - shares[i-1], 0) if shares[i] is not None and shares[i-1] is not None else None
                        for i in range(1, len(shares))]
    return dates, shares, changes


def get_fut_ts(futures, generic_code):
    """获取期货时序"""
    df = futures[futures['generic'] == generic_code].copy()
    if df.empty:
        return [], []
    df['trade_date'] = df['trade_date'].astype(int).astype(str)
    df = df.sort_values('trade_date')
    df['settle'] = pd.to_numeric(df['settle'], errors='coerce')
    dates = [d[4:6]+'-'+d[6:8] for d in df['trade_date']]
    return dates, df['settle'].tolist()


def get_sw_ts(sw_indices, ts_code):
    """获取申万/南华指数时序"""
    df = sw_indices[sw_indices['ts_code'] == ts_code].copy()
    if df.empty:
        return [], []
    df['trade_date'] = df['trade_date'].astype(int).astype(str)
    df = df.sort_values('trade_date')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    dates = [d[4:6]+'-'+d[6:8] for d in df['trade_date']]
    return dates, df['close'].tolist()


def trend_arrow(val):
    if val is None: return '—'
    if val > 2: return '↗↗'
    if val > 0.5: return '↗'
    if val > -0.5: return '→'
    if val > -2: return '↘'
    return '↘↘'


def chain_signal(dirs):
    """根据上中下游5日方向判断传导"""
    up, mid, down = dirs.get('up'), dirs.get('mid'), dirs.get('down')
    def pos(d): return d is not None and d > 0.5
    def neg(d): return d is not None and d < -0.5

    if pos(up) and pos(mid) and pos(down):
        return '全链景气上行', '🟢'
    if neg(up) and neg(mid) and neg(down):
        return '全链景气下行', '🔴'
    if pos(up) and neg(down):
        return '上游涨价挤压下游', '⚠️'
    if neg(up) and pos(down):
        return '成本改善利好下游', '🟢'
    if pos(up) and pos(mid) and not pos(down):
        return '上中游景气,下游滞后', '🟡'
    if not pos(up) and pos(down):
        return '下游独立走强', '🔵'
    return '分化震荡', '🟡'


def make_tier_summary(name, chg_5d, chg_20d=None, share_chg_5d=None):
    return {
        'name': name,
        'chg_5d': chg_5d,
        'chg_20d': chg_20d,
        'arrow': trend_arrow(chg_5d),
        'share_chg_5d': share_chg_5d,
    }


def calc():
    etf_price = load_csv('etf_price.csv')
    etf_share = load_csv('etf_share.csv')
    futures = load_csv('futures.csv')
    sw_indices = load_csv('sw_indices.csv')
    ifind = load_csv('ifind_global.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'signals': [],
        'chains': {},
    }

    # ═══════ 科技芯片 ═══════
    tech = {'name': '🔬 科技芯片', 'trend_lines': [], 'share_lines': [], 'tiers': [], 'notes': []}

    # 走势线
    d1, v1 = get_etf_ts(etf_price, '512480.SH')
    d2, v2 = get_etf_ts(etf_price, '159732.SZ')
    d3, v3 = get_etf_ts(etf_price, '588000.SH')

    # 用最长的dates做基准
    base_dates = d1 if len(d1) >= len(d2) else d2

    tech['trend_lines'] = [
        {'name': 'SOXX费城半导体', 'color': '#2563eb', 'data': None},  # iFind只有实时没有历史
        {'name': '芯片ETF', 'color': '#7c3aed', 'data': normalize_series(d1, v1)},
        {'name': '消费电子ETF', 'color': '#f59e0b', 'data': normalize_series(d2, v2)},
        {'name': '科创50ETF', 'color': '#10b981', 'data': normalize_series(d3, v3)},
    ]

    # 份额
    for code, name in [('512480.SH','芯片ETF'), ('159732.SZ','消费电子ETF'), ('588000.SH','科创50ETF')]:
        sd, ss, sc = get_etf_share_ts(etf_share, code)
        tech['share_lines'].append({'name': name, 'dates': sd, 'changes': sc})

    # 摘要
    chg_chip = pct_n(pd.Series(v1), 5) if v1 else None
    chg_ce = pct_n(pd.Series(v2), 5) if v2 else None
    chg_kc = pct_n(pd.Series(v3), 5) if v3 else None

    soxx_pct = None
    if not ifind.empty:
        row = ifind[ifind['code'] == 'SOXX.O']
        if not row.empty and pd.notna(row.iloc[0].get('pct_change')):
            soxx_pct = round(float(row.iloc[0]['pct_change']), 2)

    tech['tiers'] = [
        make_tier_summary('SOXX费城半导体', soxx_pct),
        make_tier_summary('芯片ETF', chg_chip, pct_n(pd.Series(v1), 20) if v1 else None),
        make_tier_summary('消费电子ETF', chg_ce),
        make_tier_summary('科创50ETF', chg_kc),
    ]

    down_avg = np.mean([x for x in [chg_ce, chg_kc] if x is not None]) if any(x is not None for x in [chg_ce, chg_kc]) else None
    tech['signal_text'], tech['emoji'] = chain_signal({'up': soxx_pct, 'mid': chg_chip, 'down': down_avg})
    result['chains']['tech'] = tech

    # ═══════ 创新药 ═══════
    pharma = {'name': '💊 创新药', 'trend_lines': [], 'share_lines': [], 'tiers': [], 'notes': []}

    d_sw, v_sw = get_sw_ts(sw_indices, '801150.SI')
    d_inno, v_inno = get_etf_ts(etf_price, '159992.SZ')
    d_med, v_med = get_etf_ts(etf_price, '512010.SH')

    pharma['trend_lines'] = [
        {'name': '医药生物(申万)', 'color': '#2563eb', 'data': normalize_series(d_sw, v_sw)},
        {'name': '创新药ETF', 'color': '#7c3aed', 'data': normalize_series(d_inno, v_inno)},
        {'name': '医药ETF', 'color': '#f59e0b', 'data': normalize_series(d_med, v_med)},
    ]

    for code, name in [('159992.SZ','创新药ETF'), ('512010.SH','医药ETF')]:
        sd, ss, sc = get_etf_share_ts(etf_share, code)
        pharma['share_lines'].append({'name': name, 'dates': sd, 'changes': sc})

    chg_sw = pct_n(pd.Series(v_sw), 5) if v_sw else None
    chg_inno = pct_n(pd.Series(v_inno), 5) if v_inno else None
    chg_med = pct_n(pd.Series(v_med), 5) if v_med else None

    pharma['tiers'] = [
        make_tier_summary('医药生物(申万)', chg_sw, pct_n(pd.Series(v_sw), 20) if v_sw else None),
        make_tier_summary('创新药ETF', chg_inno, pct_n(pd.Series(v_inno), 20) if v_inno else None),
        make_tier_summary('医药ETF', chg_med, pct_n(pd.Series(v_med), 20) if v_med else None),
    ]

    pharma['signal_text'], pharma['emoji'] = chain_signal({'up': chg_sw, 'mid': chg_inno, 'down': chg_med})
    result['chains']['pharma'] = pharma

    # ═══════ 周期 ═══════
    cycle = {'name': '⛏️ 周期', 'trend_lines_up': [], 'trend_lines_mid': [], 'trend_lines_down': [], 'share_lines': [], 'tiers': [], 'notes': []}

    # 上游
    up_chgs = []
    for code, color in [('CU.SHF','#dc2626'), ('AL.SHF','#f59e0b'), ('I.DCE','#2563eb'), ('ZC.ZCE','#6b7280')]:
        d, v = get_fut_ts(futures, code)
        cycle['trend_lines_up'].append({'name': FUTURES_NAMES[code], 'color': color, 'data': normalize_series(d, v)})
        c5 = pct_n(pd.Series(v), 5) if v else None
        cycle['tiers'].append(make_tier_summary(FUTURES_NAMES[code], c5, pct_n(pd.Series(v), 20) if v else None))
        if c5 is not None: up_chgs.append(c5)

    # 中游
    mid_chgs = []
    for code, color in [('RB.SHF','#dc2626'), ('FG.ZCE','#f59e0b'), ('SA.ZCE','#7c3aed')]:
        d, v = get_fut_ts(futures, code)
        cycle['trend_lines_mid'].append({'name': FUTURES_NAMES[code], 'color': color, 'data': normalize_series(d, v)})
        c5 = pct_n(pd.Series(v), 5) if v else None
        cycle['tiers'].append(make_tier_summary(FUTURES_NAMES[code], c5, pct_n(pd.Series(v), 20) if v else None))
        if c5 is not None: mid_chgs.append(c5)

    # 南华工业品
    d_nh, v_nh = get_sw_ts(sw_indices, 'NHCI.NH')
    cycle['trend_lines_mid'].append({'name': '南华工业品', 'color': '#10b981', 'data': normalize_series(d_nh, v_nh)})

    # 下游
    d_jj, v_jj = get_etf_ts(etf_price, '516950.SH')
    d_dc, v_dc = get_etf_ts(etf_price, '512200.SH')
    cycle['trend_lines_down'] = [
        {'name': '基建ETF', 'color': '#2563eb', 'data': normalize_series(d_jj, v_jj)},
        {'name': '房地产ETF', 'color': '#f59e0b', 'data': normalize_series(d_dc, v_dc)},
    ]

    chg_jj = pct_n(pd.Series(v_jj), 5) if v_jj else None
    chg_dc = pct_n(pd.Series(v_dc), 5) if v_dc else None
    cycle['tiers'].append(make_tier_summary('基建ETF', chg_jj))
    cycle['tiers'].append(make_tier_summary('房地产ETF', chg_dc))

    for code, name in [('516950.SH','基建ETF'), ('512200.SH','房地产ETF')]:
        sd, ss, sc = get_etf_share_ts(etf_share, code)
        cycle['share_lines'].append({'name': name, 'dates': sd, 'changes': sc})

    up_avg = np.mean(up_chgs) if up_chgs else None
    mid_avg = np.mean(mid_chgs) if mid_chgs else None
    down_avg = np.mean([x for x in [chg_jj, chg_dc] if x is not None]) if any(x is not None for x in [chg_jj, chg_dc]) else None
    cycle['signal_text'], cycle['emoji'] = chain_signal({'up': up_avg, 'mid': mid_avg, 'down': down_avg})
    result['chains']['cycle'] = cycle

    # ═══════ 消费 ═══════
    consumer = {'name': '🛒 消费', 'trend_lines_up': [], 'trend_lines_mid': [], 'share_lines': [], 'tiers': [], 'notes': []}

    # 上游
    con_up_chgs = []
    for code, color in [('LH.DCE','#dc2626'), ('A.DCE','#f59e0b'), ('P.DCE','#10b981')]:
        d, v = get_fut_ts(futures, code)
        consumer['trend_lines_up'].append({'name': FUTURES_NAMES[code], 'color': color, 'data': normalize_series(d, v)})
        c5 = pct_n(pd.Series(v), 5) if v else None
        consumer['tiers'].append(make_tier_summary(FUTURES_NAMES[code], c5, pct_n(pd.Series(v), 20) if v else None))
        if c5 is not None: con_up_chgs.append(c5)

    # 中下游
    d_bj, v_bj = get_etf_ts(etf_price, '512690.SH')
    d_fb, v_fb = get_sw_ts(sw_indices, '801120.SI')
    d_xf, v_xf = get_etf_ts(etf_price, '159928.SZ')

    consumer['trend_lines_mid'] = [
        {'name': '白酒ETF', 'color': '#7c3aed', 'data': normalize_series(d_bj, v_bj)},
        {'name': '食品饮料(申万)', 'color': '#2563eb', 'data': normalize_series(d_fb, v_fb)},
        {'name': '消费ETF', 'color': '#f59e0b', 'data': normalize_series(d_xf, v_xf)},
    ]

    chg_bj = pct_n(pd.Series(v_bj), 5) if v_bj else None
    chg_fb = pct_n(pd.Series(v_fb), 5) if v_fb else None
    chg_xf = pct_n(pd.Series(v_xf), 5) if v_xf else None
    consumer['tiers'].append(make_tier_summary('白酒ETF', chg_bj, pct_n(pd.Series(v_bj), 20) if v_bj else None))
    consumer['tiers'].append(make_tier_summary('食品饮料(申万)', chg_fb))
    consumer['tiers'].append(make_tier_summary('消费ETF', chg_xf))

    for code, name in [('512690.SH','白酒ETF'), ('159928.SZ','消费ETF')]:
        sd, ss, sc = get_etf_share_ts(etf_share, code)
        consumer['share_lines'].append({'name': name, 'dates': sd, 'changes': sc})

    up_avg = np.mean(con_up_chgs) if con_up_chgs else None
    mid_avg = chg_bj
    down_avg = chg_xf
    consumer['signal_text'], consumer['emoji'] = chain_signal({'up': up_avg, 'mid': mid_avg, 'down': down_avg})
    result['chains']['consumer'] = consumer

    # ═══════ 综合信号 ═══════
    for key in ['tech', 'pharma', 'cycle', 'consumer']:
        c = result['chains'][key]
        result['signals'].append(f"{c['name']} {c['emoji']} {c['signal_text']}")

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
