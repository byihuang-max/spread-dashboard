#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Tushare 新闻接口权限
"""
import tushare as ts
from datetime import datetime, timedelta

# Tushare token
TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
ts.set_token(TOKEN)
pro = ts.pro_api()

# 测试拉取最近1小时的新闻
end_time = datetime.now()
start_time = end_time - timedelta(hours=1)

print(f"测试时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
print("\n正在测试新闻接口权限...\n")

sources = ['sina', 'wallstreetcn', 'cls', 'yicai']

for src in sources:
    try:
        df = pro.news(
            src=src,
            start_date=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_date=end_time.strftime('%Y-%m-%d %H:%M:%S')
        )
        print(f"✅ {src}: 成功，获取 {len(df)} 条新闻")
        if len(df) > 0:
            print(f"   最新一条: {df.iloc[0]['title'][:50]}...")
    except Exception as e:
        print(f"❌ {src}: {str(e)}")
    print()
