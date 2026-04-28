# -*- coding: utf-8 -*-
import sys
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundMultiCompanyPrice

APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# GAMT核心资产前5只基金
fund_codes = ["SATL65", "SCJ476", "SARZ77", "SBCA75", "VB166A"]

req = FundMultiCompanyPrice(APP_ID, APP_KEY)
# 多个基金用逗号分隔
req.set_params(reg_code=",".join(fund_codes))

res = req.do_request(use_df=False)
print(f"批量获取 {len(fund_codes)} 只基金净值：")
print(res)
print("\n调试信息：")
print(req.get_debug_info())
