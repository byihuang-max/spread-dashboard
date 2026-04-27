#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新GAMT核心资产看板数据
自动从火富牛API获取最新业绩数据，更新HTML看板
"""

import hashlib
import time
import requests
from urllib.parse import urlencode

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
    """生成签名：参数key升序排序，拼接key=value，最后拼接密钥，计算md5"""
    # 移除sign参数
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    # 拼接
    sign_str = "&".join([f"{k}={v}" for k, v in sorted_params]) + app_key
    # md5
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    return sign

def get_fund_list(page=1, pagesize=10, type_=1):
    """获取基金列表"""
    tm = int(time.time())
    params = {
        "app_id": APP_ID,
        "page": page,
        "pagesize": pagesize,
        "tm": tm,
        "type": type_
    }
    sign = generate_sign(params, APP_KEY)
    params["sign"] = sign
    
    url = BASE_URL + API_PATH
    print(f"请求URL: {url}?{urlencode(params)}")
    try:
        response = requests.get(url, params=params, timeout=10, verify=False)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"请求失败: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
            return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None

def get_all_funds():
    """获取所有基金"""
    # 先获取第一页看总数
    first_page = get_fund_list(page=1, pagesize=10)
    if not first_page or first_page.get("error_code", -1) != 0:
        print(f"获取第一页失败: {first_page}")
        return []
    
    total_count = first_page.get("data", {}).get("count", 0)
    print(f"总基金数: {total_count}")
    
    all_funds = []
    all_funds.extend(first_page.get("data", {}).get("list", []))
    
    # 计算总页数
    total_pages = (total_count + 10 - 1) // 10
    print(f"总页数: {total_pages}")
    
    # 获取剩余页
    for page in range(2, total_pages + 1):
        print(f"获取第 {page} 页...")
        page_data = get_fund_list(page=page, pagesize=10)
        if page_data and page_data.get("error_code", -1) == 0:
            funds = page_data.get("data", {}).get("list", [])
            all_funds.extend(funds)
        time.sleep(0.5)
    
    print(f"共获取 {len(all_funds)} 只基金")
    return all_funds

def match_gamt_products(all_funds):
    """匹配GAMT产品"""
    matched = []
    not_matched = []
    
    for gamt_name in GAMT_PRODUCTS:
        found = False
        for fund in all_funds:
            fund_short = fund.get("fund_short_name", "")
            fund_full = fund.get("fund_name", "")
            # 模糊匹配
            if gamt_name in fund_short or gamt_name in fund_full or fund_short in gamt_name:
                matched.append({
                    "gamt_name": gamt_name,
                    "fund_info": fund
                })
                found = True
                print(f"✓ 匹配成功: {gamt_name} -> {fund_short}")
                break
        if not found:
            not_matched.append(gamt_name)
            print(f"✗ 未匹配: {gamt_name}")
    
    print(f"\n匹配结果: 成功 {len(matched)} 只, 未匹配 {len(not_matched)} 只")
    if not_matched:
        print(f"未匹配列表: {not_matched}")
    
    return matched, not_matched

def update_html_data(matched_data, html_path="/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final.html"):
    """更新HTML中的产品数据
    这里我们需要获取最新净值收益数据
    API返回的list里只有基本信息，如果需要收益数据可能需要另一个接口
    先输出获取到的信息，看一下有哪些字段
    """
    print("\n获取到的基金信息字段:")
    if matched_data:
        first = matched_data[0]["fund_info"]
        for key, value in first.items():
            print(f"  {key}: {value}")
    
    # 保存匹配结果到JSON
    import json
    with open("/Users/huangqingmeng/.openclaw/workspace/gamt_matched_data.json", "w", encoding="utf-8") as f:
        json.dump(matched_data, f, ensure_ascii=False, indent=2)
    print(f"\n匹配数据已保存到 gamt_matched_data.json")
    
    return matched_data

def main():
    print("=== GAMT核心资产数据更新 ===")
    print(f"配置APP_ID: {APP_ID}")
    
    print("\n1. 获取所有基金列表...")
    all_funds = get_all_funds()
    
    if not all_funds:
        print("获取基金列表失败")
        return
    
    print("\n2. 匹配GAMT产品...")
    matched, not_matched = match_gamt_products(all_funds)
    
    print("\n3. 保存匹配结果...")
    update_html_data(matched)
    
    print("\n完成！请检查匹配结果，如果需要进一步获取收益数据，请确认是否需要调用其他接口。")

if __name__ == "__main__":
    main()
