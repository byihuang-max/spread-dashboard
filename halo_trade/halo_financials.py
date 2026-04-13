#!/usr/bin/env python3
"""
HALO 财务指标模块 - AkShare 美股财报版
1. CapEx 二阶导（超大规模科技）
PE 剪刀差由 halo_pe_scissors.py 单独生成
"""
import json
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
FINANCIAL_JSON = DATA_DIR / "halo_financials.json"

HYPERSCALERS = {
    "MSFT": "微软",
    "AMZN": "亚马逊",
    "GOOGL": "谷歌",
    "META": "Meta",
}


def fetch_capex_data():
    print("⏳ 拉取 CapEx 数据...")
    results = {}
    for ticker, name in HYPERSCALERS.items():
        try:
            df = ak.stock_financial_us_report_em(stock=ticker, symbol='现金流量表', indicator='单季报')
            if df.empty:
                print(f"  ⚠️  {name} 无现金流数据")
                continue
            df = df[df['ITEM_NAME'] == '购买固定资产'].copy()
            if df.empty:
                print(f"  ⚠️  {name} 无 CapEx 数据")
                continue
            df['date'] = pd.to_datetime(df['REPORT_DATE'])
            df['capex'] = pd.to_numeric(df['AMOUNT'], errors='coerce').abs()
            df = df[['date', 'capex']].dropna().sort_values('date').drop_duplicates(subset=['date'], keep='first')
            if len(df) < 3:
                print(f"  ⚠️  {name} CapEx 数据不足")
                continue
            results[ticker] = df.reset_index(drop=True)
            print(f"  ✅ {name}: {len(df)} 个季度")
        except Exception as e:
            print(f"  ❌ {name} 拉取失败: {e}")
    return results


def calculate_capex_derivatives(capex_data):
    print("⏳ 计算 CapEx 二阶导...")
    results = {}
    for ticker, df in capex_data.items():
        if len(df) < 3:
            continue
        df = df.copy()
        df['qoq_growth'] = df['capex'].pct_change() * 100
        df['yoy_growth'] = df['capex'].pct_change(4) * 100
        df['second_derivative'] = df['qoq_growth'].diff()
        latest = df.iloc[-1]
        if pd.notna(latest['second_derivative']):
            if latest['second_derivative'] > 5:
                trend, signal = '加速', '🟢'
            elif latest['second_derivative'] < -5:
                trend, signal = '减速', '🔴'
            else:
                trend, signal = '平稳', '🟡'
        else:
            trend, signal = '数据不足', '⚪'
        history = []
        for _, row in df.tail(8).iterrows():
            history.append({
                'quarter': row['date'].strftime('%Y-%m-%d'),
                'capex': round(float(row['capex']) / 1e9, 2) if pd.notna(row['capex']) else None,
                'yoy_growth': round(float(row['yoy_growth']), 2) if pd.notna(row['yoy_growth']) else None,
                'second_derivative': round(float(row['second_derivative']), 2) if pd.notna(row['second_derivative']) else None,
            })
        results[ticker] = {
            'name': HYPERSCALERS[ticker],
            'latest': {
                'capex': round(float(latest['capex']) / 1e9, 2),
                'qoq_growth': round(float(latest['qoq_growth']), 2) if pd.notna(latest['qoq_growth']) else None,
                'yoy_growth': round(float(latest['yoy_growth']), 2) if pd.notna(latest['yoy_growth']) else None,
                'second_derivative': round(float(latest['second_derivative']), 2) if pd.notna(latest['second_derivative']) else None,
                'trend': trend,
                'signal': signal,
                'quarter': latest['date'].strftime('%Y-%m-%d'),
            },
            'history': history,
        }
    print(f"✅ 完成 {len(results)} 家公司")
    return results


def main():
    print('=' * 60)
    print('HALO 财务指标计算（AkShare）')
    print('=' * 60)
    capex_data = fetch_capex_data()
    capex_deriv = calculate_capex_derivatives(capex_data)

    if FINANCIAL_JSON.exists():
        output = json.loads(FINANCIAL_JSON.read_text(encoding='utf-8'))
    else:
        output = {}

    output['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    output['capex_second_derivative'] = capex_deriv

    with open(FINANCIAL_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print('=' * 60)
    print('✅ CapEx 二阶导:')
    for ticker, data in capex_deriv.items():
        latest = data['latest']
        print(f"   {ticker:6} {data['name']:6} CapEx={latest['capex']}B, YoY={latest['yoy_growth']}%, 二阶导={latest['second_derivative']}% {latest['signal']}")
    print(f"✅ 结果已保存：{FINANCIAL_JSON}")
    print('=' * 60)


if __name__ == '__main__':
    main()
