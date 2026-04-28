# -*- coding: utf-8 -*-
"""
按照梦梦给出的面板，重新计算 3月22日 ~ 3月26日 这一周的收益
"""
import pandas as pd

# 读取完整历史数据
df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data_v2.csv')

# 按策略分类整理
FUND_MAPPING = [
    {"display": "量化选股（顽岩量化选股1号）", "code": "SATW62", "category": "量选类"},
    {"display": "股票择时（正仁股票择时一期）", "code": "SARD76", "category": "量选类"},
    {"display": "双创择时（正仁双创）", "code": "SXG834", "category": "风格类"},
    {"display": "微盘择时（瀚鑫纸鸢量化优选）", "code": "SZC020", "category": "风格类"},
    {"display": "1000指增（积沐领航者）", "code": "SAJJ91", "category": "风格类"},
    {"display": "2000指增T0（太衍光年中证2000指数增强2号）", "code": "SBCA75", "category": "风格类"},
    {"display": "红利指增（时间序列红利增强）", "code": "SSV122", "category": "风格类"},
    {"display": "转债多头-集中类（赢仕安盈二号）", "code": "SLQ349", "category": "风格类"},
    {"display": "转债多头-分散类（具力芒种1号）", "code": "STE836", "category": "风格类"},
    {"display": "短线择时（旌安思源1号B类）", "code": "AEU46B", "category": "绝对收益"},
    {"display": "趋势策略（创世纪顾锝灵活多策略1号）", "code": "SBDC67", "category": "绝对收益"},
    {"display": "主线择时（立心-私募学院菁英353号）", "code": "SCJ476", "category": "绝对收益"},
    {"display": "大盘择时（翔云50二号A类）", "code": "VB166A", "category": "绝对收益"},
    {"display": "量化打板（特夫郁金香全量化）", "code": "SQX078", "category": "绝对收益"},
    {"display": "量化时序cta（铭跃行远均衡一号）", "code": "SVZ009", "category": "商品类"},
    {"display": "化工-碳硅1号", "code": "SXJ836", "category": "商品类"},
    {"display": "黑色-涌泉君安三号", "code": "SZM385", "category": "商品类"},
    {"display": "农产品-海鹏扬帆", "code": "SSR379", "category": "商品类"},
    {"display": "黄金大类（格林基金鲲鹏六号）", "code": "SVZ638", "category": "多策略"},
    {"display": "宏观大类（波克宏观配置一号）", "code": "SARZ77", "category": "多策略"},
]

# 目标区间：本周一(3月22日) 到 本周五(3月26日)
start_date = "2026-03-22"
end_date = "2026-03-26"

print(f"=== 计算区间 {start_date} ~ {end_date} 周收益 ===")
print(f"{'序号':<3} {'产品名称':<28} {'分类':<10} {'起点净值':<10} {'终点净值':<10} {'我的计算':>8} {'你面板显示'}")
print("-" * 100)

results = []
for i, item in enumerate(FUND_MAPPING, 1):
    code = item["code"]
    fund_df = df[df['code'] == code].sort_values('price_date')
    
    # 找最接近start_date但<=
    start_rows = fund_df[fund_df['price_date'] <= start_date]
    if start_rows.empty:
        start_nav = None
    else:
        start_nav = start_rows.iloc[-1]['cumulative_nav']
        actual_start_date = start_rows.iloc[-1]['price_date']
    
    # 找最接近end_date但<=
    end_rows = fund_df[fund_df['price_date'] <= end_date]
    if end_rows.empty:
        end_nav = None
    else:
        end_nav = end_rows.iloc[-1]['cumulative_nav']
        actual_end_date = end_rows.iloc[-1]['price_date']
    
    if start_nav is None or end_nav is None:
        ret = None
    else:
        ret = (end_nav / start_nav - 1) * 100
    
    results.append({
        "i": i,
        "display": item["display"],
        "category": item["category"],
        "start_nav": start_nav,
        "end_nav": end_nav,
        "ret": ret,
        "actual_start_date": actual_start_date if start_nav else None,
        "actual_end_date": actual_end_date if end_nav else None,
    })
    
    # 输出
    ret_str = f"{ret:.2f}%" if ret is not None else "N/A"
    print(f"{i:<3} {item['display']:<28} {item['category']:<10} {start_nav if start_nav else 'N/A':<10.4f} {end_nav if end_nav else 'N/A':<10.4f} {ret_str:>8}")

print("\n" + "-" * 100)
