#!/usr/bin/env python3
import pandas as pd

# 读取我们已经下载的全部团队跟踪基金
all_dfs = []
for file in [
    'huofuniu_team_track.csv',
    'huofuniu_team_track_page2-4.csv', 
    'huofuniu_team_track_page5-8.csv',
    'huofuniu_team_track_page9-12.csv',
    'missing_found.csv',
]:
    try:
        df = pd.read_csv(file)
        all_dfs.append(df)
        print(f"读取 {file}: {len(df)} 只")
    except:
        pass

full_df = pd.concat(all_dfs, ignore_index=True)
print(f"\n总共读取 {len(full_df)} 只基金")

# 我们要找的目标基金名称
target_names = [
    "顽岩",
    "正仁股票择时",
    "正仁双创",
    "瀚鑫纸鸢",
    "积沐领航",
    "太衍光年",
    "时间序列红利",
    "赢仕安盈",
    "具力芒种",
    "旌安思源",
    "顾锝",
    "立心",
    "翔云",
    "特夫",
    "铭跃行远",
    "碳硅",
    "涌泉君安",
    "海鹏扬帆",
    "鲲鹏",
    "波克",
]

found = []
for idx, row in full_df.iterrows():
    short_name = row['fund_short_name']
    for target in target_names:
        if target in short_name:
            found.append({
                'target': target,
                'found_name': short_name,
                'register_number': row['register_number'],
                'price_type': row['price_type']
            })
            print(f"✅ 找到 '{target}' -> {short_name} [{row['register_number']}]")

print(f"\n总共找到 {len(found)} / {len(target_names)} 只")

df_found = pd.DataFrame(found)
df_found.to_csv('matched_regcodes.csv', index=False, encoding='utf-8-sig')
print("\n已保存到 matched_regcodes.csv")
print(df_found)
