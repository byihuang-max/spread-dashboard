# -*- coding: utf-8 -*-
"""
检查HTML中的数据和会话中输出的数据是否一致
"""
import json
import re

# 读取HTML文件提取fundData
with open('/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final_20260329.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# 查找fundData起始位置
start = html_content.find('const fundData = ')
end = html_content.find('];', start) + 2
json_str = html_content[start + len('const fundData = ') : end]

# 解析JSON
fund_data = json.loads(json_str)

print("=== 数据对比：HTML中的数据 vs 会话中输出的数据 ===\n")
print(f"{'基金名称':<25} {'HTML周收益':>10} {'会话周收益':>10} {'差异':>10}")
print("-" * 60)

# 会话中输出的数据
session_data = {
    "立心-私募学院菁英353号": 0.25,
    "波克宏观配置1号": -1.06,
    "太衍光年中证2000指数增强2号": -3.50,
    "翔云50二号A类": -0.24,
    "创世纪顾锝灵活多策略1号": -1.53,
    "瀚鑫纸鸢量化优选": -3.81,
    "碳硅1号": -0.25,
    "顽岩量化选股1号": -5.89,
    "正仁股票择时一期": -0.37,
    "格林基金鲲鹏6号": -12.57,
    "赢仕安盈二号": 0.51,
    "具力芒种1号": -3.12,
    "时间序列红利增强1号": -2.52,
    "积沐领航者": -3.56,
    "旌安思源1号B类": 0.33,
    "涌泉君安三号": 0.28,
    "铭跃行远均衡一号": -0.38,
    "正仁双创择时一号": -4.26,
    "特夫郁金香全量化": 0.19,
    "海鹏扬帆": -2.89,
}

mismatch = []
for fund in fund_data:
    if not fund["has_data"]:
        continue
    name = fund["name"]
    html_week = fund["week_return"]
    if name in session_data:
        session_week = session_data[name]
        diff = html_week - session_week
        print(f"{name:<25} {html_week:>10.2f} {session_week:>10.2f} {diff:>10.4f}")
        if abs(diff) > 0.01:
            mismatch.append({
                "name": name,
                "html": html_week,
                "session": session_week,
                "diff": diff
            })

print("\n" + "-" * 60)
if mismatch:
    print(f"\n发现 {len(mismatch)} 处不一致：")
    for item in mismatch:
        print(f"  {item['name']}: HTML={item['html']:.4f}%, 会话={item['session']:.2f}%, 差异={item['diff']:.4f}%")
else:
    print(f"\n✓ 所有数据四舍五入后完全一致，没有差异")

# 再检查计算区间说明
print("\n=== 计算区间说明 ===")
print("HTML中计算的近一周是：从7天前到最新净值日")
print("不同基金最新净值日不同（有的到26日，有的到27日，两只补全的只到20日）")
print("我会话中汇总的时候：")
print("  - 最新净值日到26/27日的：计算起点是3月22日，终点是26/27日")
print("  - 瀚鑫和时间序列最新只到20日：所以它们的周收益就是3月13日-20日那一周")
print("\n你说的不一致，是不是因为两只补全的基金最新数据只到3月20日，所以它们显示的近一周是截止到20日，而不是27日？")
