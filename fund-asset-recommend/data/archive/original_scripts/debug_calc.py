# -*- coding: utf-8 -*-
import pandas as pd
import json

# 直接从已经保存的完整csv数据中计算，不需要重新请求API
df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_correct.csv')

def find_nav_exact_date(code, date_str):
    fund = df[df['code'] == code]
    fund = fund.sort_values('price_date')
    for _, item in fund.iterrows():
        if item['price_date'] == date_str:
            return item['cumulative_nav']
    for _, item in fund[::-1].iterrows():
        if item['price_date'] <= date_str:
            return item['cumulative_nav']
    return fund.iloc[0]['cumulative_nav']

# 基金列表
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
color_map = {
    "量选类": "#3b82f6",
    "风格类": "#10b981",
    "绝对收益": "#8b5cf6",
    "商品类": "#f59e0b",
    "多策略": "#06b6d4",
}

def main():
    print("=== 对比结果（正确区间：3.13-3.20）===")
    print("%-30s %10s %10s %10s %10s" % ("产品名称", "我的周收益", "你的周收益", "我的月收益", "你的月收益"))
    print("-" * 90)
    dream = {
        "量化选股（顽岩量化选股1号)": (-1.33, 6.74),
        "股票择时（正仁股票择时一期)": (-0.82, 0.84),
        "双创择时（正仁双创)": (None, 4.03),
        "微盘择时（瀚鑫纸鸢量化优选)": (-0.84, 0.89),
        "1000指增（积沐领航者)": (-2.76, 3.87),
        "2000指增T0（太衍光年中证2000指数增强2号)": (-2.75, 2.94),
        "红利指增（时间序列红利增强)": (0.50, 0.70),
        "转债多头-集中类（赢仕安盈二号)": (-1.62, -0.96),
        "转债多头-分散类（具力芒种1号)": (-1.63, -0.33),
        "短线择时（旌安思源1号B)": (-1.13, -1.23),
        "趋势策略（创世纪顾锝灵活多策略1号)": (-1.32, -1.52),
        "主线择时（立心-私募学院菁英353号)": (0.27, 1.63),
        "大盘择时（翔云50二号A)": (-1.80, 2.11),
        "量化打板（特夫郁金香全量化)": (-2.51, 3.21),
        "量化时序cta（铭跃行远均衡一号)": (-1.23, -1.60),
        "化工-碳硅1号": (-2.31, -0.80),
        "黑色-涌泉君安三号": (1.14, 4.74),
        "农产品-海鹏扬帆": (-1.36, 0.09),
        "黄金大类（格林基金鲲鹏六号)": (0.79, 6.35),
        "宏观大类（波克宏观配置一号)": (-0.13, 3.31),
    }
    
    all_results = []
    for fund in GAMT_FUNDS:
        code = fund["code"]
        display_name = fund["display_name"]
        week_start = "2026-03-13"
        week_end = "2026-03-20"
        month_start = "2026-02-20"
        
        wstart_nav = find_nav_exact_date(code, week_start)
        wend_nav = find_nav_exact_date(code, week_end)
        mstart_nav = find_nav_exact_date(code, month_start)
        mend_nav = find_nav_exact_date(code, week_end)
        
        week_return = (wend_nav / wstart_nav - 1) * 100
        month_return = (mend_nav / mstart_nav - 1) * 100
        
        # 找最新净值就是week_end
        fund_df = df[df['code'] == code].sort_values('price_date')
        latest = fund_df[fund_df['price_date'] == week_end]
        if latest.empty:
            latest = fund_df.iloc[-1]
        else:
            latest = latest.iloc[-1]
        
        # 计算最大回撤
        start_idx = 0
        for i, (_, item) in enumerate(fund_df.iterrows()):
            if item['price_date'] >= "2026-01-01":
                start_idx = i
                break
        
        recent_cum = []
        for i, (_, item) in enumerate(fund_df.iloc[start_idx:].iterrows()):
            if item['price_date'] <= "2026-03-20":
                recent_cum.append(item['cumulative_nav'])
        
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
        result["week_return"] = week_return
        result["month_return"] = month_return
        result["latest_nav"] = latest["nav"]
        result["latest_cum_nav"] = latest["cumulative_nav"]
        result["latest_date"] = latest["price_date"]
        result["daily_change"] = latest.get("price_change", 0) * 100 if "price_change" in latest else 0
        result["ytd_return"] = (wend_nav / find_nav_exact_date(code, "2026-01-01") - 1) * 100
        result["max_drawdown"] = max_drawdown
        result["sharpe"] = sharpe
        result["rank"] = rank_map[display_name]
        result["rankText"] = {"top": "前1/3", "middle": "中1/3", "bottom": "后1/3"}[result["rank"]]
        result["risk"] = risk_map[display_name]
        result["strategyColor"] = color_map[result["category"]]
        result["has_data"] = True
        all_results.append(result)
        
        if display_name in dream:
            d_week, d_month = dream[display_name]
            print("%-30s %10.2f%% %10s%% %10.2f%% %10s%%" % (display_name, week_return, str(d_week), month_return, str(d_month)))
    
    with open('/Users/huangqingmeng/.openclaw/workspace/static_data_final.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)
    
    print()
    print("✓ 计算完成，已保存到 static_data_final.json")

if __name__ == "__main__":
    main()
