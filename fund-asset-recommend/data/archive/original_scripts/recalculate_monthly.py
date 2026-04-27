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

# 20只产品
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

# 重新匹配获取正确的reg_code和price_type
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
            existing = next((m for m in matched if m['name'] == target), None)
            if existing:
                if existing['price_type'] == 1 and price_type == 2:
                    matched.remove(existing)
                    matched.append({
                        'name': target,
                        'found_name': name,
                        'reg_code': reg_code,
                        'price_type': price_type
                    })
            else:
                matched.append({
                    'name': target,
                    'found_name': name,
                    'reg_code': reg_code,
                    'price_type': price_type
                })
            break

# 正确的月末日期：2026年2月没有29天，最后一个交易日是2月27日
target_end_feb = '2026-02-27'
date_20 = '2026-03-20'
date_27 = '2026-03-27'

result = []

for i, fund in enumerate(matched):
    name = fund['name']
    reg_code = fund['reg_code']
    price_type = fund['price_type']
    
    print(f"正在查询: {name} [{reg_code}]")
    
    nav_27 = None  # 3月27日
    nav_20 = None  # 3月20日
    nav_feb = None # 2月27日
    
    if price_type == 1:
        req = FundPrice(appid, appkey)
    else:
        req = FundCompanyPrice(appid, appkey)
    
    req.set_params(reg_code=reg_code, start_date='2026-02-20', end_date='2026-03-27')
    res = req.do_request(use_df=False)
    
    if res:
        for item in res:
            p_date = item.get('price_date')
            nav_val = item.get('nav')
            if nav_val is None:
                nav_val = item.get('net_value')
            if nav_val is None:
                continue
            try:
                nav = float(nav_val)
            except:
                continue
            if p_date == date_27:
                nav_27 = nav
            if p_date == date_20:
                nav_20 = nav
            if p_date == target_end_feb:
                nav_feb = nav
    
    # 计算
    weekly_return = (nav_27 / nav_20 - 1) if nav_20 and nav_27 else None
    monthly_return = (nav_27 / nav_feb - 1) if nav_feb and nav_27 else None
    
    result.append({
        '产品名称': name,
        '价格类型': '平台' if price_type == 1 else '团队',
        '2月27日净值': nav_feb,
        '3月20日净值': nav_20,
        '3月27日净值': nav_27,
        '近一周': weekly_return,
        '近一月': monthly_return
    })
    
    time.sleep(0.3)

# 排序
result.sort(key=lambda x: target_funds.index(x['产品名称']))

# 输出
print("\n\n=== ✅ 修正后计算结果：近一月用2月27日（上月最后交易日）计算 ===")
print()

from collections import defaultdict
categories = {
    '量选类': ['顽岩量化选股1号', '正仁股票择时一期'],
    '风格类': ['正仁双创择时一号', '瀚鑫纸鸢量化优选', '积沐领航者', '太衍光年中证2000指数增强', 
               '时间序列红利增强', '赢仕安盈二号', '具力芒种1号'],
    '绝对收益': ['旌安思源1号B类', '创世纪顾锝灵活多策略', '立心-私募学院菁英353号', 
                '翔云50二号A类', '特夫郁金香全量化'],
    '商品类': ['铭跃行远均衡一号', '碳硅1号', '涌泉君安三号', '海鹏扬帆'],
    '多策略': ['格林基金鲲鹏6号', '波克宏观配置1号'],
}

for cat, cat_items in categories.items():
    print(f"**{cat}**")
    print("| 产品名称 | 近一周 | 近一月 |")
    print("|----------|--------|--------|")
    for item in result:
        if item['产品名称'] in cat_items:
            w = f"{item['近一周']:+.2%}" if item['近一周'] is not None else "无数据"
            m = f"{item['近一月']:+.2%}" if item['近一月'] is not None else "无数据"
            print(f"| {item['产品名称']} | {w} | {m} |")
    print()

df = pd.DataFrame(result)
df.to_csv('/Users/huangqingmeng/.openclaw/workspace/returns_20260327_corrected.csv', index=False, encoding='utf-8-sig')
print(f"\n已保存修正后数据到: returns_20260327_corrected.csv")
