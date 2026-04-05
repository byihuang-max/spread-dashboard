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

stock_map = {s['ts_code']: s for s in FACTOR}

# 总体验证总览表
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

# 恶化链条验证表：重逻辑，不做机械统计
# 说明：这里先做“行业规则 + 当前样本观察”的底表，供第四板块使用
industry_rows = []
all_rows = VERIFY_HIT + VERIFY_MISS
by_industry = {}
for r in all_rows:
    by_industry.setdefault(r['industry'] or '未分类', []).append(r)

for industry, rule in RULES.items():
    rows = by_industry.get(industry, [])
    hit_rows = [r for r in rows if r['exclude_flag'] == '1']
    miss_rows = [r for r in rows if r['exclude_flag'] != '1']
    bad_counter = Counter()
    for r in rows:
        for sig in [x for x in (r.get('bad_signals') or '').split('；') if x]:
            bad_counter[sig] += 1
    top_signals = '；'.join([k for k, _ in bad_counter.most_common(3)])
    sample = rows[:3]
    sample_text = '；'.join([f"{x['ts_code']} {x['name']}" for x in sample])
    if rows:
        verify_result = '已观察到样本验证'
    else:
        verify_result = '待更多样本'
    industry_rows.append({
        '行业': industry,
        '行业类型': rule['type'],
        '原定义核心风险': rule['core_risk'],
        '原定义差的标准': '；'.join(rule['bad_when']),
        '原定义变得更差标准': '；'.join(rule['worse_when']),
        '本期财报验证结果': verify_result,
        '本期主要被验证的坏信号': top_signals,
        '命中样本数': len(hit_rows),
        '漏判样本数': len(miss_rows),
        '典型样本': sample_text,
        '不应误判情形': '；'.join(rule.get('not_worse_if', [])),
        '备注': rule.get('_warning', '')
    })

with open(OUT_DIR / 'deterioration_chain_validation.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(industry_rows[0].keys()))
    w.writeheader()
    w.writerows(industry_rows)

# 样本清单：命中 / 漏判 / 争议
sample_rows = []
for r in VERIFY_HIT:
    sample_rows.append({
        '样本类型': '命中',
        '股票代码': r['ts_code'],
        '股票简称': r['name'],
        '行业': r['industry'],
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
        '行业': r['industry'],
        '是否在剔除名单': '否',
        '新财报披露日': r['actual_date'],
        '恶化链条是否验证': '已验证',
        '坏信号数': r['bad_signal_count'],
        '坏信号明细': r['bad_signals'],
        '原始主因': r.get('primary_reason', ''),
    })

# 争议样本：先用金融类 + 高研发类里出现坏信号但可能是误判的样本
controversy_industries = {'证券', '银行', '多元金融', '半导体', '生物制药', '化学制药', '航空'}
for r in VERIFY_ALL:
    if r['industry'] in controversy_industries and int(r['bad_signal_count'] or 0) >= 2:
        sample_rows.append({
            '样本类型': '争议',
            '股票代码': r['ts_code'],
            '股票简称': r['name'],
            '行业': r['industry'],
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

print('done')
print(OUT_DIR / 'validation_summary.csv')
print(OUT_DIR / 'deterioration_chain_validation.csv')
print(OUT_DIR / 'validation_samples.csv')
