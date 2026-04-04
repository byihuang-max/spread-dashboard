#!/usr/bin/env python3
"""
全市场财报风险快照生成器（Tushare 版）
- 第一步：stock_basic 拿全量股票池
- 第二步：fina_indicator 逐票拉四个报告期财务字段
- 支持断点续跑（已抓的票跳过）
- 输出：data/financial_risk_snapshot.json
"""
import json, time, requests
from pathlib import Path
from collections import defaultdict

TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
URL = 'https://api.tushare.pro'
ROOT = Path.home() / 'Desktop' / 'gamt-dashboard'
DATA = ROOT / 'data'
DATA.mkdir(parents=True, exist_ok=True)

POOL_FILE = DATA / 'stock_pool.json'
SNAPSHOT_FILE = DATA / 'financial_risk_snapshot.json'
RULEBOOK = Path.home() / 'Desktop' / 'industry_rulebook.csv'

# 四个报告期
PERIODS = ['20241231', '20250331', '20250630', '20250930']

# 行业映射单独做，第一版先抓全市场原始快照

FINA_FIELDS = 'ts_code,end_date,q_dtprofit_yoy,q_sales_yoy,q_ocf_to_sales,ocf_to_or,debt_to_assets,current_ratio,quick_ratio,inv_turn,ar_turn'
BS_FIELDS = 'ts_code,end_date,money_cap,st_borr,accounts_receiv,inventories'
CF_FIELDS = 'ts_code,end_date,n_cashflow_act'

def ts_call(api, params, fields=''):
    r = requests.post(URL, json={'api_name': api, 'token': TOKEN, 'params': params, 'fields': fields}, timeout=30)
    return r.json()

def get_pool():
    if POOL_FILE.exists():
        pool = json.loads(POOL_FILE.read_text())
        print(f'pool loaded from cache: {len(pool)}')
        return pool
    d = ts_call('stock_basic', {'exchange': '', 'list_status': 'L'}, 'ts_code,name,industry,market')
    items = d['data']['items']
    fields = d['data']['fields']
    pool = [dict(zip(fields, row)) for row in items]
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2))
    print(f'pool fetched: {len(pool)}')
    return pool

def load_snapshot():
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text())
    return {}

def save_snapshot(snap):
    SNAPSHOT_FILE.write_text(json.dumps(snap, ensure_ascii=False, indent=2))

def fetch_fina(ts_code):
    """拉单票所有报告期的财务指标，合并三张表"""
    result = {}
    for period in PERIODS:
        row = {}
        for api, fields in [
            ('fina_indicator', FINA_FIELDS),
            ('balancesheet', BS_FIELDS),
            ('cashflow', CF_FIELDS),
        ]:
            d = ts_call(api, {'ts_code': ts_code, 'period': period}, fields)
            if d.get('code') == 0 and d['data'] and d['data']['items']:
                flds = d['data']['fields']
                r = d['data']['items'][0]
                row.update(dict(zip(flds, r)))
            time.sleep(0.12)
        result[period] = row if row else None
    return result

def main():
    pool = get_pool()
    targets = pool
    print(f'targets: {len(targets)} / {len(pool)}')

    snap = load_snapshot()
    done = set(snap.keys())
    todo = [s for s in targets if s['ts_code'] not in done]
    print(f'already done: {len(done)}, todo: {len(todo)}')

    max_stocks = int(__import__('os').environ.get('MAX_STOCKS', '0') or '0')
    if max_stocks:
        todo = todo[:max_stocks]
    for i, stock in enumerate(todo):
        code = stock['ts_code']
        try:
            data = fetch_fina(code)
            snap[code] = {'meta': stock, 'periods': data}
            if (i + 1) % 20 == 0:
                save_snapshot(snap)
                print(f'  [{i+1}/{len(todo)}] saved checkpoint')
        except Exception as e:
            print(f'  ERR {code}: {e}')
            time.sleep(2)

    save_snapshot(snap)
    print(f'✅ done. total={len(snap)} stocks in snapshot')

if __name__ == '__main__':
    main()
