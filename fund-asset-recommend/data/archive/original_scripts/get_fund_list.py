#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# 添加SDK路径
sdk_path = '/Users/huangqingmeng/Downloads/fof99_sdk_2/mall_sdk'
sys.path.append(sdk_path)

from fof99 import FofSubFundTrackList

# 你的API信息
appid = 'hfnogbr8zceiiygdkhw'
appkey = 'c6e941fd6aad65ceede2d780262d11ee'

# 创建请求对象 - 查询type=3的团队基金列表
# 参数名是page_size不是pagesize，之前写错了
req = FofSubFundTrackList(appid, appkey)
req.set_params(type_=3, page=1, page_size=50)  # 取50只，足够包含我们的20只

# 发起请求
res = req.do_request(use_df=True)
print("=== 团队基金列表（type=3）===")
print(res)
print("\n=== 调试信息 ===")
print(req.get_debug_info())
