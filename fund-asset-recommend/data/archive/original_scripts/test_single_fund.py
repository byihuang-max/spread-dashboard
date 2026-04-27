# -*- coding: utf-8 -*-
import sys
# 添加SDK路径
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

# 引入请求类
from fof99 import FundCompanyPrice

# 配置信息
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# 测试第一只基金：正仁股票择时四期 SATL65
fund_code = "SATL65"
start_date = "2026-01-01"

# 创建请求对象
req = FundCompanyPrice(APP_ID, APP_KEY)
# 设置请求参数
req.set_params(reg_code=fund_code, start_date=start_date, order_by='price_date', order=1)
# 发起请求
res = req.do_request(use_df=True)

# 输出结果
print(f"获取基金 {fund_code} 净值数据：")
print(res)
print("\n调试信息：")
print(req.get_debug_info())
