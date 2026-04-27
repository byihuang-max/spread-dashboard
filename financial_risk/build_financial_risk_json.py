#!/usr/bin/env python3
import csv
import json
import re
from pathlib import Path
from collections import defaultdict, Counter

BASE = Path.home() / 'Desktop' / 'gamt-dashboard' / 'timing-research'
RULEBOOK = Path.home() / 'Desktop' / 'industry_rulebook.csv'
DETAIL = Path.home() / 'Desktop' / 'stock_risk_detail.csv'
OUTPUT = BASE / 'data' / 'financial_risk_factor.json'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

RISK_MAP = {'极高': 0.95, '高': 0.78, '中': 0.58, '低': 0.32}

PRIMARY_FACTOR_MAP = {
    '净利润同比断崖': 'profit_score',
    '经营现金流为负': 'cashflow_score',
    '短债覆盖严重失衡': 'debt_score',
    '综合财务质量偏弱': 'working_capital_score',
}

TAG_FACTOR_HINTS = {
    '电子三杀': ('profit_score', 'cashflow_score', 'debt_score', 'working_capital_score'),
    '电子双杀': ('profit_score', 'cashflow_score', 'debt_score', 'working_capital_score'),
    '传媒双杀': ('profit_score', 'cashflow_score', 'working_capital_score'),
    '医药质量恶化': ('cashflow_score', 'profit_score', 'working_capital_score'),
    '化工双杀': ('cashflow_score', 'debt_score', 'profit_score'),
    '建筑双杀': ('cashflow_score', 'working_capital_score', 'profit_score', 'debt_score'),
    '机械双杀': ('profit_score', 'cashflow_score', 'working_capital_score'),
    '计算机双杀': ('cashflow_score', 'working_capital_score', 'profit_score'),
}

NUM_RE = re.compile(r'-?\d+(?:\.\d+)?')


def extract_numbers(text):
    if not text:
        return []
    return [float(x) for x in NUM_RE.findall(text.replace(',', ''))]


def score_row(row):
    risk = RISK_MAP.get(row['风险等级'].strip(), 0.5)
    profit = 0.32
    cashflow = 0.32
    debt = 0.28
    wc = 0.30

    worst = row['最差指标'].strip()
    primary = PRIMARY_FACTOR_MAP.get(worst)
    if primary == 'profit_score':
        profit = max(profit, 0.92 if row['风险等级'] == '极高' else 0.78)
    elif primary == 'cashflow_score':
        cashflow = max(cashflow, 0.9 if row['风险等级'] == '极高' else 0.76)
    elif primary == 'debt_score':
        debt = max(debt, 0.92 if row['风险等级'] == '极高' else 0.8)
    elif primary == 'working_capital_score':
        wc = max(wc, 0.82 if row['风险等级'] == '极高' else 0.7)

    why = row['为什么危险']
    nums = extract_numbers(why)
    if '净利润同比' in why:
        neg = [n for n in nums if n < 0]
        if neg:
            mag = abs(min(neg))
            profit = max(profit, min(0.98, 0.45 + mag / 1200))
    if '经营现金流为负' in why:
        cashflow = max(cashflow, 0.82 if row['风险等级'] == '高' else 0.94)
    if '货币资金低于短期借款' in why or '资金缺口明显' in why:
        debt = max(debt, 0.86 if row['风险等级'] == '高' else 0.96)
    if '应收' in why or '库存' in why or '综合财务质量偏弱' in why or '回款' in why:
        wc = max(wc, 0.68 if row['风险等级'] == '高' else 0.8)

    for hint in TAG_FACTOR_HINTS.get(row['归因主标签'].strip(), ()): 
        if hint == 'profit_score':
            profit = max(profit, 0.72)
        elif hint == 'cashflow_score':
            cashflow = max(cashflow, 0.72)
        elif hint == 'debt_score':
            debt = max(debt, 0.70)
        elif hint == 'working_capital_score':
            wc = max(wc, 0.64)

    vals = [profit, cashflow, debt, wc]
    landmine = round(sum(vals) / 4, 4)
    return {
        'profit_score': round(min(profit, 0.99), 4),
        'cashflow_score': round(min(cashflow, 0.99), 4),
        'debt_score': round(min(debt, 0.99), 4),
        'working_capital_score': round(min(wc, 0.99), 4),
        'landmine_score': round(max(landmine, risk - 0.02), 4),
    }


