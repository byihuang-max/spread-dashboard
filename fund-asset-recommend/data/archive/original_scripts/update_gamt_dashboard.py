# -*- coding: utf-8 -*-
"""
使用火富牛官方SDK更新GAMT核心资产Dashboard数据
"""
import sys
import pandas as pd
import json
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundMultiCompanyPrice

# 配置
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# GAMT核心基金列表
GAMT_FUNDS = [
    {"name": "正仁股票择时四期", "code": "SATL65", "strategy": "股票多头-300指增"},
    {"name": "立心-私募学院菁英353号", "code": "SCJ476", "strategy": "股票多头-主观多头"},
    {"name": "波克宏观配置1号", "code": "SARZ77", "strategy": "多资产-宏观策略"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75", "strategy": "股票多头-2000指增"},
    {"name": "翔云50二号A类", "code": "VB166A", "strategy": "股票多头-另类多头"},
    {"name": "创世纪顾锝灵活多策略1号", "code": "SBDC67", "strategy": "股票多头"},
    {"name": "瀚鑫纸鸢量化优选", "code": "SZC020", "strategy": "股票多头-量化选股"},
    {"name": "碳硅1号", "code": "SXJ836", "strategy": "期货策略-主观期货"},
    {"name": "顽岩量化选股1号", "code": "SATW62", "strategy": "股票多头-量化选股"},
    {"name": "正仁股票择时一期", "code": "SARD76", "strategy": "股票多头-择时择股"},
    {"name": "格林基金鲲鹏6号", "code": "SVZ638", "strategy": "债券策略-债券复合"},
    {"name": "赢仕安盈二号", "code": "SLQ349", "strategy": "股票多头-可转债"},
    {"name": "具力芒种1号", "code": "STE836", "strategy": "股票多头-可转债"},
    {"name": "时间序列红利增强1号", "code": "SSV122", "strategy": "股票多头-红利指增"},
    {"name": "积沐领航者", "code": "SAJJ91", "strategy": "股票多头-1000指增"},
    {"name": "旌安思源1号B类", "code": "AEU46B", "strategy": "股票多头-另类多头"},
    {"name": "涌泉君安三号", "code": "SZM385", "strategy": "期货策略-量化期货"},
    {"name": "铭跃行远均衡一号", "code": "SVZ009", "strategy": "期货策略-量化期货"},
    {"name": "正仁双创择时一号", "code": "SXG834", "strategy": "股票多头-1000指增"},
    {"name": "特夫郁金香全量化", "code": "SQX078", "strategy": "股票对冲-打板"},
    {"name": "海鹏扬帆", "code": "SSR379", "strategy": "期货策略-主观期货"},
]

def fetch_latest_nav():
    """批量获取最新净值"""
    print("正在批量获取最新净值...")
    
    # 分批获取，每批最多40只，我们只有21只，一次搞定
    codes = [f["code"] for f in GAMT_FUNDS]
    code_str = ",".join(codes)
    
    req = FundMultiCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=code_str)
    data = req.do_request(use_df=False)
    
    print(f"获取到 {len(data)} 只基金的最新数据")
    print("调试信息:", req.get_debug_info())
    
    # 转成字典方便查找
    result = {}
    for item in data:
        result[item["reg_code"]] = item
    
    return result, req.get_debug_info()

def update_html_dashboard(template_path, output_path, latest_nav):
    """更新HTML看板中的最新数据"""
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 准备更新数据，合并最新净值
    updated_funds = []
    for fund in GAMT_FUNDS:
        code = fund["code"]
        fund_data = fund.copy()
        if code in latest_nav:
            fund_data["latest_nav"] = latest_nav[code]["nav"]
            fund_data["latest_date"] = latest_nav[code]["price_date"]
            fund_data["daily_change"] = latest_nav[code]["price_change"] * 100  # 转成百分比
        else:
            fund_data["latest_nav"] = None
            fund_data["latest_date"] = None
            fund_data["daily_change"] = None
        
        updated_funds.append(fund_data)
    
    # 统计
    has_data = sum(1 for f in updated_funds if f["latest_nav"] is not None)
    print(f"更新完成: {has_data}/{len(updated_funds)} 只基金有最新数据")
    
    # 将数据转为JSON插入到HTML中
    # 查找现有的数据占位符或插入点
    data_json = json.dumps(updated_funds, ensure_ascii=False, indent=2)
    
    # 这里我们需要找到或创建JavaScript数据变量
    search_text = "const fundData = "
    if search_text in html:
        # 替换现有数据
        new_html = html.split(search_text)[0] + search_text + data_json + ";" + html.split(";")[1].split("\n", 1)[1]
    else:
        # 如果找不到，在头部插入
        new_html = html.replace("<head>", f"<head>\n<script>\nconst fundData = {data_json};\n</script>")
    
    # 保存新HTML
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"已保存更新后的看板到: {output_path}")
    return output_path

def main():
    print("=== 更新GAMT Dashboard数据 ===")
    
    # 1. 获取最新净值
    latest_nav, debug = fetch_latest_nav()
    
    # 2. 更新HTML
    template_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final.html"
    output_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final_20260329.html"
    
    result_path = update_html_dashboard(template_path, output_path, latest_nav)
    
    # 3. 输出结果
    print("\n=== 最新数据 ===")
    for code, nav_data in latest_nav.items():
        name = next(f["name"] for f in GAMT_FUNDS if f["code"] == code)
        print(f"{name}: 净值={nav_data['nav']}, 日涨跌={nav_data['price_change']*100:.2f}%, 日期={nav_data['price_date']}")

if __name__ == "__main__":
    main()
