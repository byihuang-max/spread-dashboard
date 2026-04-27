#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FundCompanyPrice

appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 测试涌泉君安三号，它之前有数据，试试更早的开始日期
req = FundCompanyPrice(appid, appkey)
req.set_params(reg_code='SZM385', start_date='2025-01-01', end_date='2026-03-27')
res = req.do_request(use_df=False)

print(f"拿到 {len(res)} 条数据")
if res:
    print("\n最后5条：")
    for item in res[-5:]:
        print(item)
