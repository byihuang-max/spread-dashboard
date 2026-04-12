#!/usr/bin/env python3
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path.home() / 'Desktop' / 'gamt-dashboard'
DATA = ROOT / 'data'
SNAPSHOT = DATA / 'financial_risk_snapshot.json'
OUTPUT = DATA / 'financial_risk_factor.json'

AS_OF_PERIODS = ['20241231', '20250331', '20250630', '20250930']
HISTORY_WINDOWS = 12

# 行业规则骨架：先给页面可用的解释器底座，后续可继续细化
RULEBOOK = {
    '银行': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润增速', '资产质量', '拨备覆盖', '资本充足'],
        'logic': '银行经营的是资产负债表而不是普通利润表，核心看资产质量、拨备和资本约束。',
        'blowup_mechanism': '宏观走弱或信用恶化后，不良暴露抬升，拨备侵蚀利润，资本压力显性化。',
        'hard_exclude': '利润明显恶化且资产质量同步变差。',
        'soft_exclude': '利润承压但资本与资产质量仍稳，列入观察不直接剔除。',
    },
    '非银金融': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润波动', '资本实力', '风险资产敞口', '现金头寸'],
        'logic': '非银利润受市场波动、投资收益和资本约束影响较大。',
        'blowup_mechanism': '市场下行或信用风险上升时，投资亏损与业务收缩叠加，利润和杠杆约束同步恶化。',
        'hard_exclude': '盈利塌陷且风险资产敞口高、杠杆偏重。',
        'soft_exclude': '单季利润受市场影响大，但资本和风控尚可的列观察。',
    },
    '房地产': {
        'report_period': '四截面滚动',
        'focus_metrics': ['货币资金', '短期借款', '经营现金流', '资产负债率'],
        'logic': '房地产核心不是利润，而是资金链和债务滚动能力。',
        'blowup_mechanism': '销售回款差会先伤到现金流，再传导到债务滚动和报表稳定性。',
        'hard_exclude': '货币资金覆盖不了短债，且经营现金流为负、利润明显恶化。',
        'soft_exclude': '利润弱但资金链暂稳的列观察。',
    },
    '建筑材料': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '建材是周期行业，关注利润、现金流和库存应收是否同步走坏。',
        'blowup_mechanism': '地产链或基建需求走弱后，价格和销量承压，库存和回款问题逐步暴露。',
        'hard_exclude': '利润下滑、现金流转负、库存或应收同步恶化。',
        'soft_exclude': '周期底部利润差但资金面未恶化的列观察。',
    },
    '建筑装饰': {
        'report_period': '四截面滚动',
        'focus_metrics': ['经营现金流', '应收账款', '利润同比', '负债压力'],
        'logic': '建筑装饰是项目制行业，利润表经常滞后，现金流和应收更关键。',
        'blowup_mechanism': '项目延后和回款不畅会先推高应收，再压制现金流和利润质量。',
        'hard_exclude': '利润恶化且经营现金流为负，同时应收高企。',
        'soft_exclude': '利润尚稳但回款恶化的列观察。',
    },
    '钢铁': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '资产负债率'],
        'logic': '钢铁是典型重周期行业，关键看利润、现金流和杠杆。',
        'blowup_mechanism': '价格和需求下行时，利润先压缩，随后现金流和负债压力加剧。',
        'hard_exclude': '利润和现金流同步恶化，且杠杆偏高。',
        'soft_exclude': '单季利润差但资产负债表仍稳的列观察。',
    },
    '有色金属': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '资产负债率', '存货'],
        'logic': '有色受商品价格驱动，重点看连续恶化而非单季波动。',
        'blowup_mechanism': '金属价格回落或成本抬升后，盈利和现金流同步收缩。',
        'hard_exclude': '利润、现金流、杠杆三项同步走坏。',
        'soft_exclude': '资源价格波动造成的单季扰动列观察。',
    },
    '基础化工': {
        'report_period': '四截面滚动',
        'focus_metrics': ['经营现金流', '货币资金/短债', '利润同比', '存货'],
        'logic': '化工最怕景气下行时利润、现金流和资金链一起坏。',
        'blowup_mechanism': '周期走弱后，盈利恶化先传导到现金流，再暴露短债覆盖不足。',
        'hard_exclude': '经营现金流为负且货币资金小于短债。',
        'soft_exclude': '利润差但资金链暂稳的列观察。',
    },
    '石油石化': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '资本结构'],
        'logic': '石油石化利润受油价周期和库存损益扰动较大。',
        'blowup_mechanism': '价格波动会先影响利润，再影响现金流和重资产回收周期。',
        'hard_exclude': '利润和现金流持续走弱，且重资产压力加大。',
        'soft_exclude': '由油价波动导致的单季失真列观察。',
    },
    '煤炭': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '资产负债率', '货币资金'],
        'logic': '煤炭关键看现金创造能力和负债约束。',
        'blowup_mechanism': '煤价回落后，利润和现金流同步收缩，高杠杆公司压力更大。',
        'hard_exclude': '利润与现金流连续恶化且杠杆高。',
        'soft_exclude': '周期回落但现金回收仍强的列观察。',
    },
    '电力设备': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '电力设备是成长行业，但要防价格战和扩产把经营质量拖坏。',
        'blowup_mechanism': '行业内卷时利润先压缩，再向存货、应收和现金流传导。',
        'hard_exclude': '利润恶化、现金流恶化、存货或应收同步恶化。',
        'soft_exclude': '利润差但仍处扩产爬坡、资产负债表稳的列观察。',
    },
    '机械设备': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '应收周转'],
        'logic': '机械设备本质是订单和回款行业，现金流比利润更重要。',
        'blowup_mechanism': '下游资本开支收缩后，订单与回款双弱，利润质量变差。',
        'hard_exclude': '利润大降、经营现金流为负、应收恶化。',
        'soft_exclude': '利润尚稳但回款明显变差的列观察。',
    },
    '国防军工': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '存货'],
        'logic': '军工要看订单兑现和回款节奏，单季扰动不能机械放大。',
        'blowup_mechanism': '验收和回款延后会先压制现金流，再影响利润兑现。',
        'hard_exclude': '多个截面持续利润承压且回款恶化。',
        'soft_exclude': '单季波动但订单与经营质量仍稳的列观察。',
    },
    '汽车': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '汽车行业要看价格战、库存和渠道压力是否传导到现金流。',
        'blowup_mechanism': '价格战和销量承压会导致毛利压缩，再推动库存和现金流恶化。',
        'hard_exclude': '利润快速恶化、库存压力上升、经营现金流转弱。',
        'soft_exclude': '利润波动但库存和现金链仍稳的列观察。',
    },
    '家用电器': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '家电行业重点看渠道库存和现金流质量。',
        'blowup_mechanism': '需求放缓时，渠道压货会先体现在库存和回款上，再拖累利润。',
        'hard_exclude': '利润弱、现金流弱、渠道库存迹象明显。',
        'soft_exclude': '龙头利润波动但经营质量仍稳的列观察。',
    },
    '电子': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '货币资金/短债'],
        'logic': '电子行业要区分研发投入期和经营失控期，不能机械按利润差判雷。',
        'blowup_mechanism': '景气下行、去库存或扩产错配后，利润、现金流、存货和短债压力会逐步暴露。',
        'hard_exclude': '利润恶化、现金流恶化、存货或短债压力同步抬升。',
        'soft_exclude': '半导体处研发投入期但资金链未坏的列观察。',
    },
    '计算机': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '应收周转'],
        'logic': '计算机行业最怕纸面利润还在，但回款已经恶化。',
        'blowup_mechanism': '项目延期和客户付款变慢会先推高应收，再压制现金流和利润质量。',
        'hard_exclude': '利润恶化、经营现金流偏弱、应收恶化。',
        'soft_exclude': '利润增速回落但现金流和周转仍稳的列观察。',
    },
    '通信': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '存货'],
        'logic': '通信设备同样有项目周期，关注订单兑现和回款节奏。',
        'blowup_mechanism': '客户资本开支收缩或项目延后，会先影响应收和现金流，再传导到利润。',
        'hard_exclude': '利润下滑、应收走高、现金流转弱。',
        'soft_exclude': '单季项目扰动但经营质量未坏的列观察。',
    },
    '传媒': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '资产减值迹象'],
        'logic': '传媒行业最需要防的是财务质量连续恶化。',
        'blowup_mechanism': '广告、内容或营销兑现弱时，利润下滑会先伴随现金流和减值压力。',
        'hard_exclude': '利润差、现金流差、应收或减值压力大。',
        'soft_exclude': '波动较大但财务质量未持续恶化的列观察。',
    },
    '医药生物': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '应收账款', '存货'],
        'logic': '医药要看利润质量和商业化兑现，不能只看单期利润。',
        'blowup_mechanism': '集采、渠道压货或研发失利后，应收和存货往往先于利润全面恶化。',
        'hard_exclude': '利润弱、现金流弱、应收或存货恶化。',
        'soft_exclude': '创新药研发投入期但资金压力可控的列观察。',
    },
    '食品饮料': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '食饮关键看需求、渠道和利润质量。',
        'blowup_mechanism': '需求转弱和渠道压货会先推高库存，再压制现金流和利润质量。',
        'hard_exclude': '利润差、现金流差、渠道库存压力明显。',
        'soft_exclude': '白马龙头利润波动但渠道和现金流仍稳的列观察。',
    },
    '农林牧渔': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货/生物资产', '资产负债率'],
        'logic': '农林牧渔强周期，单看利润很容易误伤。',
        'blowup_mechanism': '价格周期下行后，利润和现金流会剧烈波动，资产质量差的公司更脆弱。',
        'hard_exclude': '周期差、资金链差、资产质量同步恶化。',
        'soft_exclude': '周期位置不利但资金链尚可的列观察。',
    },
    '商贸零售': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '零售核心是周转，不是单一利润点。',
        'blowup_mechanism': '消费弱时库存积压和周转变慢会先伤现金流，再压利润。',
        'hard_exclude': '利润恶化、库存压力大、现金流走弱。',
        'soft_exclude': '利润弱但周转和现金流仍稳的列观察。',
    },
    '社会服务': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '费用率', '应收/预收'],
        'logic': '社会服务要看需求恢复和费用吸收能力。',
        'blowup_mechanism': '需求恢复不及预期时，利润和现金流都容易弱于表面收入。',
        'hard_exclude': '收入恢复弱、利润差、现金流不跟。',
        'soft_exclude': '子行业景气扰动但经营质量未坏的列观察。',
    },
    '交通运输': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '资产负债率', '货币资金'],
        'logic': '交通运输不少公司是重资产，现金流和负债比利润更关键。',
        'blowup_mechanism': '运价或客流走弱时，利润回落会逐步传导为现金流和负债压力。',
        'hard_exclude': '利润和现金流同步恶化且负债偏高。',
        'soft_exclude': '周期扰动但现金链仍稳的列观察。',
    },
    '公用事业': {
        'report_period': '四截面滚动',
        'focus_metrics': ['经营现金流', '资产负债率', '利润同比', '货币资金'],
        'logic': '公用事业的关键不是利润波动，而是现金创造能力和负债约束。',
        'blowup_mechanism': '成本和价格机制变化会先压缩回报，再逐步传导到现金流与负债。',
        'hard_exclude': '现金流持续弱、负债重、回报下降。',
        'soft_exclude': '利润扰动但现金创造仍稳的列观察。',
    },
    '环保': {
        'report_period': '四截面滚动',
        'focus_metrics': ['经营现金流', '应收账款', '资产负债率', '利润同比'],
        'logic': '环保本质也是项目回款型行业，现金流优先级高于利润。',
        'blowup_mechanism': '客户回款慢时，应收高企会先伤 CFO，再累积成财务压力。',
        'hard_exclude': '应收高、经营现金流差、负债重。',
        'soft_exclude': '利润弱但回款改善的列观察。',
    },
    '美容护理': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '美护品牌型公司要看渠道健康度和库存。',
        'blowup_mechanism': '需求走弱或渠道压货时，库存和现金流往往先转差。',
        'hard_exclude': '利润下滑、现金流变差、库存抬升。',
        'soft_exclude': '短期投放费用高但渠道健康的列观察。',
    },
    '轻工制造': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '轻工制造多受订单和出口链影响，要看连续截面。',
        'blowup_mechanism': '订单减弱后，利润、库存和现金流会逐步转差。',
        'hard_exclude': '利润差、现金流差、库存或应收恶化。',
        'soft_exclude': '单季出口扰动但后续改善的列观察。',
    },
    '纺织服饰': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '存货', '应收账款'],
        'logic': '纺织服饰季节性强，判断要看同比和连续趋势。',
        'blowup_mechanism': '需求转弱后，库存积压会先恶化现金流，再伤利润。',
        'hard_exclude': '库存压力显著、利润下滑、经营现金流转弱。',
        'soft_exclude': '季节波动造成的短期扰动列观察。',
    },
    '综合': {
        'report_period': '四截面滚动',
        'focus_metrics': ['利润同比', '经营现金流', '资产负债率', '货币资金'],
        'logic': '综合类公司必须结合主业理解，不适合机械统一判断。',
        'blowup_mechanism': '主业不清或资产质量差时，利润和现金流会一起走弱。',
        'hard_exclude': '主业不清、财务质量差、现金流弱。',
        'soft_exclude': '业务复杂但核心资产质量仍稳的列观察。',
    },
}

