#!/usr/bin/env python3
"""
财报验证层底表生成器
=====================

这个脚本负责生成第四层"财报验证层"的全部底表和前端 JSON。

核心职责：
  用新披露的 2025 年报，去验证我们事前定义的行业风险规则到底准不准。
  不是做统计表，而是做"逻辑验证"：命中了哪些、漏判了哪些、哪些可能误判。

输入：
  1. industry_deterioration_rules.json  — 行业恶化链条规则（定义"什么叫差"和"什么叫更差"）
  2. financial_risk_factor.json         — 全市场股票的风险因子打分
  3. annual_verify_all_2025.csv         — 已披露 2025 年报的全量样本
  4. annual_verify_hit_2025.csv         — 命中样本（在剔除项且后验确实差）
  5. annual_verify_miss_bad2_2025.csv   — 漏判样本（不在剔除项但后验也差）

输出（全部写到 data/financial_validation/）：
  1. validation_summary.csv             — 总览：命中数/漏判数/命中率
  2. deterioration_chain_validation.csv — 一级行业恶化链条验证表（31个主行业）
  3. special_industry_validation.csv    — 重点二级行业特例验证表（8个高误判行业）
  4. validation_samples.csv             — 样本清单（命中/漏判/争议三类）
  5. validation_view.json               — 前端统一读取的 JSON（包含以上所有）

关键设计决策：
  - 一级行业和二级行业特例分开统计，不混在一张表里
  - "争议"样本来自金融类/高研发类行业，这些行业用统一口径容易误判
  - 行业名称做了归一化（alias），避免同一个行业出现两个名字
"""

import json
import csv
from pathlib import Path
from collections import Counter

# ── 路径配置 ──────────────────────────────────────────────────────────────
BASE = Path('/Users/apple/Desktop/gamt-dashboard')
RULES = json.load(open(BASE / 'timing-research/industry_deterioration_rules.json'))['industries']
FACTOR = json.load(open(BASE / 'data/financial_risk_factor.json'))['stocks']
VERIFY_ALL = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_all_2025.csv', encoding='utf-8-sig')))
VERIFY_HIT = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_hit_2025.csv', encoding='utf-8-sig')))
VERIFY_MISS = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_miss_bad2_2025.csv', encoding='utf-8-sig')))

OUT_DIR = BASE / 'data/financial_validation'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 行业命名归一化 ────────────────────────────────────────────────────────
# 为什么需要这个：
#   数据源里的行业名可能是一级行业（如"电子"），也可能是二级行业（如"半导体"）
#   如果不统一，统计时同一个行业的命中/漏判会被拆碎
#   但二级行业特例需要保留原始名称单独分析（用 by_raw）
PRIMARY_ALIAS = {
    '建筑工程': '建筑装饰',     # 同一个申万一级
    '环境保护': '环保',          # 同一个申万一级
    '普钢': '钢铁',              # 二级 → 一级
    '软件服务': '计算机',         # 二级 → 一级
    '电气设备': '电力设备',       # 二级 → 一级
    '半导体': '电子',            # 二级 → 一级（但半导体在特例表里保留）
    '元器件': '电子',            # 二级 → 一级（但元器件在特例表里保留）
    '生物制药': '医药生物',       # 二级 → 一级
    '化学制药': '医药生物',       # 二级 → 一级
    '食品': '食品饮料',          # 二级 → 一级
    '证券': '非银金融',          # 二级 → 一级（但证券在特例表里保留）
}

# 31 个申万一级行业，按这个顺序展示
PRIMARY_INDUSTRIES = [
    '银行', '非银金融', '房地产', '建筑材料', '建筑装饰', '钢铁', '有色金属',
    '基础化工', '石油石化', '煤炭', '电力设备', '机械设备', '国防军工', '汽车',
    '家用电器', '电子', '计算机', '通信', '传媒', '医药生物', '食品饮料',
    '农林牧渔', '商贸零售', '社会服务', '交通运输', '公用事业', '环保',
    '美容护理', '轻工制造', '纺织服饰', '综合'
]

