#!/usr/bin/env python3
"""
HALO 财务指标模块 - Tushare 版本
1. CapEx 二阶导（超大规模科技）
2. 重资产 vs 轻资产 PE 剪刀差
"""
import requests
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
FINANCIAL_JSON = DATA_DIR / "halo_financials.json"

# Tushare 配置
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'

# 超大规模科技（CapEx 追踪）
HYPERSCALERS = {
    "微软": "MSFT",
    "亚马逊": "AMZN", 
    "谷歌": "GOOGL",
    "Meta": "META",
}

def ts_api(api_name, **params):
    """调用 Tushare API"""
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    try:
        r = requests.post(TUSHARE_URL, json=body, timeout=30)
        j = r.json()
        if j.get('code') == 0:
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
    except Exception as e:
        print(f"  API 错误: {e}")
    return pd.DataFrame()

def fetch_capex_data():
    """拉取超大规模科技公司的季度 CapEx"""
    print("⏳ 拉取 CapEx 数据...")
    results = {}
    
    # 拉取最近2年数据
    start_date = '20220101'
    end_date = datetime.now().strftime('%Y%m%d')
    
    for name, ticker in HYPERSCALERS.items():
        df = ts_api('us_cashflow', ts_code=ticker, start_date=start_date, end_date=end_date)
        
        if df.empty:
            print(f"  ⚠️  {name} 无数据")
            continue
        
        # 筛选"购买固定资产"（CapEx）
        capex = df[df['ind_name'] == '购买固定资产'].copy()
        
        if capex.empty:
            print(f"  ⚠️  {name} 无 CapEx 数据")
            continue
        
        # 转换格式
        capex['date'] = pd.to_datetime(capex['end_date'], format='%Y%m%d')
        capex['capex'] = capex['ind_value'].astype(float).abs()  # 取绝对值
        capex = capex[['date', 'capex']].sort_values('date')
        
        results[ticker] = capex
        print(f"  ✅ {name} {len(capex)} 个季度")
    
    return results

def calculate_capex_acceleration(capex_data):
    """计算 CapEx 二阶导（加速度）"""
    print("⏳ 计算 CapEx 二阶导...")
    results = []
    
    for ticker, df in capex_data.items():
        if len(df) < 3:
            continue
        
        # 一阶导：环比增速
        df['growth'] = df['capex'].pct_change()
        
        # 二阶导：增速的变化
        df['acceleration'] = df['growth'].diff()
        
        # 最新值
        latest = df.iloc[-1]
        results.append({
            'ticker': ticker,
            'date': latest['date'].strftime('%Y-%m-%d'),
            'capex': float(latest['capex']),
            'growth': float(latest['growth']) if pd.notna(latest['growth']) else None,
            'acceleration': float(latest['acceleration']) if pd.notna(latest['acceleration']) else None,
        })
    
    print(f"✅ 完成 {len(results)} 家公司")
    return results

if __name__ == '__main__':
    print("="*60)
    print("HALO 财务指标计算（Tushare）")
    print("="*60)
    
    # 1. CapEx 二阶导
    capex_data = fetch_capex_data()
    capex_accel = calculate_capex_acceleration(capex_data)
    
    # 2. 保存结果
    output = {
        'capex_acceleration': capex_accel,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    with open(FINANCIAL_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print("="*60)
    print(f"✅ CapEx 二阶导:")
    for item in capex_accel:
        print(f"   {item['ticker']:6} CapEx={item['capex']/1e9:.1f}B, 增速={item['growth']*100 if item['growth'] else 0:.1f}%, 加速度={item['acceleration']*100 if item['acceleration'] else 0:.1f}%")
    
    print(f"✅ 结果已保存：{FINANCIAL_JSON}")
    print("="*60)
