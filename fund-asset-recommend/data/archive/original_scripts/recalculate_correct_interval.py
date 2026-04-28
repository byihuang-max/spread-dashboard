# -*- coding: utf-8 -*-
"""
按照正确区间重新计算：
- 近一周：起始=上周一最后交易日(3月13日) → 结束=本周最后交易日(3月20日)
- 近一月：起始=一个月前最后交易日(2月20日) → 结束=本周最后交易日(3月20日)
- 最大回撤：从起始日到最新日计算
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

def find_nav_last_before(sorted_history, target_date_str):
    """找到最后一个不晚于目标日期的净值"""
    for item in reversed(sorted_history):
        if item["price_date"] <= target_date_str:
            return item["cumulative_nav"], item["price_date"]
    return sorted_history[0]["cumulative_nav"], sorted_history[0]["price_date"]

def calculate_returns(history):
    """按正确区间计算"""
    if not history or len(history) == 0:
        return None
    
    sorted_history = sorted(history, key=lambda x: x["price_date"])
    latest = sorted_history[-1]
    
    # 找到最新的净值日期就是我们的终点
    end_date_str = latest["price_date"]
    
    returns = {}
    returns["latest_nav"] = latest["nav"]
    returns["latest_cum_nav"] = latest["cumulative_nav"]
    returns["latest_date"] = latest["price_date"]
    returns["daily_change"] = latest.get("price_change", 0) * 100
    
    # 近一周：起点 = 上周最后一个交易日(3月13日) 终点 = 本周最后交易日(3月20日)
    week_start_nav, _ = find_nav_last_before(sorted_history, "2026-03-13")
    week_end_nav, _ = find_nav_last_before(sorted_history, "2026-03-20")
    returns["week_return"] = (week_end_nav / week_start_nav - 1) * 100
    
    # 近一月：起点 = 上月最后交易日(2月20日) 终点 = 本周最后交易日(3月20日)
    month_start_nav, _ = find_nav_last_before(sorted_history, "2026-02-20")
    month_end_nav, _ = find_nav_last_before(sorted_history, "2026-03-20")
    returns["month_return"] = (month_end_nav / month_start_nav - 1) * 100
    
    # 今年以来：2026-01-01 ~ 最新
    ytd_start_nav, _ = find_nav_last_before(sorted_history, "2026-01-01")
    returns["ytd_return"] = (latest["cumulative_nav"] / ytd_start_nav - 1) * 100
    
    # 最大回撤：从今年年初到最新 或者 从有数据开始
    # 找到ytd起点之后的所有数据
    ytd_start_idx = 0
    for i, item in enumerate(sorted_history):
        if item["price_date"] >= "2026-01-01":
            ytd_start_idx = i
            break
    
    recent_cum = [item["cumulative_nav"] for item in sorted_history[ytd_start_idx:]]
    if len(recent_cum) > 0:
        max_so_far = recent_cum[0]
        max_drawdown = 0
        for nav in recent_cum:
            if nav > max_so_far:
                max_so_far = nav
            drawdown = (max_so_far - nav) / max_so_far * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        returns["max_drawdown"] = -max_drawdown  # 存为负数，显示的时候就是负的
    else:
        returns["max_drawdown"] = 0
    
    # 夏普比率：月收益 / 最大回撤（简化估算）
    returns["sharpe"] = returns["month_return"] / abs(-returns["max_drawdown"]) if returns["max_drawdown"] != 0 else 0
    
    return returns, sorted_history

def main():
    print("=== 按照正确区间重新计算收益 ===")
    print("近一周：2026-03-13 ~ 2026-03-20")
    print("近一月：2026-02-20 ~ 2026-03-20\n")
    
    all_results = []
    all_histories = {}
    
    rank_mapping = {
        "量化选股（顽岩量化选股1号）": "top",
        "股票择时（正仁股票择时一期）": "middle",
        "双创择时（正仁双创）": "top",
        "微盘择时（瀚鑫纸鸢量化优选）": "middle",
        "1000指增（积沐领航者）": "top",
        "2000指增T0（太衍光年中证2000指数增强2号）": "middle",
        "红利指增（时间序列红利增强）": "middle",
        "转债多头-集中类（赢仕安盈二号）": "bottom",
        "转债多头-分散类（具力芒种1号）": "bottom",
        "短线择时（旌安思源1号B类）": "bottom",
        "趋势策略（创世纪顾锝灵活多策略1号）": "bottom",
        "主线择时（立心-私募学院菁英353号）": "top",
        "大盘择时（翔云50二号A类）": "middle",
        "量化打板（特夫郁金香全量化）": "top",
        "量化时序cta（铭跃行远均衡一号)": "bottom",
        "化工-碳硅1号": "bottom",
        "黑色-涌泉君安三号": "top",
        "农产品-海鹏扬帆": "middle",
        "黄金大类（格林基金鲲鹏六号）": "top",
        "宏观大类（波克宏观配置一号）": "top",
    }
    
    risk_mapping = {
        "量化选股（顽岩量化选股1号）": "medium",
        "股票择时（正仁股票择时一期）": "medium",
        "双创择时（正仁双创）": "high",
        "微盘择时（瀚鑫纸鸢量化优选）": "high",
        "1000指增（积沐领航者）": "high",
        "2000指增T0（太衍光年中证2000指数增强2号）": "high",
        "红利指增（时间序列红利增强）": "low",
        "转债多头-集中类（赢仕安盈二号）": "medium",
        "转债多头-分散类（具力芒种1号）": "low",
        "短线择时（旌安思源1号B类）": "medium",
        "趋势策略（创世纪顾锝灵活多策略1号）": "medium",
        "主线择时（立心-私募学院菁英353号）": "high",
        "大盘择时（翔云50二号A类）": "medium",
        "量化打板（特夫郁金香全量化）": "high",
        "量化时序cta（铭跃行远均衡一号)": "medium",
        "化工-碳硅1号": "medium",
        "黑色-涌泉君安三号": "medium",
        "农产品-海鹏扬帆": "medium",
        "黄金大类（格林基金鲲鹏六号）": "low",
        "宏观大类（波克宏观配置一号）": "medium",
    }
    
    color_mapping = {
        "量选类": "#3b82f6",
        "风格类": "#10b981",
        "绝对收益": "#8b5cf6",
        "商品类": "#f59e0b",
        "多策略": "#06b6d4",
    }
    
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
        result["rank"] = rank_mapping[fund["display_name"]]
        result["rankText"] = {
            "top": "前1/3",
            "middle": "中1/3",
            "bottom": "后1/3",
        }[result["rank"]]
        result["risk"] = risk_mapping[fund["display_name"]]
        result["strategyColor"] = color_mapping[result["category"]]
        all_results.append(result)
        
        import time
        time.sleep(0.2)
    
    # 统计
    has_data_count = sum(1 for r in all_results if r["has_data"])
    print(f"\n完成：{has_data_count}/{len(all_results)} 只有数据")
    
    # 输出汇总
    print("\n=== 最终结果（正确区间）===")
    print(f"{'序号':<3} {'产品名称':<30} {'周收益':>8} {'月收益':>8} {'最大回撤':>10}")
    print("-" * 70)
    for i, r in enumerate(all_results, 1):
        if not r["has_data"]:
            continue
        print(f"{i:<3} {r['display_name']:<30} {r['week_return']:>7.2f}% {r['month_return']:>7.2f}% {r['max_drawdown']:>9.2f}%")
    
    # 保存JSON给HTML用
    with open('/Users/huangqingmeng/.openclaw/workspace/static_data_correct.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print(f"\n✓ 数据已保存到 static_data_correct.json")
    
    # 直接更新HTML
    with open('/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_v3_final_20260329.html', 'r', encoding='utf-8') as f:
        template = f.read()
    
    start = template.find('const productData = [')
    end = template.find('];', start) + 2
    
    with open('/Users/huangqingmeng/.openclaw/workspace/static_data_correct.json', 'r', encoding='utf-8') as f:
        product_data = json.load(f)
    
    json_str = json.dumps(product_data, ensure_ascii=False, indent=4)
    new_js = f'const productData = {json_str};'
    new_content = template[:start] + new_js + template[end:]
    
    # 更新统计区间文字
    old_period = '近一周 <span style="color:#888">(2026.03.17 - 2026.03.20)</span>'
    new_period = '近一周 <span style="color:#888">(2026.03.13 - 2026.03.20)</span>'
    new_content = new_content.replace