#!/usr/bin/env python3
"""
用 iFinD MCP 批量生成财报风险页面底层数据。

目标：先把“全量数据链路”跑通，不再依赖手工 detail CSV。
当前版本采取两阶段思路：
1) 维护一份股票池（先从现有 JSON / CSV / 手工扩展承接，后续可替换成稳定全A股票清单）
2) 分批调用 iFinD get_stock_financials 拉财务字段，生成标准化快照

说明：
- iFinD 的 search_stocks 不适合一次性返回全A股，会因结果过大被拒。
- 因此这里先重点解决“财务字段批量抓取与标准化”这一层。
"""

from __future__ import annotations
import csv
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict

ROOT = Path.home() / 'Desktop' / 'gamt-dashboard'
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

IFIND_JS = Path.home() / '.openclaw' / 'extensions' / 'ifind-finance-data' / 'call-node.js'
POOL_JSON = DATA_DIR / 'financial_risk_stock_pool.json'
SNAPSHOT_JSON = DATA_DIR / 'financial_risk_ifind_snapshot.json'
RULEBOOK = Path.home() / 'Desktop' / 'industry_rulebook.csv'
LEGACY_DETAIL = Path.home() / 'Desktop' / 'stock_risk_detail.csv'
LEGACY_JSON = ROOT / 'data' / 'financial_risk_factor.json'

PERIODS = ['20241231', '20250331', '20250630', '20250930']
FIELDS = ['净利润同比', '经营现金流', '货币资金', '短期借款', '应收账款', '存货']
BATCH_SIZE = 8
SLEEP_SEC = 1.0
MAX_BATCHES = 2  # 调试时可改成整数
ONLY_PERIODS = ['20250930']  # 调试时可改成 ['20250930']


def run_node(js: str) -> dict:
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    txt = p.stdout.strip()
    return json.loads(txt)


def ifind_call(server_type: str, tool_name: str, params: dict) -> dict:
    js = f"""
const {{ call }} = require({json.dumps(str(IFIND_JS))});
(async () => {{
  const res = await call({json.dumps(server_type)}, {json.dumps(tool_name)}, {json.dumps(params, ensure_ascii=False)});
  console.log(JSON.stringify(res));
}})().catch(err => {{ console.error(String(err&&err.stack||err)); process.exit(1); }});
"""
    return run_node(js)


def parse_answer_text(res: dict) -> str:
    try:
        content = res['data']['result']['content'][0]['text']
        outer = json.loads(content)
        data = outer.get('data', {})
        return data.get('answer') or data.get('result') or ''
    except Exception:
        return ''


def load_pool() -> list[dict]:
    if POOL_JSON.exists():
        return json.loads(POOL_JSON.read_text())

    pool = []
    seen = set()

    if LEGACY_JSON.exists():
        obj = json.loads(LEGACY_JSON.read_text())
        for s in obj.get('stocks', []):
            key = s['ts_code']
            if key in seen:
                continue
            seen.add(key)
            pool.append({
                'ts_code': s['ts_code'],
                'name': s['name'],
                'industry1': s.get('industry1', ''),
                'industry2': s.get('industry2', ''),
            })

    elif LEGACY_DETAIL.exists():
        with LEGACY_DETAIL.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row['股票代码'].strip()
                if key in seen:
                    continue
                seen.add(key)
                pool.append({
                    'ts_code': key,
                    'name': row['股票简称'].strip(),
                    'industry1': row['一级行业'].strip(),
                    'industry2': row['二级行业'].strip(),
                })

    POOL_JSON.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')
    return pool


def split_batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i+size]


def parse_cn_num(text: str):
    if text is None:
        return None
    s = str(text).strip().replace(',', '').replace('\t', '')
    if not s or s in {'--', '-', 'nan', 'None'}:
        return None
    mult = 1.0
    if s.endswith('亿'):
        mult = 1e8
        s = s[:-1]
    elif s.endswith('万'):
        mult = 1e4
        s = s[:-1]
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    if not m:
        return None
    return float(m.group()) * mult


