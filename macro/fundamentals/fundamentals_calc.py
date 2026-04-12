#!/usr/bin/env python3
import os
import json

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'fundamentals.json')
PROFIT_CYCLE_JSON = os.path.join(SCRIPT_DIR, 'profit_cycle', 'profit_cycle.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def latest_valid(df, col):
    if df.empty or col not in df.columns:
        return None
    s = df.dropna(subset=[col])
    if s.empty:
        return None
    return s.iloc[-1]


def last_n_values(df, col, n=3):
    if df.empty or col not in df.columns:
        return []
    vals = pd.to_numeric(df[col], errors='coerce').dropna().tolist()
    return vals[-n:]


def trend_label(vals, tol=0.15):
    if len(vals) < 2:
        return '持平'
    delta = vals[-1] - vals[0]
    if delta > tol:
        return '上行'
    if delta < -tol:
        return '下行'
    return '持平'


def load_profit_cycle():
    if not os.path.exists(PROFIT_CYCLE_JSON):
        return {}
    with open(PROFIT_CYCLE_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def merge_monthly_series(series_map):
    merged = None
    for field, csv_name in series_map:
        df = load_csv(csv_name)
        if df.empty or field not in df.columns or 'month' not in df.columns:
            continue
        df = df[['month', field]].copy()
        df['month'] = df['month'].astype(str)
        df[field] = pd.to_numeric(df[field], errors='coerce')
        merged = df if merged is None else merged.merge(df, on='month', how='outer')
    if merged is None:
        return pd.DataFrame()
    return merged.sort_values('month')


def build_growth_breakdown():
    field_map = [
        ('industrial_production_yoy', 'industrial_production_yoy.csv'),
        ('retail_sales_yoy', 'retail_sales_yoy.csv'),
        ('exports_yoy', 'exports_yoy.csv'),
        ('fai_ytd_yoy', 'fai_ytd_yoy.csv'),
        ('manufacturing_investment_ytd_yoy', 'manufacturing_investment_ytd_yoy.csv'),
        ('infrastructure_investment_ytd_yoy', 'infrastructure_investment_ytd_yoy.csv'),
        ('real_estate_investment_ytd_yoy', 'real_estate_investment_ytd_yoy.csv'),
    ]
    df = merge_monthly_series(field_map)
    if df.empty:
        return None
    core = ['industrial_production_yoy', 'retail_sales_yoy', 'exports_yoy', 'fai_ytd_yoy']
    latest = df.dropna(how='all', subset=[c for c in core if c in df.columns]).iloc[-1]
    improve_count = 0
    weak_count = 0
    for col in [c for c in core if c in df.columns]:
        vals = last_n_values(df, col, 3)
        if trend_label(vals) == '上行':
            improve_count += 1
        lv = latest.get(col)
        if pd.notna(lv) and float(lv) < 3:
            weak_count += 1
    status = '结构修复'
    if improve_count >= 3 and weak_count <= 1:
        status = '全面修复'
    elif improve_count <= 1 and weak_count >= 2:
        status = '偏弱'
    drivers = []
    labels = {'industrial_production_yoy': '工业', 'retail_sales_yoy': '消费', 'exports_yoy': '出口', 'fai_ytd_yoy': '投资'}
    for col in core:
        if col in df.columns and trend_label(last_n_values(df, col, 3)) == '上行':
            drivers.append(labels[col])
    summary = '、'.join(drivers[:2]) + '在拉动修复。' if drivers else '主要分项暂未形成同步改善。'
    series = []
    for _, r in df.tail(24).iterrows():
        item = {'month': str(r['month'])}
        for col in df.columns:
            if col == 'month':
                continue
            item[col] = round(float(r[col]), 2) if pd.notna(r[col]) else None
        series.append(item)
    latest_out = {col: (round(float(latest[col]), 2) if pd.notna(latest[col]) else None) for col in df.columns if col != 'month'}
    return {'status': status, 'summary': summary, 'latest': latest_out, 'series': series}


def build_credit_structure():
    field_map = [
        ('tsf_stock_yoy', 'tsf_stock_yoy.csv'),
        ('tsf_stock_value', 'tsf_stock_value.csv'),
        ('gov_bond_share_in_tsf', 'gov_bond_share_in_tsf.csv'),
        ('household_medium_long_loan', 'household_medium_long_loan.csv'),
        ('corp_medium_long_loan', 'corp_medium_long_loan.csv'),
        ('m1_yoy', 'm1_yoy.csv'),
        ('m2_yoy', 'm2_yoy.csv'),
    ]
    df = merge_monthly_series(field_map)
    if df.empty:
        return None
    if 'm1_yoy' in df.columns and 'm2_yoy' in df.columns:
        df['m1_m2_scissors'] = df['m1_yoy'] - df['m2_yoy']
    latest = df.iloc[-1]
    corp = float(latest['corp_medium_long_loan']) if 'corp_medium_long_loan' in df.columns and pd.notna(latest['corp_medium_long_loan']) else None
    hh = float(latest['household_medium_long_loan']) if 'household_medium_long_loan' in df.columns and pd.notna(latest['household_medium_long_loan']) else None
    gov_share = float(latest['gov_bond_share_in_tsf']) if 'gov_bond_share_in_tsf' in df.columns and pd.notna(latest['gov_bond_share_in_tsf']) else None
    scissors = float(latest['m1_m2_scissors']) if 'm1_m2_scissors' in df.columns and pd.notna(latest['m1_m2_scissors']) else None
    status = '托底扩张'
    if corp is not None and hh is not None and scissors is not None and corp > 0 and hh > 0 and scissors > -3:
        status = '有效扩张'
    elif scissors is not None and scissors < -5:
        status = '空转扩张'
    summary = f'企业中长贷 {corp:.0f}、居民中长贷 {hh:.0f}、政府债占比 {gov_share:.1f}% 。' if None not in [corp, hh, gov_share] else '信用分项已接入，可先观察总量、政府债占比与中长期贷款结构。'
    series = []
    for _, r in df.tail(24).iterrows():
        item = {'month': str(r['month'])}
        for col in df.columns:
            if col == 'month':
                continue
            item[col] = round(float(r[col]), 2) if pd.notna(r[col]) else None
        series.append(item)
    latest_out = {col: (round(float(latest[col]), 2) if pd.notna(latest[col]) else None) for col in df.columns if col != 'month'}
    return {'status': status, 'summary': summary, 'latest': latest_out, 'series': series}




def build_inventory_cycle():
    field_map = [
        ('finished_goods_inventory_yoy', 'finished_goods_inventory_yoy.csv'),
        ('industrial_profit_ytd_yoy', 'industrial_profit_ytd_yoy.csv'),
        ('pmi_finished_goods_inventory', 'pmi_finished_goods_inventory.csv'),
        ('pmi_raw_material_inventory', 'pmi_raw_material_inventory.csv'),
    ]
    df = merge_monthly_series(field_map)
    if df.empty:
        return None
    latest = df.iloc[-1]
    inv = float(latest['finished_goods_inventory_yoy']) if 'finished_goods_inventory_yoy' in df.columns and pd.notna(latest['finished_goods_inventory_yoy']) else None
    profit = float(latest['industrial_profit_ytd_yoy']) if 'industrial_profit_ytd_yoy' in df.columns and pd.notna(latest['industrial_profit_ytd_yoy']) else None
    pmi_fg = float(latest['pmi_finished_goods_inventory']) if 'pmi_finished_goods_inventory' in df.columns and pd.notna(latest['pmi_finished_goods_inventory']) else None
    pmi_rm = float(latest['pmi_raw_material_inventory']) if 'pmi_raw_material_inventory' in df.columns and pd.notna(latest['pmi_raw_material_inventory']) else None
    status='被动去库'
    if inv is not None and profit is not None:
        if inv > 5 and profit > 5:
            status='主动补库'
        elif inv > 3 and profit >= 0:
            status='被动补库'
        elif inv < 3 and profit < 0:
            status='主动去库'
    summary=f'产成品库存 {inv:.1f}% 、工业利润 {profit:.1f}% 、PMI产成品库存 {pmi_fg:.1f}。' if None not in [inv, profit, pmi_fg] else '库存周期字段已补进来，后续可再叠 PPI 做更完整判断。'
    series=[]
    for _, r in df.tail(24).iterrows():
        item={'month':str(r['month'])}
        for col in df.columns:
            if col=='month': continue
            item[col]=round(float(r[col]),2) if pd.notna(r[col]) else None
        series.append(item)
    latest_out = {col: (round(float(latest[col]), 2) if pd.notna(latest[col]) else None) for col in df.columns if col != 'month'}
    return {'status':status,'summary':summary,'latest':latest_out,'series':series}

def build_property_recovery():
    field_map = [
        ('property_sales_area_yoy', 'property_sales_area_yoy.csv'),
        ('real_estate_investment_ytd_yoy', 'real_estate_investment_ytd_yoy.csv'),
        ('household_medium_long_loan', 'household_medium_long_loan.csv'),
    ]
    df = merge_monthly_series(field_map)
    if df.empty:
        return None
    latest = df.iloc[-1]
    sales = float(latest['property_sales_area_yoy']) if 'property_sales_area_yoy' in df.columns and pd.notna(latest['property_sales_area_yoy']) else None
    invest = float(latest['real_estate_investment_ytd_yoy']) if 'real_estate_investment_ytd_yoy' in df.columns and pd.notna(latest['real_estate_investment_ytd_yoy']) else None
    hh = float(latest['household_medium_long_loan']) if 'household_medium_long_loan' in df.columns and pd.notna(latest['household_medium_long_loan']) else None
    status = '政策托底'
    if sales is not None and invest is not None:
        if sales > 0 and invest > -5:
            status = '弱修复'
        elif sales > -5 and invest > -10:
            status = '低位企稳'
        elif sales < -10 and invest < -10:
            status = '继续探底'
    summary = f'销售面积 {sales:.1f}% 、地产投资 {invest:.1f}% 、居民中长贷 {hh:.0f}。' if None not in [sales, invest, hh] else '地产三件套已接入，后续可继续补新开工和竣工。'
    series = []
    for _, r in df.tail(24).iterrows():
        item = {'month': str(r['month'])}
        for col in df.columns:
            if col == 'month':
                continue
            item[col] = round(float(r[col]), 2) if pd.notna(r[col]) else None
        series.append(item)
    latest_out = {col: (round(float(latest[col]), 2) if pd.notna(latest[col]) else None) for col in df.columns if col != 'month'}
    return {'status': status, 'summary': summary, 'latest': latest_out, 'series': series}


def build_macro_hypothesis(context):
    pmi_val = context.get('pmi_val')
    pmi_trend = context.get('pmi_trend')
    cpi_val = context.get('cpi_val')
    cpi_trend = context.get('cpi_trend')
    ppi_val = context.get('ppi_val')
    ppi_trend = context.get('ppi_trend')
    scissors = context.get('scissors')
    profit_stage = context.get('profit_stage')
    profit_score = context.get('profit_score')
    demand_score = context.get('demand_score')
    ppi_mom = context.get('ppi_mom')
    m1_m2_scissors = context.get('m1_m2_scissors')

    growth_support = '中性'
    growth_reason = '增长端缺少足够信号。'
    if pmi_val is not None:
        if pmi_val >= 50 and pmi_trend == '上行':
            growth_support = '支持'
            growth_reason = f'PMI {pmi_val:.1f} 位于荣枯线附近并继续上行，增长边际改善。'
        elif pmi_val >= 50:
            growth_support = '中性偏支持'
            growth_reason = f'PMI {pmi_val:.1f} 站上荣枯线，但趋势不算很强。'
        else:
            growth_support = '不支持'
            growth_reason = f'PMI {pmi_val:.1f} 仍未明显站稳荣枯线，增长修复不扎实。'

    inflation_support = '中性'
    inflation_reason = '价格端缺少足够信号。'
    if cpi_val is not None and ppi_val is not None:
        if ppi_mom is not None and ppi_mom > 0 and ppi_trend == '上行':
            inflation_support = '支持'
            inflation_reason = f'CPI {cpi_val:.1f}%、PPI {ppi_val:.1f}% 同步改善，且PPI环比转正，价格修复成立。'
        elif ppi_trend == '上行' or cpi_trend == '上行':
            inflation_support = '中性偏支持'
            inflation_reason = f'CPI {cpi_val:.1f}% 与 PPI {ppi_val:.1f}% 至少有一端改善，通缩压力在缓和。'
        else:
            inflation_support = '不支持'
            inflation_reason = f'CPI {cpi_val:.1f}% 与 PPI {ppi_val:.1f}% 尚未体现出明确的价格修复。'

    profit_support = '中性'
    profit_reason = '利润周期信号不足。'
    if profit_stage:
        if profit_stage in ['上行', '见顶']:
            profit_support = '支持'
            profit_reason = f'利润周期处于{profit_stage}阶段（{profit_score}/4分），盈利修复交易仍在。'
        elif profit_stage == '筑底':
            profit_support = '中性'
            profit_reason = f'利润周期仍在{profit_stage}阶段，更多是等待修复确认。'
        else:
            profit_support = '不支持'
            profit_reason = f'利润周期处于{profit_stage}阶段，盈利逻辑偏弱。'

    demand_support = '中性'
    demand_reason = '内需接棒尚无完整验证。'
    if demand_score is not None:
        if demand_score >= 67 and m1_m2_scissors is not None and m1_m2_scissors > 0:
            demand_support = '支持'
            demand_reason = f'内需接棒 {demand_score}/100，且 M1-M2 剪刀差为 {m1_m2_scissors:.1f}，内生需求接力较明确。'
        elif demand_score >= 67:
            demand_support = '中性偏支持'
            demand_reason = f'内需接棒 {demand_score}/100，但 M1-M2 剪刀差为 {m1_m2_scissors:.1f}，信用脉冲仍待确认。'
        elif demand_score >= 34:
            demand_support = '中性'
            demand_reason = f'内需接棒 {demand_score}/100，只有结构性改善，尚不能定性为全面接棒。'
        else:
            demand_support = '不支持'
            demand_reason = f'内需接棒 {demand_score}/100，居民和企业内生需求偏弱。'

    title = '宏观信号等待更多确认'
    summary = '当前宏观线索还不够集中，市场更像在局部试探，而不是形成统一交易主线。'
    confidence = '低'
    labels = ['观察期']

    if growth_support in ['支持', '中性偏支持'] and inflation_support in ['支持', '中性偏支持'] and profit_support == '支持':
        if demand_support in ['不支持', '中性']:
            title = '弱复苏中的价格修复'
            summary = '市场当前更像在交易名义增长修复、工业价格改善和盈利修复，但内需与信用接力还不够扎实。'
            confidence = '中'
            labels = ['弱复苏', '价格修复', '盈利修复']
        else:
            title = '再通胀预期交易'
            summary = '增长、价格、利润和内需链条都在改善，市场正在交易更完整的再通胀叙事。'
            confidence = '中高'
            labels = ['再通胀', '盈利修复', '内需接棒']
    elif inflation_support in ['支持', '中性偏支持'] and profit_support == '支持':
        title = '盈利修复先行，内需仍待确认'
        summary = '当前更像是价格修复和利润修复先走在前面，内需和信用尚未完全跟上。'
        confidence = '中'
        labels = ['盈利修复', '内需未确认']
    elif growth_support == '不支持' and inflation_support == '不支持':
        title = '增长与价格仍偏弱'
        summary = '增长和价格两端都没有形成清晰改善，市场很难形成强宏观主线。'
        confidence = '中'
        labels = ['增长偏弱', '价格偏弱']

    phenomena = []
    if pmi_val is not None:
        phenomena.append(f'PMI {pmi_val:.1f}，趋势{pmi_trend}，增长端处于边际观察区。')
    if cpi_val is not None and ppi_val is not None:
        txt = f'CPI {cpi_val:.1f}%、PPI {ppi_val:.1f}%'
        if scissors is not None:
            txt += f'，剪刀差 {scissors:+.1f}%'
        phenomena.append(txt + '，价格端处于修复验证阶段。')
    if profit_stage:
        phenomena.append(f'利润周期 {profit_stage}（{profit_score}/4分），盈利环境已从纯防守区切出。')
    if demand_score is not None:
        phenomena.append(f'内需接棒 {demand_score}/100，当前仍需观察信用与内生需求是否继续接力。')

    logic_chains = [
        {
            'name': '增长-通胀链',
            'status': '支持' if growth_support in ['支持', '中性偏支持'] and inflation_support in ['支持', '中性偏支持'] else '中性' if growth_support != '不支持' or inflation_support != '不支持' else '不支持',
            'explanation': growth_reason + ' ' + inflation_reason,
            'data_points': ['PMI', 'CPI', 'PPI', 'CPI-PPI剪刀差']
        },
        {
            'name': '利润周期链',
            'status': profit_support,
            'explanation': profit_reason,
            'data_points': ['profit_cycle_score', 'profit_cycle_stage', 'ppi_mom']
        },
        {
            'name': '内需接棒链',
            'status': demand_support,
            'explanation': demand_reason,
            'data_points': ['demand_recovery_score', 'core_cpi_yoy', 'm1_m2_scissors']
        }
    ]

    unconfirmed = [
        '该判断基于最新已公布月度宏观数据，不是日频交易信号。',
        '内需接棒目前仍是简化验证，尚未纳入社融结构、居民中长贷、企业中长贷、地产销售等更硬的数据。'
    ]
    if m1_m2_scissors is not None and m1_m2_scissors <= 0:
        unconfirmed.append('M1-M2 剪刀差仍偏弱，说明信用脉冲和企业活力还没有完全接上。')
    if profit_stage == '见顶':
        unconfirmed.append('利润周期已在高位，需警惕“修复交易”进入后段后被过度外推。')

    brief = '当前交易：' + title
    if demand_support in ['不支持', '中性', '中性偏支持']:
        brief += '；未验证：内需与信用接力'
    elif profit_stage == '见顶':
        brief += '；提醒：利润修复已到后段'

    return {
        'title': title,
        'summary': summary,
        'brief': brief,
        'confidence': confidence,
        'monthly_note': '注：本卡片基于最新已公布月度宏观数据生成，日内刷新仅同步展示，不代表宏观判断会高频变化。',
        'phenomena': phenomena,
        'logic_chains': logic_chains,
        'unconfirmed': unconfirmed,
        'labels': labels
    }


def calc():
    pmi = load_csv('pmi.csv')
    cpi = load_csv('cpi.csv')
    ppi = load_csv('ppi.csv')
    profit_cycle = load_profit_cycle()
    profit_latest = profit_cycle.get('latest', {}) if profit_cycle else {}

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'signals': [],
    }

    result['growth_breakdown'] = build_growth_breakdown()
    result['credit_structure'] = build_credit_structure()
    result['property_recovery'] = build_property_recovery()
    result['inventory_cycle'] = build_inventory_cycle()

    latest_pmi_val = None
    latest_cpi_val = None
    latest_ppi_val = None
    latest_scissors = None
    pmi_trend = '持平'
    cpi_trend = '持平'
    ppi_trend = '持平'

    if not pmi.empty:
        pmi = pmi.sort_values('month')
        for col in pmi.columns:
            if col != 'month':
                pmi[col] = pd.to_numeric(pmi[col], errors='coerce')

        pmi_data = []
        for _, r in pmi.iterrows():
            d = {'month': str(r['month']).replace('.0', '')}
            if pd.notna(r.get('pmi')):
                d['pmi'] = round(float(r['pmi']), 1)
            if 'pmi_nmp' in pmi.columns and pd.notna(r.get('pmi_nmp')):
                d['pmi_nmp'] = round(float(r['pmi_nmp']), 1)
            pmi_data.append(d)
        result['pmi'] = pmi_data

        latest_pmi = latest_valid(pmi, 'pmi')
        if latest_pmi is not None:
            latest_pmi_val = round(float(latest_pmi['pmi']), 1)
            pmi_trend = trend_label(last_n_values(pmi, 'pmi', 3))
            if latest_pmi_val >= 51:
                result['signals'].append(f"PMI {latest_pmi_val:.1f}，制造业扩张，趋势{pmi_trend} 🟢")
            elif latest_pmi_val < 49:
                result['signals'].append(f"PMI {latest_pmi_val:.1f}，制造业收缩，趋势{pmi_trend} 🔴")
            else:
                result['signals'].append(f"PMI {latest_pmi_val:.1f}，荣枯线附近，趋势{pmi_trend} 🟡")

    if not cpi.empty and not ppi.empty:
        cpi = cpi.sort_values('month')
        ppi = ppi.sort_values('month')
        cpi['nt_yoy'] = pd.to_numeric(cpi['nt_yoy'], errors='coerce')
        ppi['ppi_yoy'] = pd.to_numeric(ppi['ppi_yoy'], errors='coerce')

        merged = cpi.merge(ppi, on='month', how='outer').sort_values('month')
        merged['scissors'] = merged['nt_yoy'] - merged['ppi_yoy']

        result['cpi_ppi'] = [
            {
                'month': str(r['month']).replace('.0', ''),
                'cpi': round(float(r['nt_yoy']), 1) if pd.notna(r.get('nt_yoy')) else None,
                'ppi': round(float(r['ppi_yoy']), 1) if pd.notna(r.get('ppi_yoy')) else None,
                'scissors': round(float(r['scissors']), 1) if pd.notna(r.get('scissors')) else None,
            }
            for _, r in merged.iterrows()
        ]

        latest = merged.dropna(subset=['nt_yoy', 'ppi_yoy']).iloc[-1]
        latest_cpi_val = float(latest['nt_yoy'])
        latest_ppi_val = float(latest['ppi_yoy'])
        latest_scissors = float(latest['scissors'])
        cpi_trend = trend_label(last_n_values(merged, 'nt_yoy', 3))
        ppi_trend = trend_label(last_n_values(merged, 'ppi_yoy', 3))

        if latest_scissors > 3:
            result['signals'].append(f"CPI-PPI剪刀差 {latest_scissors:+.1f}%，下游利润承压 ⚠️")
        elif latest_scissors < 0:
            result['signals'].append("PPI仍低于CPI，利润修复仍在传导 🟡")

        if latest_ppi_val < -2:
            result['signals'].append(f"PPI {latest_ppi_val:+.1f}%，工业通缩未完全出清 🔴")
        else:
            result['signals'].append(f"核心CPI {latest_cpi_val:.1f}%（{cpi_trend}），PPI {latest_ppi_val:.1f}%（{ppi_trend}）")

    if latest_pmi_val is not None and latest_cpi_val is not None:
        econ_up = latest_pmi_val > 50
        infl_up = latest_cpi_val > 2.5

        if econ_up and not infl_up:
            clock = '复苏期'
            clock_emoji = '🌱'
            clock_advice = '超配股票，低配债券'
        elif econ_up and infl_up:
            clock = '过热期'
            clock_emoji = '🔥'
            clock_advice = '超配商品，低配债券'
        elif (not econ_up) and infl_up:
            clock = '滞胀期'
            clock_emoji = '⚠️'
            clock_advice = '超配现金，低配股票'
        else:
            clock = '衰退期'
            clock_emoji = '❄️'
            clock_advice = '超配债券，低配商品'

        result['merrill_clock'] = {
            'phase': clock,
            'emoji': clock_emoji,
            'advice': clock_advice,
            'pmi': latest_pmi_val,
            'cpi': latest_cpi_val,
        }
        result['signals'].append(f"美林时钟: {clock_emoji} {clock}（PMI={latest_pmi_val:.1f}, CPI={latest_cpi_val:.1f}%）")

    if profit_latest:
        stage = profit_latest.get('profit_cycle_stage')
        score = profit_latest.get('profit_cycle_score')
        ppi_mom = profit_latest.get('ppi_mom')
        demand_score = profit_latest.get('demand_recovery_score')
        m1_m2_scissors = profit_latest.get('m1_m2_scissors')

        if stage == '上行':
            result['signals'].append(f"利润周期: {stage}（{score}/4分），股票策略适配度提升 🟢")
        elif stage == '见顶':
            result['signals'].append(f"利润周期: {stage}（{score}/4分），修复强但需防过热 ⚠️")
        elif stage == '下行':
            result['signals'].append(f"利润周期: {stage}（{score}/4分），防御为主 🔴")
        elif stage == '筑底' and ppi_mom is not None and ppi_mom > -0.5:
            result['signals'].append(f"利润周期: {stage}（{score}/4分），等待拐点 🟡")

        if demand_score is not None:
            if demand_score >= 67:
                if m1_m2_scissors is None:
                    result['signals'].append(f"内需接棒: {demand_score}/100分，内需修复较强 🌱")
                elif m1_m2_scissors > 0:
                    result['signals'].append(f"内需接棒: {demand_score}/100分，居民/企业内生需求回升 🌱")
                else:
                    result['signals'].append(f"内需接棒: {demand_score}/100分，但信用脉冲仍待确认 🟡")
            elif demand_score >= 34:
                result['signals'].append(f"内需接棒: {demand_score}/100分，结构性改善 🟡")
            else:
                result['signals'].append(f"内需接棒: {demand_score}/100分，仍偏弱 🔴")

        result['macro_hypothesis'] = build_macro_hypothesis({
            'pmi_val': latest_pmi_val,
            'pmi_trend': pmi_trend,
            'cpi_val': latest_cpi_val,
            'cpi_trend': cpi_trend,
            'ppi_val': latest_ppi_val,
            'ppi_trend': ppi_trend,
            'scissors': latest_scissors,
            'profit_stage': stage,
            'profit_score': score,
            'demand_score': demand_score,
            'ppi_mom': ppi_mom,
            'm1_m2_scissors': m1_m2_scissors,
        })

    if not result['signals']:
        result['signals'] = ['基本面指标无极端信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
