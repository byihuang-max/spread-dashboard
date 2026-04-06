import json, csv
from pathlib import Path
from collections import Counter

BASE = Path('/Users/apple/Desktop/gamt-dashboard')
RULES = json.load(open(BASE / 'timing-research/industry_deterioration_rules.json'))['industries']
FACTOR = json.load(open(BASE / 'data/financial_risk_factor.json'))['stocks']
VERIFY_ALL = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_all_2025.csv', encoding='utf-8-sig')))
VERIFY_HIT = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_hit_2025.csv', encoding='utf-8-sig')))
VERIFY_MISS = list(csv.DictReader(open(Path.home() / 'Desktop/annual_verify_miss_bad2_2025.csv', encoding='utf-8-sig')))

OUT_DIR = BASE / 'data/financial_validation'
OUT_DIR.mkdir(parents=True, exist_ok=True)

PRIMARY_ALIAS = {
    '建筑工程': '建筑装饰',
    '环境保护': '环保',
    '普钢': '钢铁',
    '软件服务': '计算机',
    '电气设备': '电力设备',
    '半导体': '电子',
    '元器件': '电子',
    '生物制药': '医药生物',
    '化学制药': '医药生物',
    '食品': '食品饮料',
    '证券': '非银金融',
}

PRIMARY_INDUSTRIES = [
    '银行', '非银金融', '房地产', '建筑材料', '建筑装饰', '钢铁', '有色金属', '基础化工', '石油石化', '煤炭',
    '电力设备', '机械设备', '国防军工', '汽车', '家用电器', '电子', '计算机', '通信', '传媒', '医药生物',
    '食品饮料', '农林牧渔', '商贸零售', '社会服务', '交通运输', '公用事业', '环保', '美容护理', '轻工制造',
    '纺织服饰', '综合'
]

SPECIAL_INDUSTRIES = ['半导体', '元器件', '软件服务', '证券', '银行', '生物制药', '航空', '化工原料']


def normalize_industry(name: str) -> str:
    name = (name or '未分类').strip() or '未分类'
    return PRIMARY_ALIAS.get(name, name)


def top_signals(rows):
    bad_counter = Counter()
    for r in rows:
        for sig in [x for x in (r.get('bad_signals') or '').split('；') if x]:
            bad_counter[sig] += 1
    return '；'.join([k for k, _ in bad_counter.most_common(3)])


def sample_text(rows):
    return '；'.join([f"{x['ts_code']} {x['name']}" for x in rows[:3]])


stock_map = {s['ts_code']: s for s in FACTOR}
all_rows = VERIFY_HIT + VERIFY_MISS

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

by_primary = {}
by_raw = {}
for r in all_rows:
    raw = (r.get('industry') or '未分类').strip() or '未分类'
    primary = normalize_industry(raw)
    by_primary.setdefault(primary, []).append(r)
    by_raw.setdefault(raw, []).append(r)

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

sample_rows = []
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
for r in VERIFY_ALL:
    raw = (r.get('industry') or '').strip()
    primary = normalize_industry(raw)
    if (raw in SPECIAL_INDUSTRIES or primary in {'非银金融', '银行', '电子', '医药生物', '航空', '基础化工'}) and int(r['bad_signal_count'] or 0) >= 2:
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

view = {
    'summary': summary,
    'primary_industries': industry_rows,
    'special_industries': special_rows,
    'samples': sample_rows,
}
(BASE / 'data/financial_validation/validation_view.json').write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding='utf-8')

print('done')
print(OUT_DIR / 'validation_summary.csv')
print(OUT_DIR / 'deterioration_chain_validation.csv')
print(OUT_DIR / 'special_industry_validation.csv')
print(OUT_DIR / 'validation_samples.csv')
print(BASE / 'data/financial_validation/validation_view.json')
