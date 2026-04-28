# -*- coding: utf-8 -*-
"""
最终精确计算：
- 近一周：精确找到 API 给出的 2026-03-13 净值 → 2026-03-20 净值
- 近一月：精确找到 API 给出的 2026-02-20 净值 → 2026-03-20 净值
- 最大回撤：今年年初（2026-01-01）→ 2026-03-20 之间的最大回撤
- 完全按照A股交易日，火富牛有交易日才有净值，自动跳过节假日
"""
import pandas as pd
import json

df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_correct.csv')

def get_nav_by_date(code, date_str):
    """精确找到指定日期的净值，如果没有就找最后一个之前交易日"""
    fund = df[df['code'] == code].sort_values('price_date')
    exact = fund[fund['price_date'] == date_str]
    if not exact.empty:
        return exact.iloc[0]['cumulative_nav'], exact.iloc[0]['price_date']
    # 找不到精确就找最近一个之前的
    filtered = fund[fund['price_date'] <= date_str]
    if not filtered.empty:
        last = filtered.iloc[-1]
        return last['cumulative_nav'], last['price_date']
    return fund.iloc[0]['cumulative_nav'], fund.iloc[0]['price_date']

GAMT_FUNDS = [
    {"name": "顽岩量化选股1号", "code": "SATW62", "category": "量选类", "display_name": "量化选股（顽岩量化选股1号）"},
    {"name": "正仁股票择时一期", "code": "SARD76", "category": "量选类", "display_name": "股票择时（正仁股票择时一期）"},
    {"name": "正仁双创择时一号", "code": "SXG834", "category": "风格类", "display_name": "双创择时（正仁双创）"},
    {"name": "瀚鑫纸鸢量化优选", "code": "SZC020", "category": "风格类", "display_name": "微盘择时（瀚鑫纸鸢量化优选）"},
    {"name": "积沐领航者", "code": "SAJJ91", "category": "风格类", "display_name": "1000指增（积沐领航者）"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75", "category": "风格类", "display_name": "2000指增T0（太衍光年中证2000指数增强2号）"},
    {"name": "时间序列红利增强1号", "code": "SSV122", "category": "风格类", "display_name": "红利指增（时间序列红利增强）"},
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

rank_map = {
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
risk_map = {
    "量化选股（顽岩量化选股1号）": "medium",
    "股票择时（正仁股票择时一期）": "medium",
    "双创择时（正仁双创）": "high",
    "微盘择时（瀚鑫纸鸢量化优选）": "high",
    "1000指增（积沐领航者）": "high",
    "2000指增T0（太衍光年中证2000指数增强）": "high",
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
color_map = {
    "量选类": "#3b82f6",
    "风格类": "#10b981",
    "绝对收益": "#8b5cf6",
    "商品类": "#f59e0b",
    "多策略": "#06b6d4",
}

dream_panel = {
    "量化选股（顽岩量化选股1号)": {"week": -1.33, "ytd": 6.74},
    "股票择时（正仁股票择时一期)": {"week": -0.82, "ytd": 0.84},
    "双创择时（正仁双创)": {"week": None, "ytd": 4.03},
    "微盘择时（瀚鑫纸鸢量化优选)": {"week": -0.84, "ytd": 0.89},
    "1000指增（积沐领航者)": {"week": -2.76, "ytd": 3.87},
    "2000指增T0（太衍光年中证2000指数增强2号)": {"week": -2.75, "ytd": 2.94},
    "红利指增（时间序列红利增强)": {"week": 0.50, "ytd": 0.70},
    "转债多头-集中类（赢仕安盈二号)": {"week": -1.62, "ytd": -0.96},
    "转债多头-分散类（具力芒种1号)": {"week": -1.63, "ytd": -0.33},
    "短线择时（旌安思源1号B)": {"week": -1.13, "ytd": -1.23},
    "趋势策略（创世纪顾锝灵活多策略1号)": {"week": -1.32, "ytd": -1.52},
    "主线择时（立心-私募学院菁英353号)": {"week": 0.27, "ytd": 1.63},
    "大盘择时（翔云50二号A)": {"week": -1.80, "ytd": 2.11},
    "量化打板（特夫郁金香全量化)": {"week": -2.51, "ytd": 3.21},
    "量化时序cta（铭跃行远均衡一号)": {"week": -1.23, "ytd": -1.60},
    "化工-碳硅1号": {"week": -2.31, "ytd": -0.80},
    "黑色-涌泉君安三号": {"week": 1.14, "ytd": 4.74},
    "农产品-海鹏扬帆": {"week": -1.36, "ytd": 0.09},
    "黄金大类（格林基金鲲鹏六号)": {"week": 0.79, "ytd": 6.35},
    "宏观大类（波克宏观配置一号)": {"week": -0.13, "ytd": 3.31},
}

def main():
    print("=== 最终精确计算（严格按照火富牛交易日，3月13日→3月20日）===")
    print("%-30s %-12s %-12s %-10s %-10s" % ("产品名称", "我的周收益", "你的周收益", "我的月收益", "你的月收益"))
    print("-" * 90)
    
    all_results = []
    for fund in GAMT_FUNDS:
        code = fund["code"]
        name = fund["display_name"]
        
        # 精确找日期净值
        wstart_nav, wstart_date = get_nav_by_date(code, "2026-03-13")
        wend_nav, wend_date = get_nav_by_date(code, "2026-03-20")
        mstart_nav, mstart_date = get_nav_by_date(code, "2026-02-20")
        mend_nav, mend_date = get_nav_by_date(code, "2026-03-20")
        
        week_return = (wend_nav / wstart_nav - 1) * 100
        month_return = (mend_nav / mstart_nav - 1) * 100
        
        # 找最新净值信息
        latest_nav_row = df[(df['code'] == code) & (df['price_date'] == wend_date)]
        if latest_nav_row.empty:
            latest_nav_row = df[(df['code'] == code)].sort_values('price_date').iloc[-1]
        else:
            latest_nav_row = latest_nav_row.iloc[0]
        
        # 计算今年以来收益和最大回撤
        ytd_start_nav, _ = get_nav_by_date(code, "2026-01-01")
        ytd_return = (wend_nav / ytd_start_nav - 1) * 100
        
        # 最大回撤 2026-01-01 → 2026-03-20
        fund_df = df[df['code'] == code].sort_values('price_date')
        start_idx = 0
        for i, (_, row) in enumerate(fund_df.iterrows()):
            if row['price_date'] >= "2026-01-01":
                start_idx = i
                break
        
        recent_cum = []
        for i, (_, row) in enumerate(fund_df.iloc[start_idx:].iterrows()):
            if row['price_date'] <= "2026-03-20":
                recent_cum.append(row['cumulative_nav'])
        
        if len(recent_cum) > 0:
            max_so_far = recent_cum[0]
            max_drawdown = 0
            for nav in recent_cum:
                if nav > max_so_far:
                    max_so_far = nav
                drawdown = (max_so_far - nav) / max_so_far * 100
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            max_drawdown = -max_drawdown
        else:
            max_drawdown = 0
        
        sharpe = month_return / abs(-max_drawdown) if max_drawdown != 0 else 0
        
        result = fund.copy()
        result.update({
            "week_return": week_return,
            "month_return": month_return,
            "latest_nav": latest_nav_row["nav"],
            "latest_cum_nav": wend_nav,
            "latest_date": wend_date,
            "daily_change": latest_nav_row.get("price_change", 0) * 100 if "price_change" in latest_nav_row else 0,
            "ytd_return": ytd_return,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "rank": rank_map[name],
            "rankText": {"top": "前1/3", "middle": "中1/3", "bottom": "后1/3"}[rank_map[name]],
            "risk": risk_map[name],
            "strategyColor": color_map[result["category"]],
            "has_data": True,
        })
        all_results.append(result)
        
        # 输出对比
        if name in dream_panel:
            d_week = dream_panel[name]["week"]
            d_ytd = dream_panel[name]["ytd"]
            d_week_str = f