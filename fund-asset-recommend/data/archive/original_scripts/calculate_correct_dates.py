# -*- coding: utf-8 -*-
"""
完全按照正确交易日区间计算：
- 近一周：起点 = 上周五收盘(3月13日) → 终点 = 本周五收盘(3月20日)
- 近一月：起点 = 一个月前周五收盘(2月20日) → 终点 = 本周五收盘(3月20日)
- 最大回撤：今年年初到本周五(3月20日)
"""
import sys
import pandas as pd
import json
sys.path.append('/Users/huangqingmeng/.openclaw/workspace/huofuniu-sdk/mall_sdk')

from fof99 import FundCompanyPrice, FundPrice

APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"

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
    {"name": "波克宏观配置一号", "code": "SARZ77", "category": "多策略", "display_name": "宏观大类（波克宏观配置一号）"},
]

def fetch_fund_history(fund_code, start_date="2025-01-01", source="team"):
    if source == "platform":
        req = FundPrice(APP_ID, APP_KEY)
    else:
        req = FundCompanyPrice(APP_ID, APP_KEY)
    req.set_params(reg_code=fund_code, start_date=start_date, order_by='price_date', order=1)
    data = req.do_request(use_df=False)
    return data, req.get_debug_info()

def find_nav_exact_date(sorted_history, date_str):
    """找到精确匹配日期的净值，如果没有就找最近的"""
    for item in sorted_history:
        if item["price_date"] == date_str:
            return item["cumulative_nav"]
    # 如果精确找不到，找最后一个不超过的
    for item in reversed(sorted_history):
        if item["price_date"] <= date_str:
            return item["cumulative_nav"]
    return sorted_history[0]["cumulative_nav"]

def calculate_returns(history):
    if not history or len(history) == 0:
        return None
    
    sorted_history = sorted(history, key=lambda x: x["price_date"])
    
    # 精确区间：
    week_start_date = "2026-03-13"   # 上周五收盘
    week_end_date = "2026-03-20"     # 本周五收盘
    month_start_date = "2026-02-20" # 上月最后一个周五收盘
    
    week_start_nav = find_nav_exact_date(sorted_history, week_start_date)
    week_end_nav = find_nav_exact_date(sorted_history, week_end_date)
    
    month_start_nav = find_nav_exact_date(sorted_history, month_start_date)
    month_end_nav = find_nav_exact_date(sorted_history, week_end_date)
    
    returns = {}
    returns["week_return"] = (week_end_nav / week_start_nav - 1) * 100
    returns["month_return"] = (month_end_nav / month_start_nav - 1) * 100
    
    # 最新净值就是终点
    latest = None
    for item in sorted_history:
        if item["price_date"] == week_end_date:
            latest = item
            break
    if latest is None:
        latest = sorted_history[-1]
    
    returns["latest_nav"] = latest["nav"]
    returns["latest_cum_nav"] = latest["cumulative_nav"]
    returns["latest_date"] = latest["price_date"]
    returns["daily_change"] = latest.get("price_change", 0) * 100
    
    # 今年以来：2026-01-01 ~ 2026-03-20
    ytd_start_nav = find_nav_exact_date(sorted_history, "2026-01-01")
    returns["ytd_return"] = (week_end_nav / ytd_start_nav - 1) * 100
    
    # 最大回撤：2026-01-01 ~ 2026-03-20
    # 找到起始点之后的数据
    start_idx = 0
    for i, item in enumerate(sorted_history):
        if item["price_date"] >= "2026-01-01":
            start_idx = i
            break
    
    recent_cum = []
    for item in sorted_history[start_idx:]:
        if item["price_date"] <= "2026-03-20":
            recent_cum.append(item["cumulative_nav"])
    
    if len(recent_cum) > 0:
        max_so_far = recent_cum[0]
        max_drawdown = 0
        for nav in recent_cum:
            if nav > max_so_far:
                max_so_far = nav
            drawdown = (max_so_far - nav) / max_so_far * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        returns["max_drawdown"] = -max_drawdown
    else:
        returns["max_drawdown"] = 0
    
    # 夏普比率
    returns["sharpe"] = returns["month_return"] / abs(-returns["max_drawdown"]) if returns["max_drawdown"] != 0 else 0
    
    return returns, sorted_history

def main():
    print("=== 完全正确交易日区间计算 ===")
    print("近一周：2026-03-13 收盘 → 2026-03-20 收盘")
    print("近一月：2026-02-20 收盘 → 2026-03-20 收盘\n")
    
    all_results = []
    
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
    
    # 输出对比你的面板数据
    dream_panel = {
        "量化选股（顽岩量化选股1号)": {"week": -1.33, "ytd": +6.74},
        "股票择时（正仁股票择时一期)": {"week": -0.82, "ytd": +0.84},
        "双创择时（正仁双创)": {"week": None, "ytd": +4.03},
        "微盘择时（瀚鑫纸鸢量化优选)": {"week": -0.84, "ytd": +0.89},
        "1000指增（积沐领航者)": {"week": -2.76, "ytd": +3.87},
        "2000指增T0（太衍光年中证2000指数增强2号)": {"week": -2.75, "ytd": +2.94},
        "红利指增（时间序列红利增强)": {"week": +0.50, "ytd": +0.70},
        "转债多头-集中类（赢仕安盈二号)": {"week": -1.62, "ytd": -0.96},
        "转债多头-分散类（具力芒种1号)": {"week": -1.63, "ytd": -0.33},
        "短线择时（旌安思源1号B)": {"week": -1.13, "ytd": -1.23},
        "趋势策略（创世纪顾锝灵活多策略1号)": {"week": -1.32, "ytd": -1.52},
        "主线择时（立心-私募学院菁英353号)": {"week": +0.27, "ytd": +1.63},
        "大盘择时（翔云50二号A)": {"week": -1.80, "ytd": +2.11},
        "量化打板（特夫郁金香全量化)": {"week": -2.51, "ytd": +3.21},
        "量化时序cta（铭跃行远均衡一号)": {"week": -1.23, "ytd": -1.60},
        "化工-碳硅1号": {"week": -2.31, "ytd": -0.80},
        "黑色-涌泉君安三号": {"week": +1.14, "ytd": +4.74},
        "农产品-海鹏扬帆": {"week": -1.36, "ytd":