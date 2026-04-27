# -*- coding: utf-8 -*-
import sys
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FofSubFundTrackList

APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

req = FofSubFundTrackList(APP_ID, APP_KEY)
req.set_params(type_=1, page=1, page_size=50)

res = req.do_request(use_df=True)
print("团队跟踪基金列表：")
print(res)
print("\n调试信息：")
print(req.get_debug_info())