DEFAULT_RULE = {
    'report_period': '四截面滚动',
    'focus_metrics': ['利润同比', '经营现金流', '资产负债率', '应收/存货'],
    'logic': '优先看利润、现金流、资产负债表和营运质量是否同步恶化。',
    'blowup_mechanism': '经营压力通常先伤现金流和周转，再拖累利润和资产负债表。',
    'hard_exclude': '利润、现金流、资产负债表三项同时恶化。',
    'soft_exclude': '单项指标偏弱但整体经营质量未明显恶化。',
}


def to_float(v):
    if v is None or v == '':
        return None
    try:
        return float(v)
    except Exception:
        return None


def clamp(x, lo=0.0, hi=0.99):
    return max(lo, min(hi, x))


def avg(nums, default=None):
    vals = [x for x in nums if x is not None]
    if not vals:
        return default
    return sum(vals) / len(vals)


def classify_risk(score):
    if score >= 0.85:
        return '极高'
    if score >= 0.70:
        return '高'
    if score >= 0.52:
        return '中'
    return '低'


def factor_text(label, score):
    if score >= 0.85:
        level = '明显承压'
    elif score >= 0.70:
        level = '偏弱'
    elif score >= 0.52:
        level = '一般'
    else:
        level = '尚可'
    return f'{label}{level}'


