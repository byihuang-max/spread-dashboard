#!/usr/bin/env python3
"""申万二级行业→ETF映射表 月度增量更新

用法: python3 update_etf_map.py [--apply]
  默认只输出 diff（新增/退市），加 --apply 自动合并到 industry_l2_etf_map.json
  建议每月初手动跑一次
"""
import requests, json, os, sys, time
from datetime import datetime

TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
URL = 'https://api.tushare.pro'
BASE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(BASE, 'industry_l2_etf_map.json')


def tushare_call(api_name, params, fields=''):
    resp = requests.post(URL, json={
        'api_name': api_name, 'token': TOKEN,
        'params': params, 'fields': fields
    }, timeout=30, proxies={'http': None, 'https': None})
    data = resp.json()
    if data.get('code') != 0:
        print(f'ERROR: {api_name} → {data.get("msg")}')
        return []
    cols = data['data']['fields']
    return [dict(zip(cols, row)) for row in data['data']['items']]


def fetch_etf_list():
    """拉取全部场内 ETF 基金列表"""
    rows = tushare_call('fund_basic', {
        'market': 'E',  # 场内
        'status': 'L',  # 上市中
    }, 'ts_code,name,fund_type,found_date,due_date,benchmark')
    # 只保留 ETF
    etfs = [r for r in rows if 'ETF' in (r.get('name') or '')]
    print(f'拉取到 {len(etfs)} 只场内 ETF')
    return etfs


def load_current_map():
    with open(MAP_PATH) as f:
        return json.load(f)


def get_all_mapped_codes(mapping):
    """提取映射表中所有已有的 ETF 代码"""
    codes = set()
    for etfs in mapping.values():
        for e in etfs:
            codes.add(e['code'])
    return codes


def main():
    apply_mode = '--apply' in sys.argv

    print(f'=== ETF 映射表月度更新 {datetime.now().strftime("%Y-%m-%d")} ===')
    print()

    # 加载现有映射
    current = load_current_map()
    mapping = current['mapping']
    existing_codes = get_all_mapped_codes(mapping)
    print(f'现有映射: {len(mapping)} 个行业, {len(existing_codes)} 只 ETF')

    # 拉取最新 ETF 列表
    time.sleep(0.3)
    all_etfs = fetch_etf_list()
    live_codes = set(r['ts_code'][:6] for r in all_etfs)

    # 检查退市
    delisted = existing_codes - live_codes
    if delisted:
        print(f'\n⚠ 已退市/不存在的 ETF ({len(delisted)}只):')
        for code in sorted(delisted):
            # 找到它在哪些行业里
            for ind, etfs in mapping.items():
                for e in etfs:
                    if e['code'] == code:
                        print(f'  {code} {e["name"]} → {ind}')
    else:
        print('\n无退市 ETF')

    # 检查新增（近3个月成立的 ETF）
    cutoff = (datetime.now().replace(day=1)).strftime('%Y%m%d')  # 本月1号
    # 往前推3个月
    month = datetime.now().month
    year = datetime.now().year
    for _ in range(3):
        month -= 1
        if month <= 0:
            month += 12
            year -= 1
    cutoff = f'{year}{month:02d}01'

    new_etfs = [r for r in all_etfs if (r.get('found_date') or '') >= cutoff]
    new_etfs = [r for r in new_etfs if r['ts_code'][:6] not in existing_codes]

    if new_etfs:
        print(f'\n新上市 ETF ({len(new_etfs)}只, 近3个月):')
        for r in sorted(new_etfs, key=lambda x: x.get('found_date', '')):
            print(f'  {r["ts_code"][:6]} {r["name"]} 成立{r.get("found_date","")} 基准:{r.get("benchmark","")}')
    else:
        print('\n无新增 ETF（近3个月）')

    # 如果 apply 模式，移除退市的
    if apply_mode and delisted:
        removed = 0
        for ind in mapping:
            before = len(mapping[ind])
            mapping[ind] = [e for e in mapping[ind] if e['code'] not in delisted]
            removed += before - len(mapping[ind])
        print(f'\n已移除 {removed} 条退市映射')

        current['meta']['date'] = datetime.now().strftime('%Y-%m-%d')
        current['meta']['last_update'] = datetime.now().strftime('%Y-%m-%d')
        with open(MAP_PATH, 'w') as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        print(f'已保存到 {MAP_PATH}')

    if not apply_mode:
        print('\n(dry-run 模式，加 --apply 参数执行实际更新)')
        print('新增 ETF 需要手动决定映射到哪个行业，暂不自动添加')


if __name__ == '__main__':
    main()
