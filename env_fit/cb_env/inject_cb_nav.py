#!/usr/bin/env python3
"""
转债产品净值注入脚本
从 size_spread/fund_nav/fund_nav_convertible.json 读取净值数据
注入到 index.html 的转债归因分析图表
"""
import json
import re
from pathlib import Path

def inject_cb_nav():
    # 路径
    root = Path(__file__).parent.parent.parent
    nav_file = root / 'size_spread/fund_nav/fund_nav_convertible.json'
    html_file = root / 'index.html'
    
    # 读取净值数据
    with open(nav_file, 'r', encoding='utf-8') as f:
        nav_data = json.load(f)
    
    fund = nav_data['fund']
    chart = fund['chart']
    
    # 读取 HTML
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 构造注入内容
    dates_str = json.dumps(chart['dates'], ensure_ascii=False)
    fund_str = json.dumps([round(x*100-100, 2) for x in chart['fund_nav']], ensure_ascii=False)
    index_str = json.dumps([round(x*100-100, 2) for x in chart['index_nav']], ensure_ascii=False)
    excess_str = json.dumps([round(x*100, 2) for x in chart['excess']], ensure_ascii=False)
    
    # 计算基准回撤（>2%标红）
    index_nav = chart['index_nav']
    bench_dd = []
    peak = index_nav[0]
    for nav in index_nav:
        if nav > peak:
            peak = nav
        dd = (nav / peak - 1) * 100
        bench_dd.append(round(dd, 2) if dd < -2 else None)
    bench_dd_str = json.dumps(bench_dd, ensure_ascii=False)
    
    # 活跃度数据（暂时用 null，后续从 cb_env.json 补充）
    activity_str = '[' + ','.join(['null'] * len(chart['dates'])) + ']'
    
    # 更新统计信息
    info_line = f"产品收益 {fund['total_return']:.2f}% · 基准 {fund['index_return']:.2f}% · 超额 {fund['excess_return']:.2f}% · {fund['date_range']}"
    
    # 替换 HTML 中的数据
    # 1. 统计信息行
    html = re.sub(
        r'产品收益 [\d.]+% · 基准 [\d.]+% · 超额 [\d.]+% · [\d-]+ ~ [\d-]+',
        info_line,
        html
    )
    
    # 2. 日期数组
    html = re.sub(
        r'var cbDecompDates = \[.*?\];',
        f'var cbDecompDates = {dates_str};',
        html,
        flags=re.DOTALL
    )
    
    # 3. 产品收益
    html = re.sub(
        r'var cbFund = \[.*?\];',
        f'var cbFund = {fund_str};',
        html,
        flags=re.DOTALL
    )
    
    # 4. 基准收益
    html = re.sub(
        r'var cbIndex = \[.*?\];',
        f'var cbIndex = {index_str};',
        html,
        flags=re.DOTALL
    )
    
    # 5. 超额收益
    html = re.sub(
        r'var cbExcess = \[.*?\];',
        f'var cbExcess = {excess_str};',
        html,
        flags=re.DOTALL
    )
    
    # 6. 基准回撤
    html = re.sub(
        r'var cbBenchDD = \[.*?\];',
        f'var cbBenchDD = {bench_dd_str};',
        html,
        flags=re.DOTALL
    )
    
    # 7. 活跃度（暂时保持 null）
    html = re.sub(
        r'var cbActivity = \[.*?\];',
        f'var cbActivity = {activity_str};',
        html,
        flags=re.DOTALL
    )
    
    # 写回 HTML
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 转债净值数据已注入 index.html")
    print(f"   数据点数: {len(chart['dates'])}")
    print(f"   日期范围: {fund['date_range']}")
    print(f"   产品收益: {fund['total_return']:.2f}%")
    print(f"   基准收益: {fund['index_return']:.2f}%")
    print(f"   超额收益: {fund['excess_return']:.2f}%")

if __name__ == '__main__':
    inject_cb_nav()
