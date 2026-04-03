#!/usr/bin/env python3
"""
固收+基金分类与归因分析
数据源：Tushare Pro
输出：fixed_income_plus_analysis.csv
"""

import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import time

# Tushare 配置
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TUSHARE_API = "https://api.tushare.pro"

def tushare_query(api_name, fields='', **kwargs):
    """Tushare API 查询"""
    data = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': kwargs,
        'fields': fields
    }
    try:
        response = requests.post(TUSHARE_API, json=data, timeout=30)
        result = response.json()
        if result['code'] == 0:
            df = pd.DataFrame(result['data']['items'], columns=result['data']['fields'])
            return df
        else:
            print(f"❌ {api_name} 查询失败: {result.get('msg', 'Unknown error')}")
            return pd.DataFrame()
    except Exception as e:
        print(f"❌ {api_name} 请求异常: {e}")
        return pd.DataFrame()

def get_fund_basic():
    """获取基金基本信息，筛选固收+类型"""
    print("📊 拉取基金列表...")
    df = tushare_query('fund_basic', fields='ts_code,name,management,fund_type,invest_type')
    
    if df.empty:
        return df
    
    # 筛选固收+相关类型
    # fund_type: 债券型、混合型
    # invest_type: 偏债混合型、二级债基等
    fixed_income_types = ['债券型', '混合型']
    df_filtered = df[df['fund_type'].isin(fixed_income_types)].copy()
    
    print(f"✅ 筛选出 {len(df_filtered)} 只固收+候选基金")
    return df_filtered

def get_fund_nav(ts_code, start_date, end_date):
    """获取基金净值"""
    df = tushare_query('fund_nav', 
                      fields='ts_code,end_date,accum_nav,unit_nav',
                      ts_code=ts_code,
                      start_date=start_date,
                      end_date=end_date)
    return df

def get_fund_portfolio(ts_code):
    """获取基金持仓（最近一期季报）"""
    df = tushare_query('fund_portfolio',
                      fields='ts_code,end_date,symbol,mkv,amount,stk_mkv_ratio',
                      ts_code=ts_code)
    return df

def get_fund_share(ts_code):
    """获取基金份额变化"""
    df = tushare_query('fund_share',
                      fields='ts_code,end_date,fd_share',
                      ts_code=ts_code)
    return df

def classify_fund(portfolio_df):
    """
    根据持仓分类固收+类型
    返回：(类型, 股票仓位%, 转债仓位%, 其他仓位%)
    """
    if portfolio_df.empty:
        return "未知", 0, 0, 0
    
    # 简化分类逻辑：根据持仓市值占比
    # 实际需要更细致的资产类型判断
    stock_ratio = portfolio_df['stk_mkv_ratio'].sum() if 'stk_mkv_ratio' in portfolio_df.columns else 0
    
    if stock_ratio > 30:
        return "固收+股票(高仓位)", stock_ratio, 0, 0
    elif stock_ratio > 10:
        return "固收+股票(中仓位)", stock_ratio, 0, 0
    elif stock_ratio > 0:
        return "固收+股票(低仓位)", stock_ratio, 0, 0
    else:
        return "纯债/其他", 0, 0, 0

def calculate_contribution(nav_df, portfolio_df):
    """
    计算债券贡献和"加"的部分贡献
    简化版：用净值变化和仓位估算
    """
    if nav_df.empty or len(nav_df) < 2:
        return 0, 0
    
    # 计算总收益
    nav_df = nav_df.sort_values('end_date')
    latest_nav = nav_df.iloc[-1]['unit_nav']
    earliest_nav = nav_df.iloc[0]['unit_nav']
    total_return = (latest_nav - earliest_nav) / earliest_nav * 100
    
    # 简化归因：假设债券部分贡献 = 总收益 * (1 - 股票仓位)
    if not portfolio_df.empty and 'stk_mkv_ratio' in portfolio_df.columns:
        stock_ratio = portfolio_df['stk_mkv_ratio'].sum() / 100
        bond_contrib = total_return * (1 - stock_ratio)
        plus_contrib = total_return * stock_ratio
    else:
        bond_contrib = total_return
        plus_contrib = 0
    
    return bond_contrib, plus_contrib

def calculate_scale_change(share_df):
    """计算近90天规模变化"""
    if share_df.empty or len(share_df) < 2:
        return 0
    
    share_df = share_df.sort_values('end_date')
    latest_share = share_df.iloc[-1]['fd_share']
    earliest_share = share_df.iloc[0]['fd_share']
    
    change_pct = (latest_share - earliest_share) / earliest_share * 100
    return change_pct

def main():
    print("🚀 开始固收+基金分析...")
    
    # 1. 获取基金列表
    fund_basic = get_fund_basic()
    if fund_basic.empty:
        print("❌ 无法获取基金列表")
        return
    
    # 2. 计算日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date_90d = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    
    results = []
    
    # 3. 遍历基金，获取详细数据
    print(f"📈 开始分析 {len(fund_basic)} 只基金...")
    for idx, row in fund_basic.iterrows():
        ts_code = row['ts_code']
        name = row['name']
        management = row['management']
        
        print(f"  [{idx+1}/{len(fund_basic)}] {name} ({ts_code})")
        
        # 获取净值
        nav_df = get_fund_nav(ts_code, start_date_90d, end_date)
        
        # 获取持仓
        portfolio_df = get_fund_portfolio(ts_code)
        
        # 获取份额
        share_df = get_fund_share(ts_code)
        
        # 分类
        fund_type, stock_ratio, bond_ratio, other_ratio = classify_fund(portfolio_df)
        
        # 计算贡献
        bond_contrib, plus_contrib = calculate_contribution(nav_df, portfolio_df)
        
        # 计算规模变化
        scale_change = calculate_scale_change(share_df)
        
        # 标注重点公司
        is_key = "是" if any(x in management for x in ["易方达", "鹏华"]) else "否"
        
        results.append({
            '基金代码': ts_code,
            '基金名称': name,
            '基金公司': management,
            '固收+类型': fund_type,
            '股票仓位(%)': round(stock_ratio, 2),
            '债券贡献(%)': round(bond_contrib, 2),
            '加的贡献(%)': round(plus_contrib, 2),
            '90天规模变化(%)': round(scale_change, 2),
            '易方达/鹏华': is_key
        })
        
        # 避免频率限制
        time.sleep(0.2)
        
        # 测试阶段：只处理前50只
        if idx >= 49:
            print("⚠️ 测试模式：只处理前50只基金")
            break
    
    # 4. 输出CSV
    df_result = pd.DataFrame(results)
    
    # 排序：易方达/鹏华优先，然后按90天规模变化降序
    df_result = df_result.sort_values(['易方达/鹏华', '90天规模变化(%)'], 
                                     ascending=[False, False])
    
    output_path = '~/Desktop/gamt-dashboard/fund_analysis/fixed_income_plus_analysis.csv'
    df_result.to_csv(output_path.replace('~', '/Users/apple'), index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 分析完成！")
    print(f"📁 输出文件: {output_path}")
    print(f"📊 共分析 {len(df_result)} 只基金")
    print(f"🎯 易方达/鹏华基金: {len(df_result[df_result['易方达/鹏华']=='是'])} 只")

if __name__ == '__main__':
    main()
