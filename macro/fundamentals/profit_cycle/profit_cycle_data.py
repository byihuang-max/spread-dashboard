#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利润周期监控 + 内需接棒验证（简化版）
数据拉取：月度数据，3年历史，增量更新
使用Tushare免费版可用的数据
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests
import time

# Tushare配置
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TUSHARE_URL = "https://api.tushare.pro"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def ts_api(api_name, fields='', **kwargs):
    """Tushare API调用"""
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30, 
                            proxies={'http': None, 'https': None})
            j = r.json()
            if j.get('code') != 0:
                print(f"  ❌ API错误 {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            df = pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
            return df
        except Exception as e:
            print(f"  ⚠️ 尝试 {attempt+1} 失败: {e}")
            time.sleep(2)
    return pd.DataFrame()

def fetch_ppi_data(start_date, end_date):
    """拉取PPI数据（月度）"""
    print("📊 拉取PPI数据...")
    df = ts_api('cn_ppi', fields='month,ppi_yoy,ppi_mom', 
                 start_month=start_date[:6], end_month=end_date[:6])
    
    if df.empty:
        print("  ❌ PPI数据为空")
        return pd.DataFrame()
    
    df['date'] = pd.to_datetime(df['month'], format='%Y%m') + pd.offsets.MonthEnd(0)
    df['date'] = df['date'].dt.strftime('%Y%m%d')
    
    df = df.rename(columns={
        'ppi_yoy': 'ppi_yoy',
        'ppi_mom': 'ppi_mom'
    })
    
    df = df[['date', 'ppi_yoy', 'ppi_mom']]
    
    print(f"  ✅ PPI数据: {len(df)}条")
    return df

def fetch_cpi_data(start_date, end_date):
    """拉取CPI数据（月度）"""
    print("📊 拉取CPI数据...")
    
    df = ts_api('cn_cpi', fields='month,nt_yoy,nt_mom',
                 start_month=start_date[:6], end_month=end_date[:6])
    
    if df.empty:
        print("  ❌ CPI数据为空")
        return pd.DataFrame()
    
    df['date'] = pd.to_datetime(df['month'], format='%Y%m') + pd.offsets.MonthEnd(0)
    df['date'] = df['date'].dt.strftime('%Y%m%d')
    
    df = df.rename(columns={
        'nt_yoy': 'core_cpi_yoy',
        'nt_mom': 'core_cpi_mom'
    })
    
    df = df[['date', 'core_cpi_yoy', 'core_cpi_mom']]
    
    print(f"  ✅ CPI数据: {len(df)}条")
    return df

def fetch_m1m2_data(start_date, end_date):
    """拉取M1/M2数据（月度）"""
    print("📊 拉取M1/M2数据...")
    
    df = ts_api('cn_m', fields='month,m1,m1_yoy,m2,m2_yoy',
                 start_month=start_date[:6], end_month=end_date[:6])
    
    if df.empty:
        print("  ❌ M1/M2数据为空")
        return pd.DataFrame()
    
    df['date'] = pd.to_datetime(df['month'], format='%Y%m') + pd.offsets.MonthEnd(0)
    df['date'] = df['date'].dt.strftime('%Y%m%d')
    
    # 计算M1-M2剪刀差
    df['m1_yoy'] = pd.to_numeric(df['m1_yoy'], errors='coerce')
    df['m2_yoy'] = pd.to_numeric(df['m2_yoy'], errors='coerce')
    df['m1_m2_scissors'] = (df['m1_yoy'] - df['m2_yoy']).round(2)
    
    df = df[['date', 'm1_yoy', 'm2_yoy', 'm1_m2_scissors']]
    
    print(f"  ✅ M1/M2数据: {len(df)}条")
    return df

def calculate_profit_cycle_score(df):
    """
    计算利润周期得分（0-4分）
    基于可用数据的简化版本
    """
    if df.empty:
        return df
    
    df = df.copy()
    df['profit_cycle_score'] = 0
    
    # 1. PPI环比转正 (+1分)
    if 'ppi_mom' in df.columns:
        df.loc[df['ppi_mom'] > 0, 'profit_cycle_score'] += 1
    
    # 2. PPI同比改善 (+1分)
    if 'ppi_yoy' in df.columns:
        df['ppi_yoy_change'] = df['ppi_yoy'].diff()
        df.loc[df['ppi_yoy_change'] > 0, 'profit_cycle_score'] += 1
    
    # 3. 核心CPI抬升 (+1分，需求驱动)
    if 'core_cpi_yoy' in df.columns:
        df['core_cpi_change'] = df['core_cpi_yoy'].diff()
        df.loc[df['core_cpi_change'] > 0, 'profit_cycle_score'] += 1
    
    # 4. M1-M2剪刀差改善 (+1分，流动性改善)
    if 'm1_m2_scissors' in df.columns:
        df['scissors_change'] = df['m1_m2_scissors'].diff()
        df.loc[df['scissors_change'] > 0, 'profit_cycle_score'] += 1
    
    # 利润周期阶段
    df['profit_cycle_stage'] = '筑底'
    df.loc[df['profit_cycle_score'] >= 2, 'profit_cycle_stage'] = '上行'
    df.loc[df['profit_cycle_score'] >= 3, 'profit_cycle_stage'] = '见顶'
    df.loc[(df['profit_cycle_score'] == 1) & (df['ppi_mom'] < 0), 'profit_cycle_stage'] = '下行'
    
    return df

def calculate_demand_recovery_score(df):
    """
    计算内需接棒得分（0-100分）
    基于可用数据的简化版本
    """
    if df.empty:
        return df
    
    df = df.copy()
    df['demand_recovery_score'] = 0
    
    # 1. 核心CPI同比>1% (+33分)
    if 'core_cpi_yoy' in df.columns:
        df.loc[df['core_cpi_yoy'] > 1, 'demand_recovery_score'] += 33
    
    # 2. M1增速>M2增速 (+33分，企业活跃度)
    if 'm1_m2_scissors' in df.columns:
        df.loc[df['m1_m2_scissors'] > 0, 'demand_recovery_score'] += 33
    
    # 3. PPI环比转正 (+34分，价格止跌)
    if 'ppi_mom' in df.columns:
        df.loc[df['ppi_mom'] > 0, 'demand_recovery_score'] += 34
    
    return df

def main():
    print("=" * 60)
    print("利润周期监控 + 内需接棒验证 - 数据拉取（简化版）")
    print("=" * 60)
    
    # 时间范围：3年
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=365*3)).strftime('%Y%m%d')
    
    print(f"📅 时间范围: {start_date} - {end_date}\n")
    
    # 拉取数据
    ppi_df = fetch_ppi_data(start_date, end_date)
    time.sleep(0.5)
    
    cpi_df = fetch_cpi_data(start_date, end_date)
    time.sleep(0.5)
    
    m1m2_df = fetch_m1m2_data(start_date, end_date)
    time.sleep(0.5)
    
    # 合并数据
    print("\n📊 合并数据...")
    
    if ppi_df.empty and cpi_df.empty and m1m2_df.empty:
        print("❌ 所有数据都为空，退出")
        return
    
    # 从非空的df开始
    if not ppi_df.empty:
        merged_df = ppi_df
    elif not cpi_df.empty:
        merged_df = cpi_df
    else:
        merged_df = m1m2_df
    
    # 依次合并
    if not ppi_df.empty and not cpi_df.empty:
        merged_df = merged_df.merge(cpi_df, on='date', how='outer')
    elif not cpi_df.empty:
        merged_df = cpi_df
    
    if not m1m2_df.empty:
        merged_df = merged_df.merge(m1m2_df, on='date', how='outer')
    
    merged_df = merged_df.sort_values('date').reset_index(drop=True)
    
    # 计算得分
    print("📊 计算利润周期得分...")
    merged_df = calculate_profit_cycle_score(merged_df)
    
    print("📊 计算内需接棒得分...")
    merged_df = calculate_demand_recovery_score(merged_df)
    
    # 填充NaN
    merged_df = merged_df.fillna(0)
    
    print(f"✅ 合并后数据: {len(merged_df)}条")
    
    # 保存CSV
    csv_path = os.path.join(SCRIPT_DIR, 'profit_cycle.csv')
    merged_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ CSV已保存: {csv_path}")
    
    # 保存JSON
    json_data = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_range': {
            'start': start_date,
            'end': end_date,
            'count': len(merged_df)
        },
        'latest': {
            'date': merged_df.iloc[-1]['date'],
            'profit_cycle_score': int(merged_df.iloc[-1]['profit_cycle_score']),
            'profit_cycle_stage': merged_df.iloc[-1]['profit_cycle_stage'],
            'demand_recovery_score': int(merged_df.iloc[-1]['demand_recovery_score']),
            'ppi_yoy': float(merged_df.iloc[-1].get('ppi_yoy', 0)),
            'ppi_mom': float(merged_df.iloc[-1].get('ppi_mom', 0)),
            'core_cpi_yoy': float(merged_df.iloc[-1].get('core_cpi_yoy', 0)),
            'm1_m2_scissors': float(merged_df.iloc[-1].get('m1_m2_scissors', 0))
        },
        'history': merged_df.to_dict('records')
    }
    
    json_path = os.path.join(SCRIPT_DIR, 'profit_cycle.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON已保存: {json_path}")
    
    # 打印最新数据
    print("\n" + "=" * 60)
    print("📊 最新数据")
    print("=" * 60)
    print(f"日期: {json_data['latest']['date']}")
    print(f"利润周期得分: {json_data['latest']['profit_cycle_score']}/4")
    print(f"利润周期阶段: {json_data['latest']['profit_cycle_stage']}")
    print(f"内需接棒得分: {json_data['latest']['demand_recovery_score']}/100")
    print(f"PPI同比: {json_data['latest']['ppi_yoy']:.2f}%")
    print(f"PPI环比: {json_data['latest']['ppi_mom']:.2f}%")
    print(f"核心CPI同比: {json_data['latest']['core_cpi_yoy']:.2f}%")
    print(f"M1-M2剪刀差: {json_data['latest']['m1_m2_scissors']:.2f}%")
    print("=" * 60)

if __name__ == '__main__':
    main()
