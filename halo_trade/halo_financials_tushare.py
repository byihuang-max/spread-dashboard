#!/usr/bin/env python3
"""
HALO 财务指标模块 - Tushare 版本
1. CapEx 二阶导（超大规模科技）
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
    "MSFT": "微软",
    "AMZN": "亚马逊", 
    "GOOGL": "谷歌",
    "META": "Meta",
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
    
    start_date = '20220101'
    end_date = datetime.now().strftime('%Y%m%d')
    
    for ticker, name in HYPERSCALERS.items():
        df = ts_api('us_cashflow', ts_code=ticker, start_date=start_date, end_date=end_date)
        
        if df.empty:
            print(f"  ⚠️  {name} 无数据")
            continue
        
        # 筛选"购买固定资产"（CapEx）
        capex = df[df['ind_name'] == '购买固定资产'].copy()
        
        if capex.empty:
            print(f"  ⚠️  {name} 无 CapEx 数据")
            continue
        
        capex['date'] = pd.to_datetime(capex['end_date'], format='%Y%m%d')
        capex['capex'] = capex['ind_value'].astype(float).abs()
        capex = capex[['date', 'capex']].sort_values('date')
        
        results[ticker] = capex
        print(f"  ✅ {name}: {len(capex)} 个季度")
    
    return results

def calculate_capex_derivatives(capex_data):
    """计算 CapEx 一阶导和二阶导"""
    print("⏳ 计算 CapEx 二阶导...")
    results = {}
    
    for ticker, df in capex_data.items():
        if len(df) < 3:
            continue
        
        # 一阶导：YoY 增速
        df['yoy_growth'] = df['capex'].pct_change(4) * 100
        
        # 二阶导：增速的变化
        df['second_derivative'] = df['yoy_growth'].diff()
        
        # 历史数据（最近8个季度）
        history = []
        for _, row in df.tail(8).iterrows():
            history.append({
                "quarter": row['date'].strftime('%Y-%m-%d'),
                "capex": round(float(row['capex']) / 1e9, 2),
                "yoy_growth": round(float(row['yoy_growth']), 2) if pd.notna(row['yoy_growth']) else None,
                "second_derivative": round(float(row['second_derivative']), 2) if pd.notna(row['second_derivative']) else None,
            })
        
        # 最新值
        latest = df.iloc[-1]
        second_deriv = latest['second_derivative']
        
        if pd.notna(second_deriv):
            if second_deriv > 5:
                trend, signal = "加速", "🟢"
            elif second_deriv < -5:
                trend, signal = "减速", "🔴"
            else:
                trend, signal = "平稳", "🟡"
        else:
            trend, signal = "数据不足", "⚪"
        
        results[ticker] = {
            "name": HYPERSCALERS[ticker],
            "latest": {
                "capex": round(float(latest['capex']) / 1e9, 2),
                "yoy_growth": round(float(latest['yoy_growth']), 2) if pd.notna(latest['yoy_growth']) else None,
                "second_derivative": round(float(second_deriv), 2) if pd.notna(second_deriv) else None,
                "trend": trend,
                "signal": signal,
                "quarter": latest['date'].strftime('%Y-%m-%d'),
            },
            "history": history
        }
    
    print(f"✅ 完成 {len(results)} 家公司")
    return results

if __name__ == '__main__':
    print("="*60)
    print("HALO 财务指标计算（Tushare）")
    print("="*60)
    
    capex_data = fetch_capex_data()
    capex_deriv = calculate_capex_derivatives(capex_data)
    
    # 保存结果（前端期望的格式）
    output = {
        'capex_second_derivative': capex_deriv,
        'eps_scissors': {},  # PE剪刀差暂时留空
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    with open(FINANCIAL_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print("="*60)
    print(f"✅ CapEx 二阶导:")
    for ticker, data in capex_deriv.items():
        latest = data['latest']
        print(f"   {ticker:6} {data['name']:6} CapEx={latest['capex']}B, YoY={latest['yoy_growth']}%, 二阶导={latest['second_derivative']}% {latest['signal']}")
    
    print(f"✅ 结果已保存：{FINANCIAL_JSON}")
    print("="*60)