def parse_markdown_table(answer: str):
    lines = [x.strip() for x in answer.splitlines() if x.strip()]
    table = []
    for line in lines:
        if not line.startswith('|'):
            continue
        cols = [c.strip() for c in line.strip('|').split('|')]
        table.append(cols)
    if len(table) < 3:
        return []
    header = table[0]
    rows = []
    for cols in table[2:]:
        if len(cols) < len(header):
            cols += [''] * (len(header)-len(cols))
        rows.append(dict(zip(header, cols)))
    return rows


def canonicalize_row(row: dict) -> dict:
    out = {'ts_code': row.get('证券代码', ''), 'name': row.get('证券简称', ''), 'date': row.get('日期', '')}
    for k, v in row.items():
        if '净利润' in k and '同比' in k:
            out['profit_yoy'] = parse_cn_num(v)
        elif '经营活动产生的现金流量净额' in k:
            out['ocf'] = parse_cn_num(v)
        elif k.startswith('货币资金（') or k == '货币资金（单位：元；报表类型：合并报表）' or k == '货币资金':
            out['cash'] = parse_cn_num(v)
        elif '短期借款' in k:
            out['short_debt'] = parse_cn_num(v)
        elif '应收账款' in k:
            out['accounts_receivable'] = parse_cn_num(v)
        elif k.startswith('存货（') or k == '存货':
            out['inventory'] = parse_cn_num(v)
    return out


def fetch_period_batch(batch: list[dict], period: str) -> list[dict]:
    names = '、'.join([x['name'] for x in batch])
    q = f'{names}在{period}的净利润同比、经营现金流、货币资金、短期借款、应收账款、存货'
    res = ifind_call('stock', 'get_stock_financials', {'query': q})
    answer = parse_answer_text(res)
    rows = parse_markdown_table(answer)
    return [canonicalize_row(r) for r in rows]


def load_rulebook():
    rules = {}
    with RULEBOOK.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rules[r['一级行业'].strip()] = {
                'secondary_example': r['二级行业'].strip(),
                'focus_metrics': [r['重点指标1'].strip(), r['重点指标2'].strip(), r['重点指标3'].strip(), r['重点指标4'].strip()],
                'logic': r['行业为什么看这些指标'].strip(),
                'blowup_mechanism': r['行业典型爆雷机制'].strip(),
                'hard_exclude': r['硬剔除条件'].strip(),
                'soft_exclude': r['软剔除条件'].strip(),
            }
    return rules


def main():
    pool = load_pool()
    print(f'pool={len(pool)}')
    snapshots = defaultdict(dict)
    meta = {x['ts_code']: x for x in pool}

    periods = ONLY_PERIODS or PERIODS
    for period in periods:
        print(f'=== period {period} ===')
        for idx, batch in enumerate(split_batches(pool, BATCH_SIZE), start=1):
            if MAX_BATCHES and idx > MAX_BATCHES:
                break
            try:
                rows = fetch_period_batch(batch, period)
                got = {r['ts_code']: r for r in rows if r.get('ts_code')}
                for item in batch:
                    code = item['ts_code']
                    snapshots[code][period] = got.get(code, {'ts_code': code, 'name': item['name'], 'date': period})
                print(f'  batch {idx}: ok {len(rows)}/{len(batch)}')
            except Exception as e:
                print(f'  batch {idx}: ERR {e}')
                for item in batch:
                    code = item['ts_code']
                    snapshots[code][period] = {'ts_code': code, 'name': item['name'], 'date': period, 'error': str(e)}
            time.sleep(SLEEP_SEC)

    out = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'periods': PERIODS,
        'fields': FIELDS,
        'pool_size': len(pool),
        'source': 'iFinD MCP get_stock_financials',
        'stocks': []
    }
    for code, per in snapshots.items():
        item = dict(meta.get(code, {}))
        item['period_data'] = per
        out['stocks'].append(item)

    SNAPSHOT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✅ wrote {SNAPSHOT_JSON}')


if __name__ == '__main__':
    main()