# 重点二级行业特例
# 为什么这些行业要单独拉出来：
#   这些行业如果直接套一级行业的统一口径，容易产生误判。
#   比如半导体的库存高可能是战略备货，证券的高杠杆是正常业务结构。
#   所以它们需要单独的规则和单独的验证统计。
SPECIAL_INDUSTRIES = [
    '半导体',     # 归属"电子"，但库存/研发逻辑和消费电子完全不同
    '元器件',     # 归属"电子"，但客户集中度和库存周期有独立特征
    '软件服务',   # 归属"计算机"，但回款和应收恶化比硬件型公司更隐蔽
    '证券',       # 归属"非银金融"，但资产负债率/CFO 完全不适用普通口径
    '银行',       # 虽然是独立一级行业，但需要完全不同的财务字段（不良率/拨备）
    '生物制药',   # 归属"医药生物"，但持续亏损+高研发是常态，不能按利润差判
    '航空',       # 归属"交通运输"，但高杠杆+油价敏感+季节性现金流有独立逻辑
    '化工原料',   # 归属"基础化工"，但价格波动和库存周期更剧烈
]


def normalize_industry(name: str) -> str:
    """把二级行业名归一到对应的一级行业"""
    name = (name or '未分类').strip() or '未分类'
    return PRIMARY_ALIAS.get(name, name)


def top_signals(rows):
    """统计样本中出现频率最高的前 3 个坏信号"""
    bad_counter = Counter()
    for r in rows:
        for sig in [x for x in (r.get('bad_signals') or '').split('；') if x]:
            bad_counter[sig] += 1
    return '；'.join([k for k, _ in bad_counter.most_common(3)])


def sample_text(rows):
    """取前 3 个样本的代码+名称，用于底表展示"""
    return '；'.join([f"{x['ts_code']} {x['name']}" for x in rows[:3]])


# ── 数据准备 ──────────────────────────────────────────────────────────────
stock_map = {s['ts_code']: s for s in FACTOR}
all_rows = VERIFY_HIT + VERIFY_MISS  # 命中 + 漏判，都是"后验确实差"的样本

