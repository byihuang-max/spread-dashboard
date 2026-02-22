#!/usr/bin/env python3
"""
宽基量化股票指标 — 数据脚本 v2
拉取4个子指标的近一年数据，输出 JSON 供 FOF 看板使用

指标1: 全市场成交额时序（中证全指 amount）
指标2: 宽基成交额占比时序（300/500/1000/2000/科创+创业板 各占全A比例）
指标3: IF/IC/IM 年化基差时序（主力连续合约 vs 现货指数）
指标4: 因子表现时序（用可获取的指数近似）
"""

import requests, json, time, os, sys
from datetime import datetime, timedelta

# ============ 配置 ============
TS_URL  = 'http://lianghua.nanyangqiankun.top'
TS_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'

END_DATE   = datetime.now().strftime('%Y%m%d')
START_DATE = (datetime.now() - timedelta(days=400)).strftime('%Y%m%d')

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============ Tushare 封装（带限流保护）============
_last_call = 0

def ts_api(api_name, params, fields=None):
    """调用 Tushare，自动限流（每次间隔 >=1.5s）"""
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)
    
    body = {'api_name': api_name, 'token': TS_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    
    for attempt in range(3):
        try:
            _last_call = time.time()
            r = requests.post(TS_URL, json=body, timeout=60)
            if not r.text:
                print(f'    [空响应, retry {attempt+1}]')
                time.sleep(3)
                continue
            data = r.json()
            if data.get('code') == 0 and data.get('data', {}).get('items'):
                cols = data['data']['fields']
                rows = data['data']['items']
                return [dict(zip(cols, row)) for row in rows]
            elif data.get('code') == -2001:
                print(f'    [限流, 等10s...]')
                time.sleep(10)
                continue
            else:
                msg = data.get('msg', '')
                if msg:
                    print(f'    [API: {msg}]')
                return []
        except Exception as e:
            print(f'    [异常: {e}, retry {attempt+1}]')
            time.sleep(3)
    return []


# ============ 指标1: 全市场成交额 ============
def fetch_total_amount():
    print('[1/4] 全市场成交额...')
    rows = ts_api('index_daily',
                  {'ts_code': '000985.CSI', 'start_date': START_DATE, 'end_date': END_DATE},
                  'trade_date,amount')
    result = []
    for r in sorted(rows, key=lambda x: x['trade_date']):
        result.append({
            'date': r['trade_date'],
            'amount_yi': round(r['amount'] / 100000, 2)
        })
    print(f'  → {len(result)} 天')
    return result


# ============ 指标2: 宽基成交额占比 ============
def fetch_index_amount_share():
    print('[2/4] 宽基成交额占比...')
    
    # 要拉的指数（含全A）
    all_codes = [
        ('000985.CSI', '全A'),
        ('000300.SH',  '沪深300'),
        ('000905.SH',  '中证500'),
        ('000852.SH',  '中证1000'),
        ('932000.CSI', '中证2000'),
        ('000688.SH',  '科创50'),
        ('399006.SZ',  '创业板指'),
    ]
    
    # 逐个拉
    raw = {}  # {code: {date: amount}}
    for code, name in all_codes:
        rows = ts_api('index_daily',
                      {'ts_code': code, 'start_date': START_DATE, 'end_date': END_DATE},
                      'trade_date,amount')
        raw[code] = {r['trade_date']: r['amount'] for r in rows}
        print(f'  {name}({code}): {len(rows)} 天')
    
    # 计算占比
    total = raw.get('000985.CSI', {})
    dates = sorted(total.keys())
    result = []
    for d in dates:
        tot = total[d]
        if tot <= 0:
            continue
        row = {'date': d}
        for code, name in all_codes[1:5]:  # 300/500/1000/2000
            row[name] = round(raw.get(code, {}).get(d, 0) / tot * 100, 2)
        # 科创50+创业板指
        kc = raw.get('000688.SH', {}).get(d, 0)
        cy = raw.get('399006.SZ', {}).get(d, 0)
        row['科创+创业板'] = round((kc + cy) / tot * 100, 2)
        result.append(row)
    
    print(f'  → {len(result)} 天')
    return result


# ============ 指标3: 股指期货年化基差 ============
def fetch_basis():
    print('[3/4] 股指期货年化基差...')
    
    # 现货指数
    spot_map = {
        'IF': '000300.SH',
        'IC': '000905.SH',
        'IM': '000852.SH',
    }
    
    # 拉现货
    spot_data = {}
    for prefix, code in spot_map.items():
        rows = ts_api('index_daily',
                      {'ts_code': code, 'start_date': START_DATE, 'end_date': END_DATE},
                      'trade_date,close')
        spot_data[prefix] = {r['trade_date']: r['close'] for r in rows}
        print(f'  现货 {prefix}: {len(rows)} 天')
    
    # 拉期货主力连续
    fut_data = {}
    for prefix in ['IF', 'IC', 'IM']:
        code = f'{prefix}.CFX'
        rows = ts_api('fut_daily',
                      {'ts_code': code, 'start_date': START_DATE, 'end_date': END_DATE},
                      'trade_date,close')
        fut_data[prefix] = {r['trade_date']: r['close'] for r in rows}
        print(f'  期货 {prefix}.CFX: {len(rows)} 天')
    
    # 计算年化基差
    # 简化：(期货-现货)/现货 * 12 * 100（月化→年化近似）
    all_dates = sorted(
        set(spot_data['IF'].keys()) & set(fut_data['IF'].keys()) &
        set(spot_data['IC'].keys()) & set(fut_data['IC'].keys()) &
        set(spot_data['IM'].keys()) & set(fut_data['IM'].keys())
    )
    
    result = []
    for d in all_dates:
        row = {'date': d}
        for prefix in ['IF', 'IC', 'IM']:
            spot = spot_data[prefix].get(d)
            fut = fut_data[prefix].get(d)
            if spot and fut and spot > 0:
                row[prefix] = round((fut - spot) / spot * 12 * 100, 2)
        if len(row) > 1:
            result.append(row)
    
    print(f'  → {len(result)} 天')
    return result


# ============ 指标4: 因子表现时序 ============
def fetch_factor_performance():
    """
    用可获取的指数构造因子超额收益：
    - 价值: 国证价值(399371.SZ)
    - 成长: 国证成长(399370.SZ)
    - 红利/质量: 中证红利(000922.CSI)
    - 小盘/流动性: 中证2000(932000.CSI)
    基准: 中证全指(000985.CSI)
    """
    print('[4/4] 因子表现时序...')
    
    factor_codes = [
        ('000985.CSI', '基准'),
        ('399371.SZ',  '价值'),
        ('399370.SZ',  '成长'),
        ('000922.CSI', '红利'),
        ('932000.CSI', '小盘'),
    ]
    
    raw = {}
    for code, name in factor_codes:
        rows = ts_api('index_daily',
                      {'ts_code': code, 'start_date': START_DATE, 'end_date': END_DATE},
                      'trade_date,close')
        raw[name] = {}
        for r in rows:
            raw[name][r['trade_date']] = r['close']
        print(f'  {name}({code}): {len(rows)} 天')
    
    # 计算超额收益净值
    bench = raw.get('基准', {})
    factor_names = [n for _, n in factor_codes if n != '基准']
    dates = sorted(bench.keys())
    
    result = []
    nav = {n: 1.0 for n in factor_names}
    prev = {}
    
    for i, d in enumerate(dates):
        if i == 0:
            prev = {n: raw[n].get(d) for n in ['基准'] + factor_names}
            row = {'date': d}
            for n in factor_names:
                row[n] = 1.0
            result.append(row)
            continue
        
        bench_close = bench.get(d)
        bench_prev = prev.get('基准')
        if not bench_close or not bench_prev or bench_prev == 0:
            prev = {n: raw[n].get(d, prev.get(n)) for n in ['基准'] + factor_names}
            continue
        
        bench_ret = (bench_close - bench_prev) / bench_prev
        row = {'date': d}
        
        for n in factor_names:
            cur = raw[n].get(d)
            prv = prev.get(n)
            if cur and prv and prv > 0:
                factor_ret = (cur - prv) / prv
                excess = factor_ret - bench_ret
                nav[n] *= (1 + excess)
            row[n] = round(nav[n], 4)
        
        result.append(row)
        prev = {n: raw[n].get(d, prev.get(n)) for n in ['基准'] + factor_names}
    
    print(f'  → {len(result)} 天, 因子: {factor_names}')
    return result, factor_names


# ============ 主流程 ============
def main():
    print('=' * 50)
    print('宽基量化股票指标 数据拉取 v2')
    print(f'区间: {START_DATE} ~ {END_DATE}')
    print('=' * 50)
    
    data = {}
    
    data['total_amount'] = fetch_total_amount()
    data['index_share'] = fetch_index_amount_share()
    data['basis'] = fetch_basis()
    
    factor_data, factor_names = fetch_factor_performance()
    data['factor'] = factor_data
    data['factor_names'] = factor_names
    
    # 输出 JSON
    out_path = os.path.join(OUT_DIR, 'quant_stock_data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ 数据已保存: {out_path}')
    print(f'   total_amount: {len(data["total_amount"])} 天')
    print(f'   index_share:  {len(data["index_share"])} 天')
    print(f'   basis:        {len(data["basis"])} 天')
    print(f'   factor:       {len(data["factor"])} 天, 因子={data["factor_names"]}')


if __name__ == '__main__':
    main()
