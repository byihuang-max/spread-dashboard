#!/usr/bin/env python3
import pandas as pd

# 读取全部净值数据
df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_funds_latest_nav.csv')

# 我们的20只产品名单
our_products = [
    '顽岩量化选股1号',
    '正仁股票择时一期',
    '正仁双创择时一号', 
    '瀚鑫纸鸢量化优选',
    '积沐领航者',
    '太衍光年中证2000指数增强',
    '时间序列红利增强',
    '赢仕安盈二号',
    '具力芒种1号',
    '旌安思源1号B类',
    '创世纪顾锝灵活多策略',
    '立心-私募学院菁英353号',
    '翔云50二号A类',
    '特夫郁金香全量化',
    '铭跃行远均衡一号',
    '碳硅1号',
    '涌泉君安三号',
    '海鹏扬帆',
    '格林基金鲲鹏6号',
    '波克宏观配置1号'
]

# 3月27日最新净值从corrected CSV获取
latest_df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/returns_20260327_corrected.csv')

print("产品名称,去年末净值,3月27日净值,今年以来收益%")
print("-" * 70)

for idx, row in latest_df.iterrows():
    name = row['产品名称']
    nav_3m27 = row['3月27日净值']
    
    # 查找去年末（2025-12-31）的净值
    # 如果没有，找去年12月最后一个可用净值
    cond = df['our_name'] == name
    if cond.sum() == 0:
        # 试试匹配full_name
        cond = df['full_name'].str.contains(name.split('（')[0])
    matches = df[cond].copy()
    matches['date'] = pd.to_datetime(matches['price_date'])
    matches = matches[matches['date'] <= '2025-12-31'].sort_values('date', ascending=False)
    
    if len(matches) == 0:
        print(f"{name},NOT FOUND,,,-")
        continue
        
    last_year_nav = matches.iloc[0]['nav']
    ytd = (nav_3m27 / last_year_nav - 1) * 100
    date_used = matches.iloc[0]['price_date']
    print(f"{name},{last_year_nav:.4f},{nav_3m27:.4f},{ytd:.2f}% (date: {date_used})")
