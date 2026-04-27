# -*- coding: utf-8 -*-
"""
计算截止到2026-03-20那一周的收益，验证准确性
"""
import pandas as pd
import json

# 读取完整历史数据
df = pd.read_csv('/Users/huangqingmeng/.openclaw/workspace/all_full_nav_data.csv')

# GAMT基金列表
GAMT_FUNDS = [
    {"name": "立心-私募学院菁英353号", "code": "SCJ476"},
    {"name": "波克宏观配置1号", "code": "SARZ77"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75"},
    {"name": "翔云50二号A类", "code": "VB166A"},
    {"name": "创世纪顾锝灵活多策略1号", "code": "SBDC67"},
    {"name": "碳硅1号", "code": "SXJ836"},
    {"name": "顽岩量化选股1号", "code": "SATW62"},
    {"name": "正仁股票择时一期", "code": "SARD76"},
    {"name": "格林基金鲲鹏6号", "code": "SVZ638"},
    {"name": "赢仕安盈二号", "code": "SLQ349"},
    {"name": "具力芒种1号", "code": "STE836"},
    {"name": "积沐领航者", "code": "SAJJ91"},
    {"name": "旌安思源1号B类", "code": "AEU46B"},
    {"name": "涌泉君安三号", "code": "SZM385"},
    {"name": "铭跃行远均衡一号", "code": "SVZ009"},
    {"name": "正仁双创择时一号", "code": "SXG834"},
    {"name": "特夫郁金香全量化", "code": "SQX078"},
    {"name": "海鹏扬帆", "code": "SSR379"},
]

# 截止到3月20日，计算3月13日-3月20日这一周的收益
end_date = "2026-03-20"
start_date = "2026-03-13"

print(f"=== 计算截止到{end_date}一周收益 (3月13日 - 3月20日) ===\n")
print(f"{'基金名称':<25} {'起点净值':<10} {'终点净值':<10} {'周收益':>8}")
print("-" * 60)

results = []

for fund in GAMT_FUNDS:
    code = fund["code"]
    name = fund["name"]
    
    # 过滤该基金
    fund_df = df[df['code'] == code].copy()
    fund_df = fund_df.sort_values('price_date')
    
    # 找起点（最接近start_date但<=）
    start_nav_row = fund_df[fund_df['price_date'] <= start_date].tail(1)
    # 找终点（最接近end_date但<=）
    end_nav_row = fund_df[fund_df['price_date'] <= end_date].tail(1)
    
    if start_nav_row.empty or end_nav_row.empty:
        print(f"{name:<25} {'数据不足':<20}")
        continue
    
    start_nav = start_nav_row.iloc[0]['cumulative_nav']
    end_nav = end_nav_row.iloc[0]['cumulative_nav']
    ret = (end_nav / start_nav - 1) * 100
    
    print(f"{name:<25} {start_nav:<10.4f} {end_nav:<10.4f} {ret:>7.2f}%")
    results.append({
        "name": name,
        "start_nav": start_nav,
        "end_nav": end_nav,
        "week_return": ret
    })

print("\n" + "-" * 60)
print(f"\n总结：")
positive = [r for r in results if r['week_return'] > 0]
negative = [r for r in results if r['week_return'] <= 0]
print(f"上涨 {len(positive)} 只，下跌 {len(negative)} 只")
print(f"平均周收益: {sum(r['week_return'] for r in results)/len(results):.2f}%")
