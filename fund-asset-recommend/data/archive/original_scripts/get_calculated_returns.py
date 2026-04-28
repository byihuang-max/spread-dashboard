#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import pandas as pd

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundMultiPrice

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

# 我们需要获取这两个日期的净值
target_dates = ['2026-03-20', '2026-03-27']

# 批量查询
reg_codes = [f['reg_code'] for f in funds]
req = FundMultiPrice(appid, appkey)
# FundMultiPrice接受逗号分隔的多个reg_code，最多40只，正好够我们20只
reg_codes_str = ','.join(reg_codes)
req.set_params(reg_code=reg_codes_str)

res = req.do_request(use_df=False)

if not res:
    print("获取数据失败")
    print(req.get_debug_info())
    sys.exit(1)

# 整理数据
data = []
for fund in funds:
    name = fund['name']
    reg_code = fund['reg_code']
    # 查找对应的数据
    item = next((x for x in res if x['reg_code'] == reg_code), None)
    if item and 'price_list' in item:
        price_dict = {p['price_date']: float(p['net_value']) for p in item['price_list']}
        nav_20 = price_dict.get('2026-03-20')
        nav_27 = price_dict.get('2026-03-27')
        # 计算近一周: 3.27 / 3.20 - 1
        weekly = (nav_27 / nav_20 - 1) if nav_20 and nav_27 else None
        data.append({
            '产品名称': name,
            '净值_3.20': nav_20,
            '净值_3.27': nav_27,
            '近一周(3.20-3.27)': weekly
        })
    else:
        data.append({
            '产品名称': name,
            '净值_3.20': None,
            '净值_3.27': None,
            '近一周(3.20-3.27)': None
        })

# 转成DataFrame输出
df = pd.DataFrame(data)
# 格式化成百分比
print("=== 3月20日-3月27日 近一周收益计算结果 ===\n")
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}" if x is not None else "N/A"))

# 保存到CSV
df.to_csv('/Users/huangqingmeng/.openclaw/workspace/weekly_returns_20260327.csv', index=False, encoding='utf-8-sig')
print("\n已保存到 weekly_returns_20260327.csv")
