#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取全部跟踪基金列表
"""

import hashlib
import time
import requests
import json

# 配置信息
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"
API_PATH = "/fof/subfund/track/list"

# GAMT核心产品列表（需要匹配的产品名称）
GAMT_PRODUCTS = [
    "顽岩量化选股1号",
    "正仁股票择时一期",
    "正仁双创",
    "瀚鑫纸鸢量化优选",
    "积沐领航者",
    "太衍光年中证2000指数增强2号",
    "时间序列红利增强",
    "赢仕安盈二号",
    "具力芒种1号",
    "旌安思源1号B类",
    "创世纪顾锝灵活多策略1号",
    "立心-私募学院菁英353号",
    "翔云50二号A类",
    "特夫郁金香全量化",
    "铭跃行远均衡一号",
    "碳硅1号",
    "涌泉君安三号",
    "海鹏扬帆",
    "格林基金鲲鹏六号",
    "波克宏观配置一号"
]

def generate_sign(params, app_key):
    """生成签名"""
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = "&".join([f"{k}={v}" for k, v in sorted_params]) + app_key
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    return sign

def get_fund_list(page=1, pagesize=20):
    """获取一页基金列表"""
    tm = int(time.time())
    params = {
        "app_id": APP_ID,
        "page": page,
        "pagesize": pagesize,
        "tm": tm,
        "type": 1
    }
    sign = generate_sign(params, APP_KEY)
    params["sign"] = sign
    
    url = BASE_URL + API_PATH
    response = requests.get(url, params=params, timeout=15, verify=False)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"第{page}页请求失败: {response.status_code}")
        return None

def main():
    print("=== 获取全部跟踪基金列表 ===")
    
    # 第一页
    result = get_fund_list(page=1, pagesize=100)
    if not result or result.get("error_code", -1) != 0:
        print(f"获取第一页失败: {result}")
        return
    
    total_count = result.get("data", {}).get("count", 0)
    print(f"总基金数: {total_count}")
    
    all_funds = []
    all_funds.extend(result.get("data", {}).get("list", []))
    
    total_pages = (total_count + 100 - 1) // 100
    print(f"总页数: {total_pages}")
    
    for page in range(2, total_pages + 1):
        print(f"获取第 {page}/{total_pages} 页...")
        result = get_fund_list(page=page, pagesize=20)
        if result and result.get("error_code", -1) == 0:
            funds = result.get("data", {}).get("list", [])
            all_funds.extend(funds)
        time.sleep(0.5)
    
    print(f"\n共获取 {len(all_funds)} 只基金")
    
    # 保存全部数据
    with open("/Users/huangqingmeng/.openclaw/workspace/all_funds.json", "w", encoding="utf-8") as f:
        json.dump(all_funds, f, ensure_ascii=False, indent=2)
    
    # 匹配GAMT产品
    print("\n=== 匹配GAMT产品 ===")
    matched = []
    not_matched = []
    
    for gamt_name in GAMT_PRODUCTS:
        found = None
        for fund in all_funds:
            short_name = fund.get("fund_short_name", "").lower()
            full_name = fund.get("fund_name", "").lower()
            gamt_lower = gamt_name.lower()
            
            # 模糊匹配
            if gamt_lower in short_name or gamt_lower in full_name:
                found = fund
                matched.append({
                    "gamt_name": gamt_name,
                    "fund_info": fund
                })
                print(f"✓ 匹配: {gamt_name} -> {fund.get('fund_short_name')}")
                break
        if not found:
            not_matched.append(gamt_name)
            print(f"✗ 未找到: {gamt_name}")
    
    print(f"\n匹配完成: 成功 {len(matched)} 只, 未找到 {len(not_matched)} 只")
    
    # 保存匹配结果
    with open("/Users/huangqingmeng/.openclaw/workspace/gamt_matched.json", "w", encoding="utf-8") as f:
        json.dump(matched, f, ensure_ascii=False, indent=2)
    
    if not_matched:
        print("\n未找到的产品:")
        for name in not_matched:
            print(f"  - {name}")
    
    print("\n现在需要确认：业绩数据需要调用哪个接口获取？你那边有接口文档说明吗？")
    print("当前API只拿到了基金基本信息，没有周收益、月收益这些业绩数据。")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