def evaluate_stock(meta, periods):
    ordered_periods = sorted(periods.keys())
    if not ordered_periods:
        ordered_periods = AS_OF_PERIODS[:]
    score_periods = ordered_periods[-HISTORY_WINDOWS:] if len(ordered_periods) > HISTORY_WINDOWS else ordered_periods
    display_periods = [p for p in AS_OF_PERIODS if p in periods] or score_periods[-4:]

    rows = {p: periods.get(p) or {} for p in score_periods}

    profit_vals = [to_float(rows[p].get('q_dtprofit_yoy')) for p in score_periods]
    sales_vals = [to_float(rows[p].get('q_sales_yoy')) for p in score_periods]
    ocf_sales_vals = [to_float(rows[p].get('q_ocf_to_sales')) for p in score_periods]
    ocf_or_vals = [to_float(rows[p].get('ocf_to_or')) for p in score_periods]
    debt_vals = [to_float(rows[p].get('debt_to_assets')) for p in score_periods]
    current_vals = [to_float(rows[p].get('current_ratio')) for p in score_periods]
    quick_vals = [to_float(rows[p].get('quick_ratio')) for p in score_periods]
    inv_turn_vals = [to_float(rows[p].get('inv_turn')) for p in score_periods]
    ar_turn_vals = [to_float(rows[p].get('ar_turn')) for p in score_periods]
    money_vals = [to_float(rows[p].get('money_cap')) for p in score_periods]
    st_borr_vals = [to_float(rows[p].get('st_borr')) for p in score_periods]
    ar_vals = [to_float(rows[p].get('accounts_receiv')) for p in score_periods]
    inv_vals = [to_float(rows[p].get('inventories')) for p in score_periods]
    ncf_vals = [to_float(rows[p].get('n_cashflow_act')) for p in score_periods]

    latest_period = score_periods[-1]
    latest = rows.get(latest_period) or {}
    latest_profit = next((x for x in reversed(profit_vals) if x is not None), None)
    latest_sales = next((x for x in reversed(sales_vals) if x is not None), None)
    latest_ocf_sales = next((x for x in reversed(ocf_sales_vals) if x is not None), None)
    latest_ocf_or = next((x for x in reversed(ocf_or_vals) if x is not None), None)
    latest_debt = next((x for x in reversed(debt_vals) if x is not None), None)
    latest_current = next((x for x in reversed(current_vals) if x is not None), None)
    latest_quick = next((x for x in reversed(quick_vals) if x is not None), None)
    latest_inv_turn = next((x for x in reversed(inv_turn_vals) if x is not None), None)
    latest_ar_turn = next((x for x in reversed(ar_turn_vals) if x is not None), None)
    latest_money = next((x for x in reversed(money_vals) if x is not None), None)
    latest_st_borr = next((x for x in reversed(st_borr_vals) if x is not None), None)
    latest_ar = next((x for x in reversed(ar_vals) if x is not None), None)
    latest_inv = next((x for x in reversed(inv_vals) if x is not None), None)
    latest_ncf = next((x for x in reversed(ncf_vals) if x is not None), None)

    def worsening_streak(vals, worse_when='down'):
        clean = [x for x in vals if x is not None]
        if len(clean) < 2:
            return 0
        streak = 0
        for prev, cur in zip(clean[:-1], clean[1:]):
            bad = cur < prev if worse_when == 'down' else cur > prev
            if bad:
                streak += 1
            else:
                streak = 0
        return streak

    def count_bad(vals, predicate):
        return sum(1 for x in vals if x is not None and predicate(x))

    sales_down_streak = worsening_streak(sales_vals, 'down')
    ocf_sales_down_streak = worsening_streak(ocf_sales_vals, 'down')
    debt_up_streak = worsening_streak(debt_vals, 'up')
    current_down_streak = worsening_streak(current_vals, 'down')
    quick_down_streak = worsening_streak(quick_vals, 'down')
    ar_turn_down_streak = worsening_streak(ar_turn_vals, 'down')
    inv_turn_down_streak = worsening_streak(inv_turn_vals, 'down')

    neg_profit_count = count_bad(profit_vals, lambda x: x < 0)
    neg_ncf_count = count_bad(ncf_vals, lambda x: x < 0)
    weak_sales_count = count_bad(sales_vals, lambda x: x < 0)
    weak_ocf_sales_count = count_bad(ocf_sales_vals, lambda x: x < 0)

    # profit score
    profit_score = 0.30
    if latest_profit is not None:
        if latest_profit < -100:
            profit_score += 0.48
        elif latest_profit < -50:
            profit_score += 0.34
        elif latest_profit < 0:
            profit_score += 0.18
    if latest_sales is not None:
        if latest_sales < -20:
            profit_score += 0.12
        elif latest_sales < 0:
            profit_score += 0.06
    profit_score += min(0.16, neg_profit_count * 0.04)
    if sales_down_streak >= 2:
        profit_score += 0.08
    if weak_sales_count >= 6:
        profit_score += 0.06
    profit_score = clamp(profit_score)

    # cashflow score
    cashflow_score = 0.30
    if latest_ncf is not None and latest_ncf < 0:
        cashflow_score += 0.28
    if latest_ocf_sales is not None:
        if latest_ocf_sales < -20:
            cashflow_score += 0.22
        elif latest_ocf_sales < 0:
            cashflow_score += 0.12
    if latest_ocf_or is not None and latest_ocf_or < 0:
        cashflow_score += 0.12
    cashflow_score += min(0.16, neg_ncf_count * 0.04)
    if ocf_sales_down_streak >= 2:
        cashflow_score += 0.08
    if weak_ocf_sales_count >= 6:
        cashflow_score += 0.06
    cashflow_score = clamp(cashflow_score)

    # debt score
    debt_score = 0.26
    gap = None
    if latest_money is not None and latest_st_borr is not None:
        gap = latest_money - latest_st_borr
        if latest_money < latest_st_borr:
            debt_score += 0.30
        if latest_st_borr > 0:
            cover = latest_money / latest_st_borr if latest_st_borr else None
            if cover is not None and cover < 0.5:
                debt_score += 0.10
    if latest_debt is not None:
        if latest_debt > 80:
            debt_score += 0.18
        elif latest_debt > 65:
            debt_score += 0.10
    if latest_current is not None and latest_current < 1:
        debt_score += 0.08
    if latest_quick is not None and latest_quick < 0.8:
        debt_score += 0.08
    if debt_up_streak >= 2:
        debt_score += 0.06
    if current_down_streak >= 2:
        debt_score += 0.04
    if quick_down_streak >= 2:
        debt_score += 0.04
    debt_score = clamp(debt_score)

    # working capital score
    working_capital_score = 0.28
    if latest_ar is not None and latest_ar > 0:
        working_capital_score += 0.04
    if latest_inv is not None and latest_inv > 0:
        working_capital_score += 0.04
    if latest_ar_turn is not None and latest_ar_turn < 3:
        working_capital_score += 0.16
    if latest_inv_turn is not None and latest_inv_turn < 2:
        working_capital_score += 0.16
    if latest_ar_turn is not None and latest_ar_turn < 1.5:
        working_capital_score += 0.10
    if latest_inv_turn is not None and latest_inv_turn < 1:
        working_capital_score += 0.10
    if ar_turn_down_streak >= 2:
        working_capital_score += 0.06
    if inv_turn_down_streak >= 2:
        working_capital_score += 0.06
    working_capital_score = clamp(working_capital_score)

    # 科技/高研发行业修正：避免单纯按利润误伤
    industry1 = (meta.get('industry') or '未分类').strip() or '未分类'
    if industry1 in {'电子', '医药生物', '电力设备'}:
        if latest_profit is not None and latest_profit < 0 and latest_ncf is not None and latest_ncf > 0 and gap is not None and gap > 0:
            profit_score = max(0.30, profit_score - 0.10)
        if latest_profit is not None and latest_profit < -50 and latest_ncf is not None and latest_ncf < 0 and gap is not None and gap < 0:
            debt_score = clamp(debt_score + 0.05)
            working_capital_score = clamp(working_capital_score + 0.05)

    landmine_score = round((profit_score + cashflow_score + debt_score + working_capital_score) / 4, 4)
    risk_level = classify_risk(landmine_score)

    primary_reason = max(
        {
            'profit_score': profit_score,
            'cashflow_score': cashflow_score,
            'debt_score': debt_score,
            'working_capital_score': working_capital_score,
        }.items(),
        key=lambda kv: kv[1],
    )[0]

    reason_map = {
        'profit_score': '净利润同比断崖',
        'cashflow_score': '经营现金流为负',
        'debt_score': '短债覆盖严重失衡',
        'working_capital_score': '综合财务质量偏弱',
    }
    worst_metric = reason_map[primary_reason]

    why_parts = []
    if latest_profit is not None and latest_profit < 0:
        why_parts.append(f'净利润同比{latest_profit:.1f}%')
    if latest_ncf is not None and latest_ncf < 0:
        why_parts.append('经营现金流为负')
    if gap is not None and gap < 0:
        why_parts.append('货币资金低于短期借款')
    if latest_ar_turn is not None and latest_ar_turn < 3:
        why_parts.append('应收周转偏慢')
    if latest_inv_turn is not None and latest_inv_turn < 2:
        why_parts.append('存货周转偏慢')
    if not why_parts:
        why_parts = ['综合财务质量偏弱']
    why_dangerous = '；'.join(why_parts)

    industry_rule = RULEBOOK.get(industry1, DEFAULT_RULE)
    why_industry = industry_rule.get('logic', '该行业需同时观察利润、现金流、资产负债表和营运质量是否同步恶化。')

    exclude_flag = 1 if landmine_score >= 0.72 or (gap is not None and gap < 0 and latest_ncf is not None and latest_ncf < 0) else 0

    persistent_worsening_count = 0
    persistent_worsening_count += 1 if neg_profit_count >= 6 else 0
    persistent_worsening_count += 1 if neg_ncf_count >= 6 else 0
    persistent_worsening_count += 1 if sales_down_streak >= 2 else 0
    persistent_worsening_count += 1 if ocf_sales_down_streak >= 2 else 0
    persistent_worsening_count += 1 if debt_up_streak >= 2 else 0
    persistent_worsening_count += 1 if ar_turn_down_streak >= 2 else 0
    persistent_worsening_count += 1 if inv_turn_down_streak >= 2 else 0
    is_persistently_worsening = 1 if persistent_worsening_count >= 2 else 0

    worsening_signals = []
    if neg_profit_count >= 6:
        worsening_signals.append(f'近{len(score_periods)}期利润负增速出现{neg_profit_count}次')
    if neg_ncf_count >= 6:
        worsening_signals.append(f'近{len(score_periods)}期经营现金流为负出现{neg_ncf_count}次')
    if sales_down_streak >= 2:
        worsening_signals.append('营收增速连续走弱')
    if ocf_sales_down_streak >= 2:
        worsening_signals.append('经营现金流/收入连续走弱')
    if debt_up_streak >= 2:
        worsening_signals.append('资产负债率连续抬升')
    if ar_turn_down_streak >= 2:
        worsening_signals.append('应收周转连续变慢')
    if inv_turn_down_streak >= 2:
        worsening_signals.append('存货周转连续变慢')

    # ── 造假预警因子（勾稽异常检测）──────────────────────────────────────
    # 不下"造假结论"，只标记"报表勾稽对不上"的疑点，输出 high/mid/low 三档
    fraud_signals = []

    # 1. 利润好看但经营现金流持续差（利润/现金流背离）
    pos_profit_count = sum(1 for x in profit_vals if x is not None and x > 0)
    neg_ncf_count_fraud = sum(1 for x in ncf_vals if x is not None and x < 0)
    if pos_profit_count >= 2 and neg_ncf_count_fraud >= 2:
        fraud_signals.append('利润持续为正但经营现金流持续为负')

    # 2. 货币资金高但短债压力也高（钱是真的吗）
    if latest_money is not None and latest_st_borr is not None:
        if latest_money > 0 and latest_st_borr > 0:
            # 货币资金看起来充裕（>短债），但利息支出/融资成本也很高
            # 用 debt_to_assets 作为杠杆代理：高杠杆 + 高货币资金 = 疑点
            if latest_debt is not None and latest_debt > 65 and latest_money > latest_st_borr * 1.5:
                fraud_signals.append('高杠杆下货币资金异常充裕（疑似虚增）')

    # 3. 营收增长但应收和存货涨得更快
    latest_sales_val = latest_sales  # 营收同比%
    if latest_sales_val is not None and latest_sales_val > 5:
        # 应收周转变慢说明应收增速 > 营收增速
        if latest_ar_turn is not None and latest_ar_turn < 3:
            fraud_signals.append('营收增长但应收周转明显变慢（应收膨胀快于营收）')
        # 存货周转变慢说明存货增速 > 营收增速
        if latest_inv_turn is not None and latest_inv_turn < 2:
            fraud_signals.append('营收增长但存货周转明显变慢（存货膨胀快于营收）')

    # 4. 毛利率逆势稳定但现金流不跟（用 ocf_to_or 作为现金含量代理）
    # ocf_to_or < 0 且利润为正 = 利润有但现金没进来
    if latest_ocf_or is not None and latest_ocf_or < 0 and latest_profit is not None and latest_profit > 0:
        fraud_signals.append('利润为正但现金流/营收比为负（利润含金量低）')

    # 5. 应收/存货/其他科目异常膨胀（用周转率极低作为代理）
    if latest_ar_turn is not None and latest_ar_turn < 1.5:
        fraud_signals.append('应收账款周转极慢（账期异常拉长，疑似虚增应收）')
    if latest_inv_turn is not None and latest_inv_turn < 1.0:
        fraud_signals.append('存货周转极慢（库存异常积压，疑似虚增存货）')

    # 综合评级
    n_signals = len(fraud_signals)
    if n_signals >= 3:
        fraud_risk_level = 'high'
    elif n_signals >= 1:
        fraud_risk_level = 'mid'
    else:
        fraud_risk_level = 'low'

    fraud_risk_score = round(min(0.99, 0.20 + n_signals * 0.18), 4)
    # ─────────────────────────────────────────────────────────────────────

    def _period_scores(r):
        """给单个截面算四个子分（简化版，只用当期数据）"""
        qp = to_float(r.get('q_dtprofit_yoy'))
        qs_val = to_float(r.get('q_sales_yoy'))
        qn = to_float(r.get('n_cashflow_act'))
        qocf = to_float(r.get('q_ocf_to_sales'))
        qm = to_float(r.get('money_cap'))
        qst = to_float(r.get('st_borr'))
        qda = to_float(r.get('debt_to_assets'))
        qcr = to_float(r.get('current_ratio'))
        qat = to_float(r.get('ar_turn'))
        qit = to_float(r.get('inv_turn'))

        ps = 0.30
        if qp is not None:
            ps += 0.48 if qp < -100 else (0.34 if qp < -50 else (0.18 if qp < 0 else 0))
        if qs_val is not None:
            ps += 0.12 if qs_val < -20 else (0.06 if qs_val < 0 else 0)
        ps = clamp(ps)

        cs = 0.30
        if qn is not None and qn < 0:
            cs += 0.28
        if qocf is not None:
            cs += 0.22 if qocf < -20 else (0.12 if qocf < 0 else 0)
        cs = clamp(cs)

        ds = 0.26
        if qm is not None and qst is not None and qm < qst:
            ds += 0.30
        if qda is not None:
            ds += 0.18 if qda > 80 else (0.10 if qda > 65 else 0)
        if qcr is not None and qcr < 1:
            ds += 0.08
        ds = clamp(ds)

        ws = 0.28
        if qat is not None:
            ws += 0.16 if qat < 3 else 0
            ws += 0.10 if qat < 1.5 else 0
        if qit is not None:
            ws += 0.16 if qit < 2 else 0
            ws += 0.10 if qit < 1 else 0
        ws = clamp(ws)

        return round(ps, 3), round(cs, 3), round(ds, 3), round(ws, 3)

    history = []
    for p in display_periods:
        r = periods.get(p) or {}
        ps, cs, ds, ws = _period_scores(r)
        qp = to_float(r.get('q_dtprofit_yoy'))
        qn = to_float(r.get('n_cashflow_act'))
        qm = to_float(r.get('money_cap'))
        qs = to_float(r.get('st_borr'))
        parts = []
        if qp is not None:
            parts.append(f'净利润同比{qp:.1f}%')
        if qn is not None:
            parts.append('经营现金流为负' if qn < 0 else '经营现金流为正')
        if qm is not None and qs is not None:
            parts.append('货币资金低于短债' if qm < qs else '货币资金覆盖短债')
        history.append({
            'label': p,
            'text': '，'.join(parts) if parts else '暂无数据',
            'profit_score': ps,
            'cashflow_score': cs,
            'debt_score': ds,
            'working_capital_score': ws,
        })

    return {
        'ts_code': meta.get('ts_code'),
        'name': meta.get('name'),
        'industry1': industry1,
        'industry2': meta.get('market') or '',
        'risk_level': risk_level,
        'attribution_tag': worst_metric,
        'primary_reason': worst_metric,
        'worst_metric': worst_metric,
        'why_dangerous': why_dangerous,
        'why_industry': why_industry,
        'exclude_flag': exclude_flag,
        'is_persistently_worsening': is_persistently_worsening,
        'persistent_worsening_count': persistent_worsening_count,
        'worsening_signals': worsening_signals,
        'history_periods_used': score_periods,
        'history': history,
        'profit_score': round(profit_score, 4),
        'cashflow_score': round(cashflow_score, 4),
        'debt_score': round(debt_score, 4),
        'working_capital_score': round(working_capital_score, 4),
        'landmine_score': landmine_score,
        'fraud_risk_score': fraud_risk_score,
        'fraud_risk_level': fraud_risk_level,
        'fraud_signals': fraud_signals,
    }