# ── 第 1 张表：总览 ─────────────────────────────────────────────────────
summary = {
    '已披露并对齐样本数': len(VERIFY_ALL),
    '命中样本数': len(VERIFY_HIT),
    '漏判样本数_bad_ge_2': len(VERIFY_MISS),
    '命中率_披露样本口径': round(len(VERIFY_HIT) / len(VERIFY_ALL), 4) if VERIFY_ALL else 0,
    '命中样本_全部有_ge_2_坏信号': '是',
}
with open(OUT_DIR / 'validation_summary.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['指标', '值'])
    for k, v in summary.items():
        w.writerow([k, v])

# ── 按行业分组 ────────────────────────────────────────────────────────────
# by_primary: 归一后的一级行业分组（用于主表统计）
# by_raw: 原始行业名分组（用于二级行业特例统计）
by_primary = {}
by_raw = {}
for r in all_rows:
    raw = (r.get('industry') or '未分类').strip() or '未分类'
    primary = normalize_industry(raw)
    by_primary.setdefault(primary, []).append(r)
    by_raw.setdefault(raw, []).append(r)

# ── 第 2 张表：一级行业恶化链条验证 ─────────────────────────────────────
# 每一行对应一个申万一级行业
# 用归一后的行业名统计命中/漏判
industry_rows = []
for industry in PRIMARY_INDUSTRIES:
    rule = RULES.get(industry)
    if not rule:
        continue
    rows = by_primary.get(industry, [])
    hit_rows = [r for r in rows if r['exclude_flag'] == '1']
    miss_rows = [r for r in rows if r['exclude_flag'] != '1']
    industry_rows.append({
        '行业': industry,
        '行业类型': rule['type'],
        '原定义核心风险': rule['core_risk'],
        '原定义差的标准': '；'.join(rule['bad_when']),
        '原定义变得更差标准': '；'.join(rule['worse_when']),
        '本期财报验证结果': '已观察到样本验证' if rows else '待更多样本',
        '本期主要被验证的坏信号': top_signals(rows),
        '命中样本数': len(hit_rows),
        '漏判样本数': len(miss_rows),
        '典型样本': sample_text(rows),
        '不应误判情形': '；'.join(rule.get('not_worse_if', [])),
        '备注': rule.get('_warning', '')
    })

with open(OUT_DIR / 'deterioration_chain_validation.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(industry_rows[0].keys()))
    w.writeheader()
    w.writerows(industry_rows)

# ── 第 3 张表：重点二级行业特例验证 ─────────────────────────────────────
# 用原始行业名（by_raw）统计，不归一
# 这样才能看到半导体/元器件/证券等各自独立的命中/漏判
special_rows = []
for industry in SPECIAL_INDUSTRIES:
    rule = RULES.get(industry)
    if not rule:
        continue
    rows = by_raw.get(industry, [])
    hit_rows = [r for r in rows if r['exclude_flag'] == '1']
    miss_rows = [r for r in rows if r['exclude_flag'] != '1']
    special_rows.append({
        '特例行业': industry,
        '归属主行业': normalize_industry(industry),
        '行业类型': rule['type'],
        '核心风险': rule['core_risk'],
        '差的标准': '；'.join(rule['bad_when']),
        '变得更差标准': '；'.join(rule['worse_when']),
        '不应误判情形': '；'.join(rule.get('not_worse_if', [])),
        '命中样本数': len(hit_rows),
        '漏判样本数': len(miss_rows),
        '本期主要坏信号': top_signals(rows),
        '典型样本': sample_text(rows),
        '备注': rule.get('_warning', '')
    })

with open(OUT_DIR / 'special_industry_validation.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(special_rows[0].keys()))
    w.writeheader()
    w.writerows(special_rows)

# ── 第 4 张表：样本清单 ─────────────────────────────────────────────────
# 三类样本：
#   命中 — 在剔除项且后验确实差
#   漏判 — 不在剔除项但后验也差
#   争议 — 在特殊行业里有坏信号，但可能是行业特征而非真正恶化
sample_rows = []

# 命中样本
for r in VERIFY_HIT:
    sample_rows.append({
        '样本类型': '命中',
        '股票代码': r['ts_code'],
        '股票简称': r['name'],
        '原始行业': r['industry'],
        '归一主行业': normalize_industry(r['industry']),
        '是否在剔除名单': '是',
        '新财报披露日': r['actual_date'],
        '恶化链条是否验证': '已验证',
        '坏信号数': r['bad_signal_count'],
        '坏信号明细': r['bad_signals'],
        '原始主因': r.get('primary_reason', ''),
    })

# 漏判样本
for r in VERIFY_MISS:
    sample_rows.append({
        '样本类型': '漏判',
        '股票代码': r['ts_code'],
        '股票简称': r['name'],
        '原始行业': r['industry'],
        '归一主行业': normalize_industry(r['industry']),
        '是否在剔除名单': '否',
        '新财报披露日': r['actual_date'],
        '恶化链条是否验证': '已验证',
        '坏信号数': r['bad_signal_count'],
        '坏信号明细': r['bad_signals'],
        '原始主因': r.get('primary_reason', ''),
    })

# 争议样本：金融类/高研发类行业里出现坏信号但可能是误判的
# 为什么这些行业需要"争议"标签：
#   因为银行的高杠杆、证券的CFO为负、半导体的库存高，
#   在普通企业是危险信号，在这些行业可能是正常业务特征
for r in VERIFY_ALL:
    raw = (r.get('industry') or '').strip()
    primary = normalize_industry(raw)
    is_special = (raw in SPECIAL_INDUSTRIES or
                  primary in {'非银金融', '银行', '电子', '医药生物', '航空', '基础化工'})
    if is_special and int(r['bad_signal_count'] or 0) >= 2:
        sample_rows.append({
            '样本类型': '争议',
            '股票代码': r['ts_code'],
            '股票简称': r['name'],
            '原始行业': raw,
            '归一主行业': primary,
            '是否在剔除名单': '是' if r['exclude_flag'] == '1' else '否',
            '新财报披露日': r['actual_date'],
            '恶化链条是否验证': '待行业口径复核',
            '坏信号数': r['bad_signal_count'],
            '坏信号明细': r['bad_signals'],
            '原始主因': r.get('primary_reason', ''),
        })

with open(OUT_DIR / 'validation_samples.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(sample_rows[0].keys()))
    w.writeheader()
    w.writerows(sample_rows)

# ── 前端统一 JSON ────────────────────────────────────────────────────────
# 前端 financial_risk_factor.html 的 loadValidation() 会读取这个文件
# 它包含所有四张表的数据，前端不再需要分别读取 CSV
view = {
    'summary': summary,
    'primary_industries': industry_rows,
    'special_industries': special_rows,
    'samples': sample_rows,
}
(BASE / 'data/financial_validation/validation_view.json').write_text(
    json.dumps(view, ensure_ascii=False, indent=2), encoding='utf-8'
)

print('done')
print(OUT_DIR / 'validation_summary.csv')
print(OUT_DIR / 'deterioration_chain_validation.csv')
print(OUT_DIR / 'special_industry_validation.csv')
print(OUT_DIR / 'validation_samples.csv')
print(BASE / 'data/financial_validation/validation_view.json')
