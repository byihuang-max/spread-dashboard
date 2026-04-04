#!/usr/bin/env python3
"""固收+基金分析 - 最终版"""
import pandas as pd
import requests
from datetime import datetime, timedelta

TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"

def query(api_name, **params):
    r = requests.post(API, json={'api_name':api_name,'token':TOKEN,'params':params,'fields':''}, timeout=60)
    obj = r.json()
    if obj['code'] == 0:
        return pd.DataFrame(obj['data']['items'], columns=obj['data']['fields'])
    return pd.DataFrame()

print("📊 1/4 拉取基金列表...")
df_basic = query('fund_basic')
df_basic = df_basic[(df_basic['fund_type'].isin(['债券型','混合型'])) & (df_basic['status']=='L')]
print(f"   筛选出 {len(df_basic)} 只固收+候选")

print("📊 2/4 拉取最新净值...")
end_date = '20260402'
start_date = '20260102'
df_nav_latest = query('fund_nav', nav_date=end_date)
df_nav_start = query('fund_nav', nav_date=start_date)
df_nav = pd.concat([df_nav_latest, df_nav_start])
print(f"   获取 {len(df_nav)} 条净值记录")

print("📊 3/4 拉取持仓数据...")
df_port = query('fund_portfolio', period='20251231')
print(f"   获取 {len(df_port)} 条持仓记录")

print("📊 4/4 拉取份额数据...")
df_share = query('fund_share')
df_share = df_share[df_share['trade_date'] >= start_date]
print(f"   获取 {len(df_share)} 条份额记录")

# 计算每只基金的指标
print("\n🔄 计算指标...")
results = []

for idx, row in df_basic.iterrows():
    code = row['ts_code']
    name = row['name']
    mgmt = row['management']
    
    # 股票仓位
    port = df_port[df_port['ts_code'] == code]
    stock_ratio = port['stk_mkv_ratio'].sum() if not port.empty else 0
    
    # 90天收益
    nav = df_nav[df_nav['ts_code'] == code].sort_values('nav_date')
    if len(nav) >= 2:
        ret = (nav.iloc[-1]['unit_nav'] - nav.iloc[0]['unit_nav']) / nav.iloc[0]['unit_nav'] * 100
        bond_contrib = ret * (1 - stock_ratio/100)
        plus_contrib = ret * (stock_ratio/100)
    else:
        bond_contrib = plus_contrib = 0
    
    # 规模变化
    share = df_share[df_share['ts_code'] == code].sort_values('trade_date')
    if len(share) >= 2:
        scale_chg = (share.iloc[-1]['fd_share'] - share.iloc[0]['fd_share']) / share.iloc[0]['fd_share'] * 100
    else:
        scale_chg = 0
    
    # 分类
    if stock_ratio > 30:
        ftype = "固收+股票(高)"
    elif stock_ratio > 10:
        ftype = "固收+股票(中)"
    elif stock_ratio > 0:
        ftype = "固收+股票(低)"
    else:
        ftype = "纯债/其他"
    
    is_key = "是" if any(x in mgmt for x in ["易方达","鹏华"]) else "否"
    
    results.append({
        '基金代码': code,
        '基金名称': name,
        '基金公司': mgmt,
        '固收+类型': ftype,
        '股票仓位(%)': round(stock_ratio, 2),
        '债券贡献(%)': round(bond_contrib, 2),
        '加的贡献(%)': round(plus_contrib, 2),
        '90天规模变化(%)': round(scale_chg, 2),
        '易方达/鹏华': is_key
    })
    
    if (idx + 1) % 1000 == 0:
        print(f"   已处理 {idx+1}/{len(df_basic)}")

df_out = pd.DataFrame(results)
df_out = df_out.sort_values(['易方达/鹏华','90天规模变化(%)'], ascending=[False, False])

output = '/Users/apple/Desktop/gamt-dashboard/fund_analysis/fixed_income_plus_analysis.csv'
df_out.to_csv(output, index=False, encoding='utf-8-sig')

print(f"\n✅ 完成！")
print(f"📁 {output}")
print(f"📊 共 {len(df_out)} 只基金")
print(f"🎯 易方达/鹏华: {len(df_out[df_out['易方达/鹏华']=='是'])} 只")
