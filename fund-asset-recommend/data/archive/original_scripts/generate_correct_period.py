# -*- coding: utf-8 -*-
"""
按照正确周期生成：
- 近一周：2026-03-17 ~ 2026-03-20
- 近一月：2026-02-20 ~ 2026-03-20
- 今年以来：2026-01-01 ~ 最新
- 最新净值：最新日期
- 最大回撤：历史最大回撤
"""
import sys
import pandas as pd
import json
from datetime import datetime, timedelta
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundCompanyPrice, FundPrice

# 配置
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

# GAMT核心基金列表（带策略分类）
GAMT_FUNDS = [
    {"name": "顽岩量化选股1号", "code": "SATW62", "category": "量选类", "display_name": "量化选股（顽岩量化选股1号）"},
    {"name": "正仁股票择时一期", "code": "SARD76", "category": "量选类", "display_name": "股票择时（正仁股票择时一期）"},
    {"name": "正仁双创择时一号", "code": "SXG834", "category": "风格类", "display_name": "双创择时（正仁双创）"},
    {"name": "瀚鑫纸鸢量化优选", "code": "SZC020", "category": "风格类", "display_name": "微盘择时（瀚鑫纸鸢量化优选）", "source": "platform"},
    {"name": "积沐领航者", "code": "SAJJ91", "category": "风格类", "display_name": "1000指增（积沐领航者）"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75", "category": "风格类", "display_name": "2000指增T0（太衍光年中证2000指数增强2号）"},
    {"name": "时间序列红利增强1号", "code": "SSV122", "category": "风格类", "display_name": "红利指增（时间序列红利增强）", "source": "platform"},
    {"name": "赢仕安盈二号", "code": "SLQ349", "category": "风格类", "display_name": "转债多头-集中类（赢仕安盈二号）"},
    {"name": "具力芒种1号", "code": "STE836", "category": "风格类", "display_name": "转债多头-分散类（具力芒种1号）"},
    {"name": "旌安思源1号B类", "code": "AEU46B", "category": "绝对收益", "display_name": "短线择时（旌安思源1号B类）"},
    {"name": "创世纪顾锝灵活多策略1号", "code": "SBDC67", "category": "绝对收益", "display_name": "趋势策略（创世纪顾锝灵活多策略1号）"},
    {"name": "立心-私募学院菁英353号", "code": "SCJ476", "category": "绝对收益", "display_name": "主线择时（立心-私募学院菁英353号）"},
    {"name": "翔云50二号A类", "code": "VB166A", "category": "绝对收益", "display_name": "大盘择时（翔云50二号A类）"},
    {"name": "特夫郁金香全量化", "code": "SQX078", "category": "绝对收益", "display_name": "量化打板（特夫郁金香全量化）"},
    {"name": "铭跃行远均衡一号", "code": "SVZ009", "category": "商品类", "display_name": "量化时序cta（铭跃行远均衡一号)"},
    {"name": "碳硅1号", "code": "SXJ836", "category": "商品类", "display_name": "化工-碳硅1号"},
    {"name": "涌泉君安三号", "code": "SZM385", "category": "商品类", "display_name": "黑色-涌泉君安三号"},
    {"name": "海鹏扬帆", "code": "SSR379", "category": "商品类", "display_name": "农产品-海鹏扬帆"},
    {"name": "格林基金鲲鹏6号", "code": "SVZ638", "category": "多策略", "display_name": "黄金大类（格林基金鲲鹏六号）"},
    {"name": "波克宏观配置1号", "code": "SARZ77", "category": "多策略", "display_name": "宏观大类（波克宏观配置一号）"},
]

def fetch_fund_history(fund_code, start_date="2025-01-01", source="team"):
    if source == "platform":
        req = FundPrice(APP_ID, APP_KEY)
    else:
        req = FundCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund_code, start_date=start_date, order_by='price_date', order=1)
    data = req.do_request(use_df=False)
    return data, req.get_debug_info()

def find_nav_before(sorted_history, target_date_str):
    """找到最接近且小于等于目标日期的净值"""
    for item in reversed(sorted_history):
        if item["price_date"] <= target_date_str:
            return item["cumulative_nav"], item["price_date"]
    return sorted_history[0]["cumulative_nav"], sorted_history[0]["price_date"]

