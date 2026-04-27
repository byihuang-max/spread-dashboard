#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import pandas as pd
import time

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FofSubFundTrackList, FundPrice, FundCompanyPrice

# 你的API信息
appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 重新获取完整信息，包含price_type
print("重新获取产品列表获取price_type...")
req = FofSubFundTrackList(appid, appkey)
matched = []
target_funds = [
    "顽岩量化选股1号",
    "正仁股票择时一期",
    "正仁双创择时一号",
    "瀚鑫纸鸢量化优选",
    "积沐领航者",
    "太衍光年中证2000指数增强",
    "时间序列红利增强",
    "赢仕安盈二号",
    "具力芒种1号",
    "旌安思源1号B类",
    "创世纪顾锝灵活多策略",
    "立心-私募学院菁英353号",
    "翔云50二号A类",
    "特夫郁金香全量化",
    "铭跃行远均衡一号",
    "碳硅1号",
    "涌泉君安三号",
    "海鹏扬帆",
    "格林基金鲲鹏6号",
    "波克宏观配置1号"
]

all_funds = []
page = 1
while True:
    req = FofSubFundTrackList(appid, appkey)
    req.set_params(type_=3, page=page, page_size=100)
    res = req.do_request(use_df=False)
    if not res or 'list' not in res:
        break
    all_funds.extend(res['list'])
    if len(res['list']) < 100:
        break
    page += 1

matched = []
for fund in all_funds:
    name = fund['fund_short_name']
    reg_code = fund['register_number']
    price_type = fund['price_type']
    for target in target_funds:
        if target in name or name in target:
            matched.append({
                'name': target,
                'found_name': name,
                'reg_code': reg_code,
                'price_type': price_type
            })
            break

print(f"匹配到 {len(matched)} 只产品\n")

# 我们需要的日期
date_20 = '2026-03-20'
date_27 = '2026-03-27'
date_end_feb = '2026-02-29'  # 二月末，用于计算近一月

result = []

for i, fund in enumerate(matched):
    name = fund['name']
    reg_code = fund['reg_code']
    price_type = fund['price_type']
    
    print(f"正在查询 ({i+1}/{len(matched)}): {name} [{reg_code}], price_type={price_type}")
    
    nav_20 = None
    nav_27 = None
    nav_feb = None
    
    if price_type == 1:
        # 平台净值
        req = FundPrice(appid, appkey)
    else:
        # 团队净值
        req = FundCompanyPrice(appid, appkey)
    
    req.set_params(reg_code=reg_code, start_date='2026-02-01', end_date='2026-03-27')
    res = req.do_request(use_df=False)
    
    if res:
        for item in res:
            p_date = item.get('price_date')
            nav_val = item.get('net_value')
            if nav_val is None:
                continue
            try:
                nav = float(nav_val)
            except:
                continue
            if p_date == date_20:
                nav_20 = nav
            if p_date == date_27:
                nav_27 = nav
            if p_date == date_end_feb:
                nav_feb = nav
    
    # 计算收益率
    weekly_return = (nav_27 / nav_20 - 1) if nav_20 and nav_27 else None
    monthly_return = (nav_27 / nav_feb - 1) if nav_feb and nav_27 else None
    
    result.append({
        '产品名称': name,
        'price_type': price_type,
        '净值_3.20': nav_20,
        '净值_3.27': nav_27,
        '净值_2.29': nav_feb,
        '近一周(3.20-3.27)': weekly_return,
        '近一月(截至3.27)': monthly_return
    })
    
    time.sleep(0.5)

# 按照原顺序排序
result.sort(key=lambda x: target_funds.index(x['产品名称']))

# 输出结果
df = pd.DataFrame(result)
print("\n\n=== ✅ 最终计算结果：3月20日 - 3月27日 ===")
print()
print("| 产品名称 | 近一周 | 近一月 |")
print("|----------|--------|--------|")
for _, row in df.iterrows():
    w = f"{row['近一周(3.20-3.27)']:.2%}" if row['近一周(3.20-3.27)'] is not None else "无数据"
    m = f"{row['近一月(截至3.27)']:.2%}" if row['近一月(截至3.27)'] is not None else "无数据"
    print(f"| {row['产品名称']} | {w} | {m} |")

# 保存到CSV
df.to_csv('/Users/huangqingmeng/.openclaw/workspace/returns_20260327.csv', index=False, encoding='utf-8-sig')
print(f"\n📝 已保存完整数据到: /Users/huangqingmeng/.openclaw/workspace/returns_20260327.csv")
