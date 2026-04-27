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

# 剩下没找到的两只
not_matched = [
    "太衍光年中证2000指数增强",
    "创世纪顾锝灵活多策略"
]

matched = []
start_page = 11
total_count = 1023

for page in range(start_page, (total_count // 100) + 2):
    print(f"正在翻页第{page}页，还剩{len(not_matched)}只没找到...")
    req = FofSubFundTrackList(appid, appkey)
    req.set_params(type_=3, page=page, page_size=100)
    page_res = req.do_request(use_df=False)
    if page_res and 'list' in page_res:
        for fund in page_res['list']:
            name = fund['fund_short_name']
            reg_code = fund['register_number']
            for target in not_matched:
                if target in name or name in target or "太衍" in name or "顾锝" in name:
                    matched.append({
                        'target_name': target,
                        'found_name': name,
                        'register_number': reg_code,
                        'price_type': fund['price_type']
                    })
                    not_matched.remove(target)
                    break
    if not not_matched:
        break

print("\n=== 剩余匹配结果 ===")
for m in matched:
    print(f"{m['target_name']}: {m['register_number']}")

print("\n还没找到:")
for nm in not_matched:
    print(f"- {nm}")
