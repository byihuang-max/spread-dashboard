#!/usr/bin/env python3
"""固收+基金分析 - 精简版"""
import pandas as pd
import requests
from datetime import datetime, timedelta
import time

TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
API = "https://api.tushare.pro"

def query(api_name, **params):
    r = requests.post(API, json={'api_name':api_name,'token':TOKEN,'params':params,'fields':''}, timeout=30)
    obj = r.json()
    if obj['code'] == 0:
        return pd.DataFrame(obj['data']['items'], columns=obj['data']['fields'])
    return pd.DataFrame()

# 1. 获取基金列表
print("📊 拉取基金列表...")
df_basic = query('fund_basic')
df_basic = df_basic[(df_basic['fund_type'].isin(['债券型','混合型'])) & (df_basic['status']=='L')]
print(f"✅ 筛选出 {len(df_basic)} 只固收+候选基金")

# 2. 计算日期
end_date = datetime.now().strftime('%Y%m%d')
start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')

results = []
total = min(len(df_basic), 200)  # 限制200只，避免超时

for idx, row in df_basic.head(total).iterrows():
    code = row['ts_code']
    name = row['name']
    mgmt = row['management']
    
    print(f"  [{idx+1}/{total}] {name}")
    
    # 净值
    nav = query('fund_nav', ts_code=code, start_date=start_date, end_date=end_date)
    
    # 持仓（最新季报）
    port = query('fund_portfolio', ts_code=code)
    
    # 份额
    share = query('fund_share', ts_code=code)
    
    # 计算指标
    stock_ratio = port['stk_mkv_ratio'].sum() if not port.empty else 0
    
    if len(nav) >= 2:
        nav = nav.sort_values('nav_date')
        ret = (nav.iloc[-1]['unit_nav'] - nav.iloc[0]['unit_nav']) / nav.iloc[0]['unit_nav'] * 100
        bond_contrib = ret * (1 - stock_ratio/100)
        plus_contrib = ret * (stock_ratio/100)
    else:
        bond_contrib = plus_contrib = 0
    
    if len(share) >= 2:
        share = share.sort_values('trade_date')
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
    
    time.sleep(0.15)

# 3. 输出
df_out = pd.DataFrame(results)
df_out = df_out.sort_values(['易方达/鹏华','90天规模变化(%)'], ascending=[False, False])
output = '/Users/apple/Desktop/gamt-dashboard/fund_analysis/fixed_income_plus_analysis.csv'
df_out.to_csv(output, index=False, encoding='utf-8-sig')

print(f"\n✅ 完成！共 {len(df_out)} 只基金")
print(f"📁 {output}")
print(f"🎯 易方达/鹏华: {len(df_out[df_out['易方达/鹏华']=='是'])} 只")
