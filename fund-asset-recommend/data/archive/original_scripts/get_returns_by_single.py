#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import pandas as pd
import time

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundPrice

# 你的API信息
appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 20只产品信息
funds = [
    {"name": "顽岩量化选股1号", "reg_code": "SATW62"},
    {"name": "正仁股票择时一期", "reg_code": "SARD76"},
    {"name": "正仁双创择时一号", "reg_code": "SXG834"},
    {"name": "瀚鑫纸鸢量化优选", "reg_code": "SZC020"},
    {"name": "积沐领航者", "reg_code": "SAJJ90"},
    {"name": "太衍光年中证2000指数增强", "reg_code": "SBDC67"},
    {"name": "时间序列红利增强", "reg_code": "SSV122"},
    {"name": "赢仕安盈二号", "reg_code": "SLQ349"},
    {"name": "具力芒种1号", "reg_code": "STE836"},
    {"name": "旌安思源1号B类", "reg_code": "ST6924"},
    {"name": "创世纪顾锝灵活多策略", "reg_code": "SBCA75"},
    {"name": "立心-私募学院菁英353号", "reg_code": "SCJ476"},
    {"name": "翔云50二号A类", "reg_code": "SY6829"},
    {"name": "特夫郁金香全量化", "reg_code": "SQX078"},
    {"name": "铭跃行远均衡一号", "reg_code": "SVZ009"},
    {"name": "碳硅1号", "reg_code": "SXJ836"},
    {"name": "涌泉君安三号", "reg_code": "SZM385"},
    {"name": "海鹏扬帆", "reg_code": "SSR379"},
    {"name": "格林基金鲲鹏6号", "reg_code": "SVZ638"},
    {"name": "波克宏观配置1号", "reg_code": "SARZ77"},
]

# 我们需要的日期
date_20 = '2026-03-20'
date_27 = '2026-03-27'
date_end_feb = '2026-02-29'  # 二月末，用于计算近一月

result = []

for i, fund in enumerate(funds):
    name = fund['name']
    reg_code = fund['reg_code']
    print(f"正在查询 ({i+1}/{len(funds)}): {name} [{reg_code}]")
    
    req = FundPrice(appid, appkey)
    req.set_params(reg_code=reg_code, start_date='2026-02-01', end_date='2026-03-27')
    res = req.do_request(use_df=False)
    
    nav_20 = None
    nav_27 = None
    nav_feb = None
    
    if res:
        # 查找对应日期的净值
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
        '净值_3.20': nav_20,
        '净值_3.27': nav_27,
        '净值_2.29': nav_feb,
        '近一周(3.20-3.27)': weekly_return,
        '近一月(截至3.27)': monthly_return
    })
    
    # 稍微休息一下，避免请求过快
    time.sleep(0.5)

# 输出结果
df = pd.DataFrame(result)
print("\n\n=== 计算结果：3月20日 - 3月27日 ===")
print("\n| 产品名称 | 近一周 | 近一月 |")
print("|----------|--------|--------|")
for _, row in df.iterrows():
    w = f"{row['近一周(3.20-3.27)']:.2%}" if row['近一周(3.20-3.27)'] is not None else "N/A"
    m = f"{row['近一月(截至3.27)']:.2%}" if row['近一月(截至3.27)'] is not None else "N/A"
    print(f"| {row['产品名称']} | {w} | {m} |")

# 保存到CSV
df.to_csv('/Users/huangqingmeng/.openclaw/workspace/returns_20260327.csv', index=False, encoding='utf-8-sig')
print(f"\n已保存完整数据到: /Users/huangqingmeng/.openclaw/workspace/returns_20260327.csv")
