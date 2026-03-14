#!/usr/bin/env python3
"""
HALO PE剪刀差 - 用Tushare EPS + iFind价格计算
重资产（能源+国防）vs 轻资产（金融）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../meme/antifragile'))
from fetch_data_ifind import get_token, IFIND_BASE
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_JSON = DATA_DIR / "halo_financials.json"

TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'

# 重资产组（能源+国防）- Tushare代码不带后缀
HEAVY_ASSETS = ['SO', 'NEE', 'DUK', 'XOM', 'LMT', 'RTX', 'NOC']  # 去掉GD（无数据）

# 轻资产组（金融）
LIGHT_ASSETS = ['JPM', 'GS', 'MS', 'BAC']

# iFind代码映射（带.N后缀）
IFIND_CODES = {
    'SO': 'SO.N', 'NEE': 'NEE.N', 'DUK': 'DUK.N', 'XOM': 'XOM.N',
    'LMT': 'LMT.N', 'RTX': 'RTX.N', 'NOC': 'NOC.N',
    'JPM': 'JPM.N', 'GS': 'GS.N', 'MS': 'MS.N', 'BAC': 'BAC.N'
}

def ts_api(api_name, **params):
    """Tushare API调用"""
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    r = requests.post(TUSHARE_URL, json=body, timeout=30)
    j = r.json()
    if j.get('code') == 0:
        data = j.get('data', {})
        return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
    return pd.DataFrame()

def get_eps(codes):
    """拉取EPS数据（最近4个季度）"""
    result = {}
    for code in codes:
        df = ts_api('us_fina_indicator', ts_code=code, start_date='20240101', end_date='20241231')
        if not df.empty:
            # 优先用basic_eps，金融股用basic_eps_cs
            df['eps'] = df['basic_eps'].fillna(df['basic_eps_cs'])
            df = df[df['eps'].notna()].sort_values('end_date')
            if not df.empty:
                result[code] = {
                    'eps': float(df.iloc[-1]['eps']),  # 最新EPS
                    'date': df.iloc[-1]['end_date']
                }
    return result

def get_prices(codes, days=365):
    """拉取股价数据（iFind）"""
    token = get_token()
    if not token:
        return {}
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    # 转换为iFind代码
    ifind_codes = ','.join([IFIND_CODES[c] for c in codes if c in IFIND_CODES])
    
    r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
        json={
            'codes': ifind_codes,
            'indicators': 'close',
            'startdate': start.strftime('%Y-%m-%d'),
            'enddate': end.strftime('%Y-%m-%d')
        },
        headers={'Content-Type': 'application/json', 'access_token': token},
        timeout=30)
    
    d = r.json()
    if d.get('errorcode') != 0:
        print(f"  ❌ iFind错误: {d.get('errmsg')}")
        return {}
    
    # 解析数据
    result = {}
    for table in d.get('tables', []):
        ifind_code = table['thscode']
        # 反向查找Tushare代码
        ts_code = next((k for k, v in IFIND_CODES.items() if v == ifind_code), None)
        if not ts_code:
            continue
        
        times = table['time']
        prices = table['table']['close']
        result[ts_code] = {date: price for date, price in zip(times, prices) if price}
    
    return result

def calc_pe(prices, eps_data):
    """计算PE（股价/EPS）"""
    result = {}
    for code, price_dict in prices.items():
        if code not in eps_data:
            continue
        eps = eps_data[code]['eps']
        if eps <= 0:
            continue
        
        result[code] = {}
        for date, price in price_dict.items():
            result[code][date] = round(price / eps, 2)
    
    return result

def calc_scissors(heavy_pe, light_pe):
    """计算PE剪刀差"""
    # 计算平均PE
    heavy_avg = {}
    for code, pe_dict in heavy_pe.items():
        for date, pe in pe_dict.items():
            if date not in heavy_avg:
                heavy_avg[date] = []
            heavy_avg[date].append(pe)
    heavy_avg = {d: sum(v)/len(v) for d, v in heavy_avg.items()}
    
    light_avg = {}
    for code, pe_dict in light_pe.items():
        for date, pe in pe_dict.items():
            if date not in light_avg:
                light_avg[date] = []
            light_avg[date].append(pe)
    light_avg = {d: sum(v)/len(v) for d, v in light_avg.items()}
    
    # 找到共同日期
    all_dates = sorted(set(heavy_avg.keys()) & set(light_avg.keys()))
    
    history = []
    for date in all_dates:
        scissors = heavy_avg[date] - light_avg[date]
        history.append({
            'date': date,
            'heavy_pe': round(heavy_avg[date], 2),
            'light_pe': round(light_avg[date], 2),
            'scissors': round(scissors, 2),
        })
    
    return {
        'latest': history[-1] if history else None,
        'history': history[-252:],  # 最近一年
    }

if __name__ == '__main__':
    print("="*60)
    print("HALO PE剪刀差计算（Tushare EPS + iFind价格）")
    print("="*60)
    
    # 1. 拉取EPS
    print("⏳ 拉取EPS数据...")
    heavy_eps = get_eps(HEAVY_ASSETS)
    light_eps = get_eps(LIGHT_ASSETS)
    print(f"  ✅ 重资产: {len(heavy_eps)}/{len(HEAVY_ASSETS)}")
    print(f"  ✅ 轻资产: {len(light_eps)}/{len(LIGHT_ASSETS)}")
    
    # 2. 拉取股价
    print("⏳ 拉取股价数据...")
    all_codes = list(heavy_eps.keys()) + list(light_eps.keys())
    prices = get_prices(all_codes)
    print(f"  ✅ {len(prices)} 只股票")
    
    # 3. 计算PE
    print("⏳ 计算PE...")
    heavy_pe = calc_pe({k: v for k, v in prices.items() if k in HEAVY_ASSETS}, heavy_eps)
    light_pe = calc_pe({k: v for k, v in prices.items() if k in LIGHT_ASSETS}, light_eps)
    
    # 4. 计算剪刀差
    scissors = calc_scissors(heavy_pe, light_pe)
    
    # 5. 读取现有数据（CapEx）
    if OUTPUT_JSON.exists():
        with open(OUTPUT_JSON, 'r') as f:
            existing = json.load(f)
    else:
        existing = {}
    
    # 6. 合并数据
    existing['eps_scissors'] = scissors
    existing['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    print("="*60)
    if scissors['latest']:
        latest = scissors['latest']
        print(f"✅ PE剪刀差:")
        print(f"   日期: {latest['date']}")
        print(f"   重资产PE: {latest['heavy_pe']}")
        print(f"   轻资产PE: {latest['light_pe']}")
        print(f"   剪刀差: {latest['scissors']} ({'负值=重资产便宜' if latest['scissors'] < 0 else '正值=轻资产便宜'})")
        print(f"   历史点数: {len(scissors['history'])}")
    
    print(f"✅ 结果已保存：{OUTPUT_JSON}")
    print("="*60)
