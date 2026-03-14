#!/usr/bin/env python3
"""
HALO PE剪刀差 - 用iFind拉取个股PE
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

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_JSON = DATA_DIR / "halo_financials.json"

# 重资产组（能源+国防）
HEAVY_ASSETS = {
    'SO.N': '南方电力',
    'NEE.N': 'NextEra',
    'DUK.N': '杜克能源',
    'XOM.N': '埃克森美孚',
    'LMT.N': '洛克希德',
    'RTX.N': '雷神',
    'GD.N': '通用动力',
    'NOC.N': '诺斯罗普',
}

# 轻资产组（金融）
LIGHT_ASSETS = {
    'JPM.N': '摩根大通',
    'GS.N': '高盛',
    'MS.N': '摩根士丹利',
    'BAC.N': '美国银行',
}

def ifind_pe(codes, days=365):
    """拉取PE数据（最近一年）"""
    token = get_token()  # 每次请求前获取新token
    if not token:
        print("  ❌ 无法获取token")
        return {}
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
    r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
        json={
            'codes': codes,
            'indicators': 'pe_ttm',
            'startdate': start.strftime('%Y-%m-%d'),
            'enddate': end.strftime('%Y-%m-%d')
        },
        headers={'Content-Type': 'application/json', 'access_token': token},
        timeout=30)
    
    d = r.json()
    if d.get('errorcode') != 0:
        print(f"  ❌ iFind错误: {d.get('errmsg')}")
        return {}
    
    # 解析数据（tables格式）
    result = {}
    for table in d.get('tables', []):
        code = table.get('thscode')
        for row in table.get('table', []):
            date = row.get('time')
            pe = row.get('pe_ttm')
            if pe and pe > 0:
                if code not in result:
                    result[code] = {}
                result[code][date] = float(pe)
    
    return result

def calc_scissors(heavy_pe, light_pe):
    """计算PE剪刀差"""
    # 找到共同日期
    all_dates = sorted(set(heavy_pe.keys()) & set(light_pe.keys()))
    
    history = []
    for date in all_dates:
        scissors = heavy_pe[date] - light_pe[date]
        history.append({
            'date': date,
            'heavy_pe': round(heavy_pe[date], 2),
            'light_pe': round(light_pe[date], 2),
            'scissors': round(scissors, 2),
        })
    
    return {
        'latest': history[-1] if history else None,
        'history': history[-252:],  # 最近一年
    }

if __name__ == '__main__':
    print("="*60)
    print("HALO PE剪刀差计算（iFind）")
    print("="*60)
    
    # 1. 拉取重资产PE
    print("⏳ 拉取重资产PE...")
    heavy_data = ifind_pe(list(HEAVY_ASSETS.keys()))
    print(f"  ✅ {len(heavy_data)} 只股票")
    
    # 2. 拉取轻资产PE
    print("⏳ 拉取轻资产PE...")
    light_data = ifind_pe(list(LIGHT_ASSETS.keys()))
    print(f"  ✅ {len(light_data)} 只股票")
    
    # 3. 计算平均PE
    print("⏳ 计算平均PE...")
    heavy_avg = {}
    for code, pe_dict in heavy_data.items():
        for date, pe in pe_dict.items():
            if date not in heavy_avg:
                heavy_avg[date] = []
            heavy_avg[date].append(pe)
    heavy_avg = {d: sum(v)/len(v) for d, v in heavy_avg.items()}
    
    light_avg = {}
    for code, pe_dict in light_data.items():
        for date, pe in pe_dict.items():
            if date not in light_avg:
                light_avg[date] = []
            light_avg[date].append(pe)
    light_avg = {d: sum(v)/len(v) for d, v in light_avg.items()}
    
    # 4. 计算剪刀差
    scissors = calc_scissors(heavy_avg, light_avg)
    
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
