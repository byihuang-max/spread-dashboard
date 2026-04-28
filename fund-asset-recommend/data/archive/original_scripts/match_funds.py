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

# 我们要找的20只产品名称
target_funds = [
    "顽岩量化选股1号",
    "正仁股票择时一期",
    "正仁双创择时一号",
    "瀚鑫纸鸢量化优选",
    "积沐领航者",
    "太衍光年中证2000指数增强",
    "时间序列红利增强",
    "赢仕安盈二号",
    "具力芒种1号",
    "旌安思源1号",
    "创世纪顾锝灵活多策略",
    "立心-私募学院菁英353号",
    "翔云50二号A类",
    "特夫郁金香全量化",
    "铭跃行远均衡一号",
    "碳硅1号",
    "涌泉君安三号",
    "海鹏扬帆",
    "格林基金鲲鹏6号",
    "波克宏观配置1号"
]

# 获取第一页数据
req = FofSubFundTrackList(appid, appkey)
req.set_params(type_=3, page=1, page_size=100)
res = req.do_request(use_df=False)

matched = []
not_matched = []

if res and 'list' in res:
    for fund in res['list']:
        name = fund['fund_short_name']
        reg_code = fund['register_number']
        # 检查是否匹配我们的目标产品
        for target in target_funds:
            if target in name or name in target:
                matched.append({
                    'target_name': target,
                    'found_name': name,
                    'register_number': reg_code,
                    'price_type': fund['price_type']
                })
                break
    
    # 找没找到的，继续翻页
    matched_names = [m['target_name'] for m in matched]
    not_matched = [t for t in target_funds if t not in matched_names]
    
    if not_matched and res.get('count', 0) > 100:
        page = 2
        while not_matched and page * 100 <= res.get('count', 0):
            print(f"正在翻页第{page}页，还剩{len(not_matched)}只没找到...")
            req = FofSubFundTrackList(appid, appkey)
            req.set_params(type_=3, page=page, page_size=100)
            page_res = req.do_request(use_df=False)
            if page_res and 'list' in page_res:
                for fund in page_res['list']:
                    name = fund['fund_short_name']
                    reg_code = fund['register_number']
                    for target in not_matched:
                        if target in name or name in target:
                            matched.append({
                                'target_name': target,
                                'found_name': name,
                                'register_number': reg_code,
                                'price_type': fund['price_type']
                            })
                            not_matched.remove(target)
                            break
            page += 1

print("=== 匹配结果 ===")
print(f"已找到: {len(matched)} 只")
print(f"未找到: {len(not_matched)} 只")
print()
for m in sorted(matched, key=lambda x: target_funds.index(x['target_name'])):
    print(f"{m['target_name']}: {m['register_number']}")

print("\n未找到:")
for nm in not_matched:
    print(f"- {nm}")