def main():
    snap = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    stocks = []
    by_industry = defaultdict(list)

    for code, payload in snap.items():
        meta = payload.get('meta') or {'ts_code': code, 'name': code, 'industry': '未分类', 'market': ''}
        periods = payload.get('periods') or {}
        stock = evaluate_stock(meta, periods)
        stocks.append(stock)
        by_industry[stock['industry1']].append(stock)

    for _, items in by_industry.items():
        items.sort(key=lambda x: x['landmine_score'], reverse=True)
        n = len(items)
        for idx, item in enumerate(items):
            item['industry_percentile'] = round((n - idx) / n, 4)

    industries = []
    for industry_name, items in sorted(by_industry.items(), key=lambda kv: avg([x['landmine_score'] for x in kv[1]], 0), reverse=True):
        factor_means = {
            'profit_score': round(avg([x['profit_score'] for x in items], 0), 4),
            'cashflow_score': round(avg([x['cashflow_score'] for x in items], 0), 4),
            'debt_score': round(avg([x['debt_score'] for x in items], 0), 4),
            'working_capital_score': round(avg([x['working_capital_score'] for x in items], 0), 4),
        }
        primary_factor = max(factor_means, key=factor_means.get)
        rule = RULEBOOK.get(industry_name, DEFAULT_RULE)
        industries.append({
            'name': industry_name,
            'secondary_example': items[0]['industry2'] if items else '',
            'count': len(items),
            'exclude_count': sum(x['exclude_flag'] for x in items),
            'high_risk_count': sum(1 for x in items if x['landmine_score'] >= 0.70),
            'avg_risk': round(avg([x['landmine_score'] for x in items], 0), 4),
            'avgRisk': round(avg([x['landmine_score'] for x in items], 0), 4),
            'factor_means': factor_means,
            'factorMeans': factor_means,
            'primary_factor': primary_factor,
            'primary': primary_factor,
            'excludeCount': sum(x['exclude_flag'] for x in items),
            'highRiskCount': sum(1 for x in items if x['landmine_score'] >= 0.70),
            'rule': rule,
            'stocks': items[:50],
        })

    out = {
        'as_of': 'Tushare 全市场快照 / 四截面',
        'source_files': [str(SNAPSHOT)],
        'industries': industries,
        'stocks': sorted(stocks, key=lambda x: x['landmine_score'], reverse=True),
    }
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✅ wrote {OUTPUT} | industries={len(industries)} stocks={len(stocks)}')


if __name__ == '__main__':
    main()
