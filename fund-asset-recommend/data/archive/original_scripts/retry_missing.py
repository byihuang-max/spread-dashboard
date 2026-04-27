# -*- coding: utf-8 -*-
"""
重新尝试获取瀚鑫纸鸢量化优选和时间序列红利增强1号
"""
import sys
import pandas as pd
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundCompanyPrice, FundPrice, FundMultiCompanyPrice

APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# 需要重试的两只
missing_funds = [
    {"name": "瀚鑫纸鸢量化优选", "code": "SZC020", "strategy": "股票多头-量化选股"},
    {"name": "时间序列红利增强1号", "code": "SSV122", "strategy": "股票多头-红利指增"},
]

print("=== 重试获取缺失的两只基金 ===")
print("\n1. 尝试团队净值接口 FundCompanyPrice:")

for fund in missing_funds:
    print(f"\n--- {fund['name']} ({fund['code']}) ---")
    req = FundCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund["code"], start_date="2025-01-01")
    data = req.do_request(use_df=False)
    print(f"获取到 {len(data)} 条数据")
    if data:
        print(f"最新数据: {data[-1]}")
    else:
        print(f"调试信息: {req.get_debug_info()}")

print("\n\n2. 尝试平台净值接口 FundPrice:")

for fund in missing_funds:
    print(f"\n--- {fund['name']} ({fund['code']}) ---")
    req = FundPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund["code"], start_date="2025-01-01")
    data = req.do_request(use_df=False)
    print(f"获取到 {len(data)} 条数据")
    if data:
        print(f"最新数据: {data[-1]}")
    else:
        print(f"调试信息: {req.get_debug_info()}")

print("\n\n3. 尝试批量接口 FundMultiCompanyPrice:")

codes = [f["code"] for f in missing_funds]
code_str = ",".join(codes)
req = FundMultiCompanyPrice(APP_ID, APP_KEY)
req.set_params(reg_code=code_str)
data = req.do_request(use_df=False)
print(f"获取到 {len(data)} 条数据")
for item in data:
    print(item)