def calculate_returns(history):
    """按正确周期计算"""
    if not history or len(history) == 0:
        return None
    
    sorted_history = sorted(history, key=lambda x: x["price_date"])
    latest = sorted_history[-1]
    latest_cum_nav = latest["cumulative_nav"]
    
    returns = {}
    returns["latest_nav"] = latest["nav"]
    returns["latest_cum_nav"] = latest_cum_nav
    returns["latest_date"] = latest["price_date"]
    returns["daily_change"] = latest.get("price_change", 0) * 100
    
    # 近一周：2026-03-17 ~ 2026-03-20
    week_start_nav, _ = find_nav_before(sorted_history, "2026-03-17")
    week_end_nav, _ = find_nav_before(sorted_history, "2026-03-20")
    returns["week_return"] = (week_end_nav / week_start_nav - 1) * 100
    
    # 近一月：2026-02-20 ~ 2026-03-20
    month_start_nav, _ = find_nav_before(sorted_history, "2026-02-20")
    month_end_nav, _ = find_nav_before(sorted_history, "2026-03-20")
    returns["month_return"] = (month_end_nav / month_start_nav - 1) * 100
    
    # 今年以来：2026-01-01 ~ 最新
    ytd_start_nav, _ = find_nav_before(sorted_history, "2026-01-01")
    returns["ytd_return"] = (latest_cum_nav / ytd_start_nav - 1) * 100
    
    # 最大回撤
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

def main():
    print("=== 按正确周期重新计算 ===")
    print(f"近一周：2026-03-17 ~ 2026-03-20")
    print(f"近一月：2026-02-20 ~ 2026-03-20")
    print(f"今年以来：2026-01-01 ~ 最新\n")
    
    all_results = []
    all_histories = {}
    
    for fund in GAMT_FUNDS:
        source = fund.get("source", "team")
        print(f"获取 {fund['display_name']} ...")
        history, _ = fetch_fund_history(fund["code"], start_date="2025-01-01", source=source)
        
        if not history:
            print(f"  ✗ 无数据")
            result = fund.copy()
            result["has_data"] = False
            all_results.append(result)
            continue
        
        returns_data, sorted_history = calculate_returns(history)
        all_histories[fund["code"]] = sorted_history
        
        result = fund.copy()
        result.update(returns_data)
        result["has_data"] = True
        all_results.append(result)
        
        import time
        time.sleep(0.2)
    
    # 统计
    has_data_count = sum(1 for r in all_results if r["has_data"])
    print(f"\n完成：{has_data_count}/{len(all_results)} 只有数据")
    
    # 输出汇总
    print("\n=== 最终结果（API抓取数据计算）===")
    print(f"{'序号':<3} {'产品名称':<30} {'周收益':>8} {'月收益':>8} {'今年以来':>8} {'最新净值':>10}")
    print("-" * 100)
    for i, r in enumerate(all_results, 1):
        if not r["has_data"]:
            continue
        print(f"{i:<3} {r['display_name']:<30} {r['week_return']:>7.2f}% {r['month_return']:>7.2f}% {r['ytd_return']:>7.2f}% {r['latest_nav']:>10.4f}")
    
    # 保存完整CSV
    all_dfs = []
    for code, history in all_histories.items():
        df = pd.DataFrame(history)
        df["code"] = code
        all_dfs.append(df)
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        csv_path = "/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_correct.csv"
        full_df.to_csv(csv_path, index=False, encoding='utf-8')
        print(f"\n✓ 完整数据保存到 {csv_path}")
    
    # 更新HTML
    template_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final_20260329.html"
    output_path = "/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final.html"
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    data_json = json.dumps(all_results, ensure_ascii=False, indent=2)
    
    search_text = "const fundData = "
    if search_text in html:
        parts = html.split(search_text)
        if ";" in parts[1]:
            new_html = parts[0] + search_text + data_json + ";" + parts[1].split(";", 1)[1]
        else:
            new_html = parts[0] + search_text + data_json
    else:
        new_html = html.replace("<head>", f"<head>\n<script>\nconst fundData = {data_json};\n</script>")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"✓ 更新后的HTML保存到 {output_path}")

if __name__ == "__main__":
    main()
