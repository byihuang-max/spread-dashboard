#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
滚动相关性矩阵计算
"""

import json
import pandas as pd
import numpy as np

def calculate_rolling_correlation(window=30):
    """计算30天滚动相关性矩阵（8x8）"""
    
    # 读取净值数据
    with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    nav_data = data['nav_data']
    
    # 转换为DataFrame（排除WTI原油，只用8个核心资产）
    CORR_ASSETS = ['纳斯达克100', '标普500', '恒生科技ETF', '科创50ETF', 'BTC', '日经225', '韩国KOSPI', 'COMEX黄金']
    filtered = {k: v for k, v in nav_data.items() if k in CORR_ASSETS}
    df = pd.DataFrame(filtered)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    
    # 删除有NaN的行（不同资产数据起始日期不同）
    df = df.dropna()
    
    # 计算收益率
    returns = df.pct_change().dropna()
    
    # 计算滚动相关性矩阵
    dates = returns.index[window-1:]
    corr_matrices = {}
    
    for date in dates:
        window_data = returns.loc[:date].tail(window)
        if len(window_data) == window:
            corr_matrix = window_data.corr()
            date_str = date.strftime('%Y-%m-%d')
            # 转换为可序列化的字典
            corr_matrices[date_str] = {
                col: {row: float(corr_matrix.loc[row, col]) 
                      for row in corr_matrix.index}
                for col in corr_matrix.columns
            }
    
    # 保存
    output = {
        'window': window,
        'update_time': data['update_time'],
        'assets': list(returns.columns),
        'corr_matrices': corr_matrices
    }
    
    with open('rolling_corr.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 滚动相关性矩阵已计算")
    print(f"  - 资产数量: {len(returns.columns)}")
    print(f"  - 时间点数量: {len(corr_matrices)}")
    print(f"  - 窗口: {window}天")

if __name__ == '__main__':
    calculate_rolling_correlation()
