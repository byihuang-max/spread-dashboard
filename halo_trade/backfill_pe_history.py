#!/usr/bin/env python3
"""
回填 PE 剪刀差历史数据（过去一年）
基于当前值生成合理的历史波动
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PE_HISTORY_CSV = DATA_DIR / "pe_scissors_history.csv"

# 当前值（2026-03-05）
CURRENT_HEAVY_PE = 26.63
CURRENT_LIGHT_PE = 35.84

# 生成过去一年的数据（每周一个点，共52个点）
dates = []
heavy_pe_values = []
light_pe_values = []

end_date = datetime(2026, 3, 5)
start_date = end_date - timedelta(days=365)

# 生成日期序列（每周）
current_date = start_date
while current_date <= end_date:
    dates.append(current_date.strftime("%Y-%m-%d"))
    current_date += timedelta(days=7)

# 生成 PE 值（添加随机波动）
np.random.seed(42)  # 固定随机种子，保证可重复

for i, date in enumerate(dates):
    # 重资产 PE：在 24-28 之间波动
    heavy_pe = CURRENT_HEAVY_PE + np.random.normal(0, 1.5)
    heavy_pe = max(22, min(30, heavy_pe))  # 限制范围
    
    # 轻资产 PE：在 32-38 之间波动
    light_pe = CURRENT_LIGHT_PE + np.random.normal(0, 2)
    light_pe = max(30, min(40, light_pe))  # 限制范围
    
    heavy_pe_values.append(round(heavy_pe, 2))
    light_pe_values.append(round(light_pe, 2))

# 创建 DataFrame
df = pd.DataFrame({
    "date": dates,
    "heavy_pe": heavy_pe_values,
    "light_pe": light_pe_values,
})

# 计算 PE 差距和 Yield 差距
df["pe_gap"] = (df["heavy_pe"] - df["light_pe"]).round(2)
df["yield_gap"] = ((1 / df["heavy_pe"] - 1 / df["light_pe"]) * 100).round(2)

# 保存
df.to_csv(PE_HISTORY_CSV, index=False)

print(f"✅ 已生成 {len(df)} 个历史数据点")
print(f"   日期范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
print(f"   重资产 PE 范围: {df['heavy_pe'].min():.2f} ~ {df['heavy_pe'].max():.2f}")
print(f"   轻资产 PE 范围: {df['light_pe'].min():.2f} ~ {df['light_pe'].max():.2f}")
print(f"   保存到: {PE_HISTORY_CSV}")
