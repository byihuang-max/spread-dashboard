#!/usr/bin/env python3
"""
中观景气度 - 计算 + 生成JSON
4条产业链: 科技芯片 / 创新药 / 周期 / 消费
"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'chain_prosperity.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def pct_change_n(series, n):
    """计算最近n日涨跌幅(%)"""
    if len(series) < n + 1:
        return None
    return round((series.iloc[-1] / series.iloc[-(n+1)] - 1) * 100, 2)


def share_change_n(series, n):
    """计算最近n日份额变化(万份)"""
    if len(series) < n + 1:
        return None
    return round(series.iloc[-1] - series.iloc[-(n+1)], 2)


def calc_etf_metrics(etf_price, etf_share, code):
    """计算单只ETF的涨跌幅+份额变化"""
    metrics = {'code': code}

    price_df = etf_price[etf_price['ts_code'] == code].copy()
    if not price_df.empty:
        price_df['trade_date'] = price_df['trade_date'].astype(int).astype(str)
        price_df = price_df.sort_values('trade_date')
        price_df['close'] = pd.to_numeric(price_df['close'], errors='coerce')
        series = price_df['close'].dropna()
        metrics['latest'] = round(float(series.iloc[-1]), 3) if len(series) > 0 else None
        metrics['chg_5d'] = pct_change_n(series, 5)
        metrics['chg_20d'] = pct_change_n(series, 20)

    share_df = etf_share[etf_share['ts_code'] == code].copy()
    if not share_df.empty:
        share_df['trade_date'] = share_df['trade_date'].astype(int).astype(str)
        share_df = share_df.sort_values('trade_date')
        share_df['fd_share'] = pd.to_numeric(share_df['fd_share'], errors='coerce')
        series = share_df['fd_share'].dropna()
        metrics['share_chg_5d'] = share_change_n(series, 5)  # 万份
        metrics['latest_share'] = round(float(series.iloc[-1]), 0) if len(series) > 0 else None

    return metrics


def calc_future_metrics(futures_df, generic_code):
    """计算期货品种涨跌幅"""
    df = futures_df[futures_df['generic'] == generic_code].copy()
    if df.empty:
        return None
    df['trade_date'] = df['trade_date'].astype(int).astype(str)
    df = df.sort_values('trade_date')
    df['settle'] = pd.to_numeric(df['settle'], errors='coerce')
    series = df['settle'].dropna()
    if len(series) == 0:
        return None
    return {
        'name': df.iloc[0].get('name', generic_code),
        'latest': round(float(series.iloc[-1]), 1),
        'chg_5d': pct_change_n(series, 5),
        'chg_20d': pct_change_n(series, 20),
    }


def trend_arrow(val):
    if val is None:
        return '—'
    if val > 2:
        return '↗↗'
    elif val > 0.5:
        return '↗'
    elif val > -0.5:
        return '→'
    elif val > -2:
        return '↘'
    else:
        return '↘↘'


def chain_signal(tiers):
    """根据上中下游涨跌判断传导信号"""
    up = tiers.get('upstream', {}).get('direction')
    mid = tiers.get('midstream', {}).get('direction')
    down = tiers.get('downstream', {}).get('direction')

    if up is None and mid is None and down is None:
        return '数据不足', '⬜'

    def pos(d):
        return d is not None and d > 0.5
    def neg(d):
        return d is not None and d < -0.5

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


ETF_NAMES = {
    '512480.SH': '芯片ETF', '159732.SZ': '消费电子ETF', '588000.SH': '科创50ETF',
    '159992.SZ': '创新药ETF', '512010.SH': '医药ETF',
    '516950.SH': '基建ETF', '512200.SH': '房地产ETF',
    '512690.SH': '白酒ETF', '159928.SZ': '消费ETF',
}


def calc():
    etf_price = load_csv('etf_price.csv')
    etf_share = load_csv('etf_share.csv')
    futures = load_csv('futures.csv')
    sw_indices = load_csv('sw_indices.csv')
    ifind = load_csv('ifind_global.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'chains': {},
        'signals': [],
    }

    # ═══════ 科技芯片 ═══════
    tech = {'name': '🔬 科技芯片', 'tiers': {}}

    # 上游: SOXX
    soxx_data = {}
    if not ifind.empty:
        soxx_row = ifind[ifind['code'] == 'SOXX.O']
        if not soxx_row.empty:
            soxx_data = {
                'items': [{'name': 'SOXX费城半导体',
                           'latest': float(soxx_row.iloc[0]['latest']) if pd.notna(soxx_row.iloc[0]['latest']) else None,
                           'chg_pct': float(soxx_row.iloc[0]['pct_change']) if pd.notna(soxx_row.iloc[0].get('pct_change')) else None}],
                'direction': float(soxx_row.iloc[0]['pct_change']) if pd.notna(soxx_row.iloc[0].get('pct_change')) else None,
            }
    tech['tiers']['upstream'] = soxx_data if soxx_data else {'items': [], 'direction': None}

    # 中游: 芯片ETF
    chip_m = calc_etf_metrics(etf_price, etf_share, '512480.SH')
    tech['tiers']['midstream'] = {
        'items': [{'name': '芯片ETF', **chip_m}],
        'direction': chip_m.get('chg_5d'),
    }

    # 下游: 消费电子ETF + 科创50ETF
    ce_m = calc_etf_metrics(etf_price, etf_share, '159732.SZ')
    kc_m = calc_etf_metrics(etf_price, etf_share, '588000.SH')
    down_items = []
    chgs = []
    for name, m in [('消费电子ETF', ce_m), ('科创50ETF', kc_m)]:
        down_items.append({'name': name, **m})
        if m.get('chg_5d') is not None:
            chgs.append(m['chg_5d'])
    tech['tiers']['downstream'] = {
        'items': down_items,
        'direction': np.mean(chgs) if chgs else None,
    }

    tech['signal'], tech['emoji'] = chain_signal(tech['tiers'])
    result['chains']['tech'] = tech

    # ═══════ 创新药 ═══════
    pharma = {'name': '💊 创新药', 'tiers': {}}

    # 上游: 医药行业指数(申万)
    pharma_up_items = []
    if not sw_indices.empty:
        med = sw_indices[sw_indices['ts_code'] == '801150.SI'].copy()
        if not med.empty:
            med['trade_date'] = med['trade_date'].astype(int).astype(str)
            med = med.sort_values('trade_date')
            med['close'] = pd.to_numeric(med['close'], errors='coerce')
            series = med['close'].dropna()
            chg5 = pct_change_n(series, 5)
            pharma_up_items.append({'name': '医药生物(申万)', 'chg_5d': chg5, 'chg_20d': pct_change_n(series, 20)})
            pharma['tiers']['upstream'] = {'items': pharma_up_items, 'direction': chg5}
    if not pharma_up_items:
        pharma['tiers']['upstream'] = {'items': [], 'direction': None}

    # 中游: 创新药ETF
    inno_m = calc_etf_metrics(etf_price, etf_share, '159992.SZ')
    pharma['tiers']['midstream'] = {
        'items': [{'name': '创新药ETF', **inno_m}],
        'direction': inno_m.get('chg_5d'),
    }

    # 下游: 医药ETF
    med_m = calc_etf_metrics(etf_price, etf_share, '512010.SH')
    pharma['tiers']['downstream'] = {
        'items': [{'name': '医药ETF', **med_m}],
        'direction': med_m.get('chg_5d'),
    }

    pharma['signal'], pharma['emoji'] = chain_signal(pharma['tiers'])
    result['chains']['pharma'] = pharma

    # ═══════ 周期 ═══════
    cycle = {'name': '⛏️ 周期', 'tiers': {}}

    # 上游: 铜铝铁矿煤炭
    cycle_up_items = []
    cycle_up_chgs = []
    for code in ['CU.SHF', 'AL.SHF', 'I.DCE', 'ZC.ZCE']:
        fm = calc_future_metrics(futures, code)
        if fm:
            cycle_up_items.append(fm)
            if fm.get('chg_5d') is not None:
                cycle_up_chgs.append(fm['chg_5d'])
    cycle['tiers']['upstream'] = {
        'items': cycle_up_items,
        'direction': np.mean(cycle_up_chgs) if cycle_up_chgs else None,
    }

    # 中游: 螺纹/玻璃/纯碱 + 南华工业品
    cycle_mid_items = []
    cycle_mid_chgs = []
    for code in ['RB.SHF', 'FG.ZCE', 'SA.ZCE']:
        fm = calc_future_metrics(futures, code)
        if fm:
            cycle_mid_items.append(fm)
            if fm.get('chg_5d') is not None:
                cycle_mid_chgs.append(fm['chg_5d'])

    # 南华
    if not sw_indices.empty:
        nh = sw_indices[sw_indices['ts_code'] == 'NHCI.NH'].copy()
        if not nh.empty:
            nh['trade_date'] = nh['trade_date'].astype(int).astype(str)
            nh = nh.sort_values('trade_date')
            nh['close'] = pd.to_numeric(nh['close'], errors='coerce')
            series = nh['close'].dropna()
            chg5 = pct_change_n(series, 5)
            cycle_mid_items.append({'name': '南华工业品', 'latest': round(float(series.iloc[-1]), 1) if len(series) > 0 else None, 'chg_5d': chg5})

    cycle['tiers']['midstream'] = {
        'items': cycle_mid_items,
        'direction': np.mean(cycle_mid_chgs) if cycle_mid_chgs else None,
    }

    # 下游: 基建ETF + 房地产ETF
    jj_m = calc_etf_metrics(etf_price, etf_share, '516950.SH')
    dc_m = calc_etf_metrics(etf_price, etf_share, '512200.SH')
    down_items = []
    down_chgs = []
    for name, m in [('基建ETF', jj_m), ('房地产ETF', dc_m)]:
        down_items.append({'name': name, **m})
        if m.get('chg_5d') is not None:
            down_chgs.append(m['chg_5d'])
    cycle['tiers']['downstream'] = {
        'items': down_items,
        'direction': np.mean(down_chgs) if down_chgs else None,
    }

    cycle['signal'], cycle['emoji'] = chain_signal(cycle['tiers'])
    result['chains']['cycle'] = cycle

    # ═══════ 消费 ═══════
    consumer = {'name': '🛒 消费', 'tiers': {}}

    # 上游: 生猪/大豆/棕榈油
    con_up_items = []
    con_up_chgs = []
    for code in ['LH.DCE', 'A.DCE', 'P.DCE']:
        fm = calc_future_metrics(futures, code)
        if fm:
            con_up_items.append(fm)
            if fm.get('chg_5d') is not None:
                con_up_chgs.append(fm['chg_5d'])
    consumer['tiers']['upstream'] = {
        'items': con_up_items,
        'direction': np.mean(con_up_chgs) if con_up_chgs else None,
    }

    # 中游: 白酒ETF + 食品饮料(申万)
    bj_m = calc_etf_metrics(etf_price, etf_share, '512690.SH')
    con_mid_items = [{'name': '白酒ETF', **bj_m}]
    con_mid_chg = bj_m.get('chg_5d')

    if not sw_indices.empty:
        fb = sw_indices[sw_indices['ts_code'] == '801120.SI'].copy()
        if not fb.empty:
            fb['trade_date'] = fb['trade_date'].astype(int).astype(str)
            fb = fb.sort_values('trade_date')
            fb['close'] = pd.to_numeric(fb['close'], errors='coerce')
            series = fb['close'].dropna()
            chg5 = pct_change_n(series, 5)
            con_mid_items.append({'name': '食品饮料(申万)', 'chg_5d': chg5, 'chg_20d': pct_change_n(series, 20)})

    consumer['tiers']['midstream'] = {
        'items': con_mid_items,
        'direction': con_mid_chg,
    }

    # 下游: 消费ETF
    xf_m = calc_etf_metrics(etf_price, etf_share, '159928.SZ')
    consumer['tiers']['downstream'] = {
        'items': [{'name': '消费ETF', **xf_m}],
        'direction': xf_m.get('chg_5d'),
    }

    consumer['signal'], consumer['emoji'] = chain_signal(consumer['tiers'])
    result['chains']['consumer'] = consumer

    # ═══════ 综合信号 ═══════
    for key in ['tech', 'pharma', 'cycle', 'consumer']:
        c = result['chains'][key]
        result['signals'].append(f"{c['name']} {c['emoji']} {c['signal']}")

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
