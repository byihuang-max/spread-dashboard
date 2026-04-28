# -*- coding: utf-8 -*-
"""
计算区间 3月15日 ~ 3月20日 对比梦梦给的面板数据
"""
import pandas as pd

df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_v2.csv')

FUND_MAPPING = [
    {"display": "量化选股（顽岩量化选股1号）", "code": "SATW62", "category": "量选类", "dream_week": -1.33, "dream_month": +6.74},
    {"display": "股票择时（正仁股票择时一期）", "code": "SARD76", "category": "量选类", "dream_week": -0.82, "dream_month": +0.84},
    {"display": "双创择时（正仁双创）", "code": "SXG834", "category": "风格类", "dream_week": None, "dream_month": +4.03},
    {"display": "微盘择时（瀚鑫纸鸢量化优选）", "code": "SZC020", "category": "风格类", "dream_week": -0.84, "dream_month": +0.89},
    {"display": "1000指增（积沐领航者）", "code": "SAJJ91", "category": "风格类", "dream_week": -2.76, "dream_month": +3.87},
    {"display": "2000指增T0（太衍光年中证2000指数增强2号）", "code": "SBCA75", "category": "风格类", "dream_week": -2.75, "dream_month": +2.94},
    {"display": "红利指增（时间序列红利增强）", "code": "SSV122", "category": "风格类", "dream_week": +0.50, "dream_month": +0.70},
    {"display": "转债多头-集中类（赢仕安盈二号）", "code": "SLQ349", "category": "风格类", "dream_week": -1.62, "dream_month": -0.96},
    {"display": "转债多头-分散类（具力芒种1号）", "code": "STE836", "category": "风格类", "dream_week": -1.63, "dream_month": -0.33},
    {"display": "短线择时（旌安思源1号B类）", "code": "AEU46B", "category": "绝对收益", "dream_week": -1.13, "dream_month": -1.23},
    {"display": "趋势策略（创世纪顾锝灵活多策略1号）", "code": "SBDC67", "category": "绝对收益", "dream_week": -1.32, "dream_month": -1.52},
    {"display": "主线择时（立心-私募学院菁英353号）", "code": "SCJ476", "category": "绝对收益", "dream_week": +0.27, "dream_month": +1.63},
    {"display": "大盘择时（翔云50二号A类）", "code": "VB166A", "category": "绝对收益", "dream_week": -1.80, "dream_month": +2.11},
    {"display": "量化打板（特夫郁金香全量化）", "code": "SQX078", "category": "绝对收益", "dream_week": -2.51, "dream_month": +3.21},
    {"display": "量化时序cta（铭跃行远均衡一号）", "code": "SVZ009", "category": "商品类", "dream_week": -1.23, "dream_month": -1.60},
    {"display": "化工-碳硅1号", "code": "SXJ836", "category": "商品类", "dream_week": -2.31, "dream_month": -0.80},
    {"display": "黑色-涌泉君安三号", "code": "SZM385", "category": "商品类", "dream_week": +1.14, "dream_month": +4.74},
    {"display": "农产品-海鹏扬帆", "code": "SSR379", "category": "商品类", "dream_week": -1.36, "dream_month": +0.09},
    {"display": "黄金大类（格林基金鲲鹏六号）", "code": "SVZ638", "category": "多策略", "dream_week": +0.79, "dream_month": +6.35},
    {"display": "宏观大类（波克宏观配置一号）", "code": "SARZ77", "category": "多策略", "dream_week": -0.13, "dream_month": +3.31},
]

start_date = "2026-03-15"
end_date = "2026-03-20"

print(f"{'序号':<3} {'产品名称':<28} {'我的周收益':>10} {'面板周收益':>10} {'差异':>8} | {'我的月收益':>10} {'面板月收益':>10}")
print("-" * 110)

for i, item in enumerate(FUND_MAPPING, 1):
    code = item["code"]
    fund_df = df[df['code'] == code].sort_values('price_date')
    
    start_rows = fund_df[fund_df['price_date'] <= start_date]
    start_nav = start_rows.iloc[-1]['cumulative_nav'] if not start_rows.empty else None
    
    end_rows = fund_df[fund_df['price_date'] <= end_date]
    end_nav = end_rows.iloc[-1]['cumulative_nav'] if not end_rows.empty else None
    
    if start_nav and end_nav:
        my_week = (end_nav / start_nav - 1) * 100
    else:
        my_week = None
    
    # 计算月收益（截至3月20日，过去30天 2月18日~3月20日）
    from datetime import datetime, timedelta
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    month_start_dt = end_dt - timedelta(days=30)
    month_start_str = month_start_dt.strftime("%Y-%m-%d")
    
    month_start_rows = fund_df[fund_df['price_date'] <= month_start_str]
    if not month_start_rows.empty:
        month_start_nav = month_start_rows.iloc[-1]['cumulative_nav']
        my_month = (end_nav / month_start_nav - 1) * 100
    else:
        my_month = None
    
    # 输出
    my_week_str = f"{my_week:.2f}%" if my_week is not None else "N/A"
    dream_week_str = f"{item['dream_week']:.2f}%" if item['dream_week'] is not None else "N/A"
    diff_str = f"{my_week - item['dream_week']:.2f}" if (my_week is not None and item['dream_week'] is not None) else "N/A"
    
    my_month_str = f"{my_month:.2f}%" if my_month is not None else "N/A"
    dream_month_str = f"{item['dream_month']:.2f}%" if item['dream_month'] is not None else "N/A"
    
    print(f"{i:<3} {item['display']:<28} {my_week_str:>10} {dream_week_str:>10} {diff_str:>8} | {my_month_str:>10} {dream_month_str:>10}")
