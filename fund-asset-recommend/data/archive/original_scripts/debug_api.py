#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundPrice

# 测试一下旌安思源，看看返回什么
appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

req = FundPrice(appid, appkey)
req.set_params(reg_code='ST6924', start_date='2026-01-01', end_date='2026-03-27')
res = req.do_request(use_df=False)

print("=== 测试查询 ST6924（旌安思源）返回数据 ===")
print(f"返回条数: {len(res) if res else 0}")
if res:
    print("\n前10条数据:")
    for i, item in enumerate(res[:10]):
        print(item)
print("\n调试信息:")
print(req.get_debug_info())