def build_history(row):
    return [
        {'label': '前年年报', 'text': row['前年年报表现']},
        {'label': '去年Q1', 'text': row['去年Q1表现']},
        {'label': '去年Q2', 'text': row['去年Q2表现']},
        {'label': '去年Q3', 'text': row['去年Q3表现']},
    ]


with RULEBOOK.open('r', encoding='utf-8-sig', newline='') as f:
    rules = list(csv.DictReader(f))

rule_map = {}
for r in rules:
    key = (r['一级行业'].strip(), r['二级行业'].strip())
    rule_map[key] = {
        'report_period': r['适用报告期'].strip(),
        'focus_metrics': [r['重点指标1'].strip(), r['重点指标2'].strip(), r['重点指标3'].strip(), r['重点指标4'].strip()],
        'logic': r['行业为什么看这些指标'].strip(),
        'blowup_mechanism': r['行业典型爆雷机制'].strip(),
        'hard_exclude': r['硬剔除条件'].strip(),
        'soft_exclude': r['软剔除条件'].strip(),
    }

stocks = []
by_industry = defaultdict(list)
with DETAIL.open('r', encoding='utf-8-sig', newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        scores = score_row(row)
        stock = {
            'ts_code': row['股票代码'].strip(),
            'name': row['股票简称'].strip(),
            'industry1': row['一级行业'].strip(),
            'industry2': row['二级行业'].strip(),
            'risk_level': row['风险等级'].strip(),
            'attribution_tag': row['归因主标签'].strip(),
            'worst_metric': row['最差指标'].strip(),
            'why_dangerous': row['为什么危险'].strip(),
            'why_industry': row['为什么这个行业要这么看'].strip(),
            'exclude_flag': 1 if row['是否建议剔除'].strip() == '1' else 0,
            'history': build_history(row),
            **scores,
        }
        stocks.append(stock)
        by_industry[stock['industry1']].append(stock)

for _, items in by_industry.items():
    items.sort(key=lambda x: x['landmine_score'], reverse=True)
    n = len(items)
    for idx, item in enumerate(items):
        item['industry_percentile'] = round((n - idx) / n, 4)

industries = []
for industry_name, items in sorted(by_industry.items(), key=lambda kv: sum(x['landmine_score'] for x in kv[1]) / len(kv[1]), reverse=True):
    secondary = Counter([x['industry2'] for x in items]).most_common(1)[0][0]
    rule = rule_map.get((industry_name, secondary), {})
    factor_means = {}
    for k in ['profit_score', 'cashflow_score', 'debt_score', 'working_capital_score']:
        factor_means[k] = round(sum(x[k] for x in items) / len(items), 4)
    primary = max(factor_means, key=factor_means.get)
    industries.append({
        'name': industry_name,
        'secondary_example': secondary,
        'count': len(items),
        'exclude_count': sum(x['exclude_flag'] for x in items),
        'high_risk_count': sum(1 for x in items if x['landmine_score'] >= 0.7),
        'avg_risk': round(sum(x['landmine_score'] for x in items) / len(items), 4),
        'factor_means': factor_means,
        'primary_factor': primary,
        'rule': rule,
    })

out = {
    'as_of': '2026Q1 / 桌面CSV导入',
    'source_files': [str(RULEBOOK), str(DETAIL)],
    'industries': industries,
    'stocks': stocks,
}

OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'✅ wrote {OUTPUT} | industries={len(industries)} stocks={len(stocks)}')
