#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundCompanyPrice

appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 正仁股票择时一期，reg_code=SARD76，price_type=2（团队净值）
req = FundCompanyPrice(appid, appkey)
req.set_params(reg_code='SARD76', start_date='2025-12-20', end_date='2026-03-31')
res = req.do_request(use_df=False)

print("=== 正仁股票择时一期(SARD76) 原始数据 ===")
print(f"共获取到 {len(res)} 条数据\n")
print("日期      |   净值   ")
print("----------|---------")
for item in res:
    date = item['price_date']
    nav = item['nav']
    print(f"{date} | {nav}")

print("\n调试信息:")
print(req.get_debug_info())
