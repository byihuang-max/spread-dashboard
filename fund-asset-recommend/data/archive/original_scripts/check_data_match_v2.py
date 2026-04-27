# -*- coding: utf-8 -*-
"""
检查HTML中的数据和会话中输出的数据是否一致
"""
import json

# 读取HTML文件提取fundData
with open('/Users/huangqingmeng/.openclaw/workspace/GAMT_Dashboard_final_20260329.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到const fundData开始，找到结束的];
json_lines = []
started = False
for line in lines:
    if 'const fundData = ' in line:
        started = True
        json_lines.append(line.split('const fundData = ')[1])
    elif started and '];' in line:
        json_lines.append(line.split('];')[0] + ']')
        break
    elif started:
        json_lines.append(line)

json_str = ''.join(json_lines)
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
        if abs(diff) > 0.02:  # 允许四舍五入误差
            mismatch.append({
                "name": name,
                "html": html_week,
                "session": session_week,
                "diff": diff
            })

print("\n" + "-" * 60)
if mismatch:
    print(f"\n发现 {len(mismatch)} 处差异超过0.02%：")
    for item in mismatch:
        print(f"  {item['name']}: HTML={item['html']:.2f}% | 会话={item['session']:.2f}% | 差异={item['diff']:.4f}%")
else:
    print(f"\n✓ 所有数据四舍五入到两位小数完全一致")

print("\n=== 关键说明：计算区间差异 ===")
print("• HTML里\"近一周\"的定义：自然日过去7天，根据每只基金最新净值日自动计算起点")
print("• 我在会话里汇总的：")
print("  - 多数基金最新净值到 3月26/27日：近一周 = 3月22日 ~ 3月26/27日")
print("  - 瀚鑫纸鸢、时间序列最新净值只到 3月20日：近一周 = 3月13日 ~ 3月20日")
print("\n你看到的不一致，是不是这个原因？还是具体哪几只数据对不上？")
