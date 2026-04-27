# -*- coding: utf-8 -*-
"""
获取每只基金的完整历史净值，计算各阶段收益
"""
import sys
import pandas as pd
import json
from datetime import datetime, timedelta
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundCompanyPrice

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

def get_date_n_days_ago(n_days):
    """获取n天前的日期字符串"""
    date = datetime.now() - timedelta(days=n_days)
    return date.strftime("%Y-%m-%d")

def fetch_fund_history(fund_code, start_date="2026-01-01"):
    """获取单只基金历史净值"""
    req = FundCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund_code, start_date=start_date, order_by='price_date', order=1)
    data = req.do_request(use_df=False)
    return data, req.get_debug_info()

def calculate_returns(history):
    """计算各阶段收益
    近一周、近一月、近三月、今年以来、累计
    """
    if not history or len(history) == 0:
        return None
    
    # 按日期排序
    sorted_history = sorted(history, key=lambda x: x["price_date"])
    if len(sorted_history) == 0:
        return None
    
    latest = sorted_history[-1]
    latest_date = datetime.strptime(latest["price_date"], "%Y-%m-%d")
    
    # 找到各个时间节点的净值
    def find_nav_by_date(days_ago):
        target_date = latest_date - timedelta(days=days_ago)
        # 找最接近目标日期之前的净值
        candidate = None
        for item in sorted_history:
            item_date = datetime.strptime(item["price_date"], "%Y-%m-%d")
            if item_date <= target_date:
                candidate = item
            else:
                break
        if candidate:
            return candidate["cumulative_nav"]
        # 如果找不到，返回最早的
        return sorted_history[0]["cumulative_nav"]
    
    # 节点：近一周(7天)、近一月(30天)、近三月(90天)、今年以来(今年1月1日)
    nav_latest = latest["cumulative_nav"]
    
    returns = {}
    returns["latest_nav"] = latest["nav"]
    returns["latest_cum_nav"] = latest["cumulative_nav"]
    returns["latest_date"] = latest["price_date"]
    returns["daily_change"] = latest.get("price_change", 0) * 100
    
    # 近一周
    if len(sorted_history) >= 5:  # 至少一周数据
        nav_week_ago = find_nav_by_date(7)
        returns["week_return"] = (nav_latest / nav_week_ago - 1) * 100
    else:
        returns["week_return"] = None
    
    # 近一月
    nav_month_ago = find_nav_by_date(30)
    returns["month_return"] = (nav_latest / nav_month_ago - 1) * 100
    
    # 近三月
    nav_3month_ago = find_nav_by_date(90)
    returns["3month_return"] = (nav_latest / nav_3month_ago - 1) * 100
    
    # 今年以来 (从2026-01-01开始)
    jan1_nav = None
    for item in sorted_history:
        if item["price_date"] >= "2026-01-01":
            jan1_nav = sorted_history[0]["cumulative_nav"] if sorted_history[0]["price_date"] >= "2026-01-01" else None
            break
    if jan1_nav is None:
        for item in sorted_history:
            if "2026" in item["price_date"]:
                jan1_nav = item["cumulative_nav"]
                break
    if jan1_nav:
        returns["ytd_return"] = (nav_latest / jan1_nav - 1) * 100
    else:
        returns["ytd_return"] = None
    
    # 累计收益（从第一个净值开始）
    first_nav = sorted_history[0]["cumulative_nav"]
    returns["total_return"] = (nav_latest / first_nav - 1) * 100
    
    # 计算最大回撤（近一年）
    # 简化计算：只算已有数据
    cumulative = [item["cumulative_nav"] for item in sorted_history]
    max_so_far = cumulative[0]
    max_drawdown = 0
    for nav in cumulative:
        if nav > max_so_far:
            max_so_far = nav
        drawdown = (max_so_far - nav) / max_so_far * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    returns["max_drawdown"] = max_drawdown
    
    return returns, sorted_history

def fetch_all_funds_history():
    """获取所有基金历史数据并计算收益"""
    all_results = []
    all_histories = {}
    
    for fund in GAMT_FUNDS:
        print(f"正在获取 {fund['name']} ({fund['code']}) ...")
        history, debug = fetch_fund_history(fund["code"], start_date="2025-01-01")
        
        if not history or len(history) == 0:
            print(f"  ✗ 无数据")
            result = fund.copy()
            result["has_data"] = False
            all_results.append(result)
            continue
        
        print(f"  ✓ 获取到 {len(history)} 条净值数据")
        returns_data, sorted_history = calculate_returns(history)
        all_histories[fund["code"]] = sorted_history
        
        result = fund.copy()
        result.update(returns_data)
        result["has_data"] = True
        all_results.append(result)
        
        # 延时一下，避免请求过快
        import time
        time.sleep(0.2)
    
    # 统计
    has_data_count = sum(1 for r in all_results if r["has_data"])
    print(f"\n获取完成：共 {has_data_count}/{len(all_results)} 只基金获取到数据")
    
    return all_results, all_histories

def update_html_with_returns(template_path, output_path, fund_data):
    """更新HTML中的完整收益数据"""
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 转为JSON
    data_json = json.dumps(fund_data, ensure_ascii=False, indent=2)
    
    # 替换fundData变量
    search_text = "const fundData = "
    if search_text in html:
        parts = html.split(search_text)
        if ";" in parts[1]:
            # 找到第一个分号
            new_html = parts[0] + search_text + data_json + ";" + parts[1].split(";", 1)[1]
        else:
            new_html = parts[0] + search_text + data_json
    else:
        new_html = html.replace("<head>", f"<head>\n<script>\nconst fundData = {data_json};\n</script>")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"\n✓ 已更新HTML到: {output_path}")
    return output_path

def save_full_csv(all_histories):
    """保存完整历史数据到CSV"""
    all_dfs = []
    for code, history in all_histories.items():
        df = pd.DataFrame(history)
        df["code"] = code
        all_dfs.append(df)
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        csv_path = "/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data.csv"
        full_df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"✓ 完整历史数据已保存到: {csv_path}")

def main():
    print("=== 获取完整历史净值并计算收益 ===")
    
    # 1. 获取所有基金历史数据
    fund_results, all_histories = fetch_all_funds_history()
    
    # 2. 保存完整CSV
    save_full_csv(all_histories)
    
    # 3. 更新HTML
    template_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final_20260329.html"
    output_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final_20260329_full.html"
    
    update_html_with_returns(template_path, output_path, fund_results)
    
    # 4. 输出收益汇总
    print("\n=== 收益汇总（近一周）===")
    for r in fund_results:
        if r["has_data"] and r.get("week_return") is not None:
            print(f"{r['name']}: 周收益 {r['week_return']:.2f}% | 月收益 {r.get('month_return', 0):.2f}%")

if __name__ == "__main__":
    main()
