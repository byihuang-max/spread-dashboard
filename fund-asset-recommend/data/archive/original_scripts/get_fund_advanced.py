#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundAdvancedList

# 你的API信息
appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 创建请求对象 - 根据团队策略获取基金列表，type=3
req = FundAdvancedList(appid, appkey)
# strategy_one可以选不限，type=3
req.set_params(strategy_one='不限', strategy_two='不限', strategy_three='不限', type_=3,
               page=1, pagesize=50, order_by='price_date', order=1, fund_state=1)

# 发起请求
res = req.do_request(use_df=True)
print("=== 高级基金列表（type=3）===")
print(res)
print("\n=== 调试信息 ===")
print(req.get_debug_info())
