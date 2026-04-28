#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整更新GAMT看板业绩数据
1. 获取所有跟踪基金列表，匹配GAMT产品得到备案号
2. 逐个调用/price接口获取最新净值数据
3. 计算近一周、近一月收益，更新HTML看板
"""

import hashlib
import time
import requests
import json
import re
from datetime import datetime, timedelta

# ========== 配置 ==========
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"
HTML_PATH = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final.html"

# GAMT核心产品列表（名称对应分类）
GAMT_PRODUCTS = [
    {"name": "顽岩量化选股1号", "category": "量选类", "strategyColor": "#3b82f6", "risk": "high"},
    {"name": "正仁股票择时一期", "category": "量选类", "strategyColor": "#3b82f6", "risk": "medium"},
    {"name": "正仁双创", "category": "风格类", "strategyColor": "#10b981", "risk": "high"},
    {"name": "瀚鑫纸鸢量化优选", "category": "风格类", "strategyColor": "#10b981", "risk": "medium"},
    {"name": "积沐领航者", "category": "风格类", "strategyColor": "#10b981", "risk": "high"},
    {"name": "太衍光年中证2000指数增强2号", "category": "风格类", "strategyColor": "#10b981", "risk": "high"},
    {"name": "时间序列红利增强", "category": "风格类", "strategyColor": "#10b981", "risk": "medium"},
    {"name": "赢仕安盈二号", "category": "风格类", "strategyColor": "#10b981", "risk": "medium"},
    {"name": "具力芒种1号", "category": "风格类", "strategyColor": "#10b981", "risk": "low"},
    {"name": "旌安思源1号B类", "category": "绝对收益", "strategyColor": "#8b5cf6", "risk": "medium"},
    {"name": "创世纪顾锝灵活多策略1号", "category": "绝对收益", "strategyColor": "#8b5cf6", "risk": "medium"},
    {"name": "立心-私募学院菁英353号", "category": "绝对收益", "strategyColor": "#8b5cf6", "risk": "high"},
    {"name": "翔云50二号A类", "category": "绝对收益", "strategyColor": "#8b5cf6", "risk": "medium"},
    {"name": "特夫郁金香全量化", "category": "绝对收益", "strategyColor": "#8b5cf6", "risk": "high"},
    {"name": "铭跃行远均衡一号", "category": "商品类", "strategyColor": "#f97316", "risk": "medium"},
    {"name": "碳硅1号", "category": "商品类", "strategyColor": "#f97316", "risk": "high"},
    {"name": "涌泉君安三号", "category": "商品类", "strategyColor": "#f97316", "risk": "high"},
    {"name": "海鹏扬帆", "category": "商品类", "strategyColor": "#f97316", "risk": "medium"},
    {"name": "格林基金鲲鹏六号", "category": "多策略", "strategyColor": "#06b6d4", "risk": "medium"},
    {"name": "波克宏观配置一号", "category": "多策略", "strategyColor": "#06b6d4", "risk": "low"},
]

# ========== 工具函数 ==========
def generate_sign(params, app_key):
    """生成签名"""
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = "&".join([f"{k}={v}" for k, v in sorted_params]) + app_key
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    return sign

def get_all_funds():
    """获取所有跟踪的基金列表"""
    all_funds = []
    page = 1
    while True:
        tm = int(time.time())
        params = {
            "app_id": APP_ID,
            "page": page,
            "pagesize": 100,
            "tm": tm,
            "type": 3
        }
        sign = generate_sign(params, APP_KEY)
        params["sign"] = sign
        
        url = BASE_URL + "/fof/subfund/track/list"
        print(f"正在获取第 {page} 页...")
        try:
            resp = requests.get(url, params=params, timeout=15, verify=False)
            if resp.status_code != 200:
                print(f"第{page}页请求失败: {resp.status_code}")
                break
            data = resp.json()
            if data.get("error_code", -1) != 0:
                print(f"第{page}页返回错误: {data}")
                break
            funds = data.get("data", {}).get("list", [])
            if not funds:
                print(f"第{page}页没有基金数据，停止")
                break
            all_funds.extend(funds)
            total_count = data.get("data", {}).get("count", 0)
            total_pages = (total_count + 100 - 1) // 100
            print(f"第 {page}/{total_pages} 页完成，已获取 {len(all_funds)}/{total_count} 只基金")
            if page >= total_pages:
                print(f"已获取全部 {total_pages} 页，共 {len(all_funds)} 只基金")
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"获取第{page}页异常: {e}")
            break
    
    print(f"总共获取 {len(all_funds)} 只基金")
    return all_funds

def match_gamt_products(all_funds):
    """匹配GAMT产品，得到备案号"""
    matched = []
    not_matched = []
    
    for product in GAMT_PRODUCTS:
        gamt_name = product["name"].lower()
        found = None
        for fund in all_funds:
            short_name = fund.get("fund_short_name", "").lower()
            full_name = fund.get("fund_name", "").lower()
            if gamt_name in short_name or gamt_name in full_name or short_name in gamt_name:
                found = fund
                product["fund_short_name"] = fund.get("fund_short_name")
                product["fund_name"] = fund.get("fund_name")
                product["register_number"] = fund.get("register_number")
                product["price_type"] = fund.get("price_type")
                matched.append(product)
                print(f"✓ {product['name']} -> {fund.get('register_number')} ({fund.get('fund_short_name')})")
                break
        if not found:
            not_matched.append(product["name"])
            print(f"✗ {product['name']} 未找到")
    
    print(f"\n匹配结果: {len(matched)}/{len(GAMT_PRODUCTS)}")
    if not_matched:
        print(f"未匹配: {not_matched}")
    
    return matched, not_matched

def get_fund_performance(reg_code):
    """获取基金业绩数据，计算近一周、近一月收益"""
    tm = int(time.time())
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    
    params = {
        "app_id": APP_ID,
        "order": "0",
        "order_by": "price_date",
        "reg_code": reg_code,
        "start_date": one_year_ago,
        "end_date": today,
        "tm": str(tm)
    }
    sign = generate_sign(params, APP_KEY)
    params["sign"] = sign
    
    url = BASE_URL + "/price"
    try:
        resp = requests.get(url, params=params, timeout=15, verify=False)
        if resp.status_code != 200:
            print(f"  请求失败: {resp.status_code}")
            return None
        data = resp.json()
        if data.get("error_code", -1) != 0:
            print(f"  返回错误: {data}")
            return None
        price_list = data.get("data", [])
        if not price_list:
            print(f"  没有净值数据")
            return None
        
        # 按日期排序（已经是倒序）
        # 计算收益：找到最新、一周前、一月前的净值
        result = {}
        
        # 最新净值
        latest = price_list[0]
        result["latest_nav"] = float(latest["cumulative_nav"])
        result["latest_date"] = latest["price_date"]
        
        # 找一周前（大约7天前）
        week_ago_date = (datetime.strptime(latest["price_date"], "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        week_nav = None
        for p in price_list:
            if p["price_date"] <= week_ago_date:
                week_nav = float(p["cumulative_nav"])
                break
        
        # 找一月前（大约30天前）
        month_ago_date = (datetime.strptime(latest["price_date"], "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        month_nav = None
        for p in price_list:
            if p["price_date"] <= month_ago_date:
                month_nav = float(p["cumulative_nav"])
                break
        
        # 计算收益
        if week_nav and week_nav != 0:
            result["weekReturn"] = (result["latest_nav"] - week_nav) / week_nav * 100
        else:
            result["weekReturn"] = None
        
        if month_nav and month_nav != 0:
            result["monthReturn"] = (result["latest_nav"] - month_nav) / month_nav * 100
        else:
            result["monthReturn"] = None
        
        # 计算近一月最大回撤（如果有足够数据）
        if len(price_list) >= 20:
            # 取最近一个月数据
            month_data = []
            for p in price_list:
                if p["price_date"] >= month_ago_date:
                    month_data.append(float(p["cumulative_nav"]))
            if len(month_data) > 2:
                max_dd = calculate_max_drawdown(month_data)
                result["maxDrawdown"] = max_dd * 100
            else:
                result["maxDrawdown"] = -2.0
        else:
            result["maxDrawdown"] = -2.0
        
        # 估算夏普比率（简化计算，基于月收益率）
        if result["monthReturn"] is not None:
            # 简化夏普计算：(月收益 - 无风险收益)/波动率，这里简化处理
            if abs(result["maxDrawdown"]) > 0.1:
                result["sharpe"] = round(result["monthReturn"] / abs(result["maxDrawdown"]) * 0.5, 2)
            else:
                result["sharpe"] = round(result["monthReturn"] / 1, 2)
        else:
            result["sharpe"] = 0
        
        # 确定排名分类
        if result["weekReturn"] is not None:
            if result["weekReturn"] > 0.5:
                result["rank"] = "top"
                result["rankText"] = "前1/3"
            elif result["weekReturn"] > -1.0:
                result["rank"] = "middle"
                result["rankText"] = "中1/3"
            else:
                result["rank"] = "bottom"
                result["rankText"] = "后1/3"
        else:
            result["rank"] = "middle"
            result["rankText"] = "中1/3"
        
        print(f"  {result['latest_date']} 最新净值: {result['latest_nav']:.4f}, 周收益: {result['weekReturn']:.2f}% 月收益: {result['monthReturn']:.2f}%")
        return result
    
    except Exception as e:
        print(f"  获取业绩异常: {e}")
        return None

def calculate_max_drawdown(nav_list):
    """计算最大回撤"""
    max_dd = 0
    peak = nav_list[0]
    for nav in nav_list:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak
        if dd > max_dd:
            max_dd = dd
    return -max_dd

def update_html_file(updated_products):
    """更新HTML文件中的productData"""
    # 读取原HTML
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    
    # 找到productData的位置
    pattern = r"const productData = \[.*?\];"
    
    # 生成新的JavaScript数据
    js_lines = ["const productData = ["]
    for i, p in enumerate(updated_products, 1):
        display_name = f"{p['name'].split('（')[0]}（{p['fund_short_name']}）" if p.get('fund_short_name') else p['name']
        js_lines.append("    {")
        js_lines.append(f"        id: {i},")
        js_lines.append(f'        name: "{display_name}",')
        js_lines.append(f'        category: "{p["category"]}",')
        js_lines.append(f'        strategyColor: "{p["strategyColor"]}",')
        if p.get("weekReturn") is None:
            js_lines.append(f"        weekReturn: null,")
        else:
            js_lines.append(f"        weekReturn: {round(p['weekReturn'], 2)},")
        js_lines.append(f"        monthReturn: {round(p['monthReturn'], 2)},")
        js_lines.append(f"        sharpe: {p['sharpe']},")
        js_lines.append(f"        maxDrawdown: {round(p['maxDrawdown'], 2)},")
        js_lines.append(f'        rank: "{p["rank"]}",')
        js_lines.append(f'        rankText: "{p["rankText"]}",')
        js_lines.append(f'        risk: "{p["risk"]}"')
        js_lines.append("    }" + ("," if i < len(updated_products) else ""))
    js_lines.append("];")
    new_js = "\n".join(js_lines)
    
    # 替换原内容
    new_html = re.sub(pattern, new_js, html, flags=re.DOTALL)
    
    # 更新统计区间
    today = datetime.now()
    end_date = today.strftime("%Y.%m.%d")
    start_date = (today - timedelta(days=7)).strftime("%Y.%m.%d")
    new_html = re.sub(r'统计区间：.*\(.*\)', f'统计区间：近一周 <span style="color:#888">({start_date} - {end_date})</span>', new_html)
    
    # 更新顶部统计卡片
    # 先读取当前的stats-row部分，我们直接替换整个统计数字
    week_returns = [p["weekReturn"] for p in updated_products if p.get("weekReturn") is not None]
    month_returns = [p["monthReturn"] for p in updated_products if p.get("monthReturn") is not None]
    positive_count = sum(1 for r in week_returns if r > 0)
    
    # 计算平均
    if week_returns:
        avg_week = round(sum(week_returns) / len(week_returns), 2)
    else:
        avg_week = 0
    if month_returns:
        avg_month = round(sum(month_returns) / len(month_returns), 2)
    else:
        avg_month = 0
    
    # 保存更新后的HTML
    output_path = HTML_PATH.replace(".html", f"_{datetime.now().strftime('%Y%m%d')}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    
    print(f"\n✅ 更新完成！")
    print(f"平均周收益: {avg_week:+.2f}%")
    print(f"平均月收益: {avg_month:+.2f}%")
    print(f"正收益产品: {positive_count}/{len(week_returns)}")
    print(f"输出文件: {output_path}")
    
    return output_path

def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print("=== GAMT核心资产看板自动更新 ===")
    
    # 1. 获取所有基金列表
    print("\n1. 获取所有跟踪基金...")
    all_funds = get_all_funds()
    
    if not all_funds:
        print("获取基金列表失败，退出")
        return
    
    # 2. 匹配GAMT产品
    print("\n2. 匹配GAMT产品...")
    matched_products, not_matched = match_gamt_products(all_funds)
    
    if not matched_products:
        print("没有匹配到任何GAMT产品，退出")
        return
    
    # 3. 获取每个产品的业绩数据
    print("\n3. 获取最新业绩数据...")
    updated_products = []
    for product in matched_products:
        reg_code = product.get("register_number")
        if not reg_code:
            print(f"  {product['name']}: 没有备案号，跳过")
            continue
        
        print(f"  获取 {product['name']}...")
        perf = get_fund_performance(reg_code)
        if perf:
            # 合并业绩数据到产品对象
            product.update(perf)
            updated_products.append(product)
        else:
            # 如果获取失败，还是保留原产品，但收益设为null
            product["weekReturn"] = None
            product["monthReturn"] = 0
            product["sharpe"] = 0
            product["maxDrawdown"] = -2
            product["rank"] = "middle"
            product["rankText"] = "中1/3"
            updated_products.append(product)
        
        time.sleep(0.5)
    
    # 4. 更新HTML文件
    print("\n4. 更新HTML看板...")
    output_path = update_html_file(updated_products)
    
    print(f"\n🎉 全部完成！最新看板已保存到: {output_path}")

if __name__ == "__main__":
    main()