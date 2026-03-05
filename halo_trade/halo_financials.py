#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO 财务指标模块
1. CapEx 二阶导（超大规模科技）
2. 重资产 vs 轻资产 EPS 剪刀差
"""

import yfinance as yf
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

# ==================== 配置 ====================

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

FINANCIAL_JSON = DATA_DIR / "halo_financials.json"

# 超大规模科技（CapEx 追踪）
HYPERSCALERS = {
    "微软": "MSFT",
    "亚马逊": "AMZN", 
    "谷歌": "GOOGL",
    "Meta": "META",
}

# 重资产 ETF（公用事业 + 能源 + 国防）
HEAVY_ASSET_ETFS = {
    "公用事业": "XLU",
    "能源": "XLE",
    "国防": "ITA",
}

# 轻资产 ETF（软件 + 科技）
LIGHT_ASSET_ETFS = {
    "软件": "IGV",
    "科技": "XLK",
}


# ==================== CapEx 二阶导 ====================

def fetch_capex_data():
    """
    拉取超大规模科技公司的季度 CapEx
    返回：{ticker: DataFrame(date, capex)}
    """
    print("⏳ 拉取 CapEx 数据...")
    results = {}
    
    for name, ticker in HYPERSCALERS.items():
        try:
            stock = yf.Ticker(ticker)
            cf = stock.quarterly_cashflow
            
            if cf.empty or 'Capital Expenditure' not in cf.index:
                print(f"  ⚠️  {name} 无 CapEx 数据")
                continue
            
            # CapEx 通常是负数，取绝对值
            capex = cf.loc['Capital Expenditure'].abs()
            capex = capex.sort_index()  # 按时间排序
            
            df = pd.DataFrame({
                'date': capex.index,
                'capex': capex.values
            })
            
            results[ticker] = df
            print(f"  ✅ {name}: {len(df)} 个季度")
            
        except Exception as e:
            print(f"  ❌ {name} 拉取失败: {e}")
    
    return results


def calculate_capex_derivatives(capex_data):
    """
    计算 CapEx 一阶导（QoQ 增速）和二阶导（增速变化率）
    改用 QoQ 而非 YoY，因为历史数据不够深
    返回：{ticker: {latest: {...}, history: [...]}}
    """
    print("⏳ 计算 CapEx 二阶导...")
    results = {}
    
    for ticker, df in capex_data.items():
        if len(df) < 3:  # 至少需要 3 个季度
            continue
        
        # 计算 QoQ 增速（一阶导）
        df['qoq_growth'] = df['capex'].pct_change() * 100  # 环比增速
        
        # 计算 YoY 增速（如果数据足够）
        df['yoy_growth'] = df['capex'].pct_change(4) * 100  # 同比增速
        
        # 计算二阶导（QoQ 增速的变化）
        df['second_derivative'] = df['qoq_growth'].diff()
        
        # 最新值
        latest = df.iloc[-1]
        
        # 判断趋势（基于二阶导）
        if pd.notna(latest['second_derivative']):
            if latest['second_derivative'] > 5:
                trend = "加速"
                signal = "🟢"
            elif latest['second_derivative'] < -5:
                trend = "减速"
                signal = "🔴"
            else:
                trend = "平稳"
                signal = "🟡"
        else:
            trend = "数据不足"
            signal = "⚪"
        
        # 历史数据（最近8个季度）
        history = []
        for _, row in df.tail(8).iterrows():
            history.append({
                "quarter": str(row['date'].date()),
                "capex": round(float(row['capex']) / 1e9, 2) if pd.notna(row['capex']) else None,
                "yoy_growth": round(float(row['yoy_growth']), 2) if pd.notna(row['yoy_growth']) else None,
                "second_derivative": round(float(row['second_derivative']), 2) if pd.notna(row['second_derivative']) else None,
            })
        
        results[ticker] = {
            "name": [k for k, v in HYPERSCALERS.items() if v == ticker][0],
            "latest": {
                "capex": round(float(latest['capex']) / 1e9, 2),
                "qoq_growth": round(float(latest['qoq_growth']), 2) if pd.notna(latest['qoq_growth']) else None,
                "yoy_growth": round(float(latest['yoy_growth']), 2) if pd.notna(latest['yoy_growth']) else None,
                "second_derivative": round(float(latest['second_derivative']), 2) if pd.notna(latest['second_derivative']) else None,
                "trend": trend,
                "signal": signal,
                "quarter": str(latest['date'].date()),
            },
            "history": history
        }
    
    print(f"✅ 完成 {len(results)} 家公司")
    return results


# ==================== EPS 剪刀差 ====================

def fetch_pe_ratios(etf_dict):
    """
    拉取 ETF 的 PE 比率
    """
    results = {}
    
    for name, ticker in etf_dict.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 获取 trailing PE
            pe = info.get('trailingPE')
            
            if pe and pe > 0:
                results[ticker] = {
                    'name': name,
                    'pe': round(pe, 2),
                }
                print(f"  ✅ {name}: PE={pe:.2f}")
            else:
                print(f"  ⚠️  {name} ({ticker}) PE 数据缺失")
                
        except Exception as e:
            print(f"  ❌ {name} 拉取失败: {e}")
    
    return results


def calculate_eps_scissors():
    """
    计算重资产 vs 轻资产估值剪刀差
    使用 PE 比率：PE 越低 = 估值越便宜 = earnings yield 越高
    """
    print("⏳ 拉取 PE 数据...")
    
    heavy_data = fetch_pe_ratios(HEAVY_ASSET_ETFS)
    light_data = fetch_pe_ratios(LIGHT_ASSET_ETFS)
    
    if not heavy_data or not light_data:
        print("⚠️  PE 数据不足，跳过剪刀差计算")
        return None
    
    # 计算平均 PE
    heavy_pe = sum(d['pe'] for d in heavy_data.values()) / len(heavy_data)
    light_pe = sum(d['pe'] for d in light_data.values()) / len(light_data)
    
    # PE 差值（负数 = 重资产更便宜）
    pe_gap = heavy_pe - light_pe
    
    # Earnings Yield 差值（正数 = 重资产收益率更高）
    heavy_yield = (1 / heavy_pe) * 100
    light_yield = (1 / light_pe) * 100
    yield_gap = heavy_yield - light_yield
    
    result = {
        "heavy_asset_pe": round(heavy_pe, 2),
        "light_asset_pe": round(light_pe, 2),
        "pe_gap": round(pe_gap, 2),
        "heavy_earnings_yield": round(heavy_yield, 2),
        "light_earnings_yield": round(light_yield, 2),
        "yield_gap": round(yield_gap, 2),
        "interpretation": f"重资产 PE {heavy_pe:.1f} vs 轻资产 PE {light_pe:.1f}，" + 
                         ("重资产估值更便宜" if pe_gap < 0 else "轻资产估值更便宜"),
        "heavy_details": list(heavy_data.values()),
        "light_details": list(light_data.values()),
    }
    
    print(f"✅ PE 剪刀差: 重资产 {heavy_pe:.1f} vs 轻资产 {light_pe:.1f}")
    return result


# ==================== 主流程 ====================

def main():
    print("=" * 60)
    print("HALO 财务指标计算")
    print("=" * 60)
    
    # 1. CapEx 二阶导
    capex_data = fetch_capex_data()
    capex_results = calculate_capex_derivatives(capex_data)
    
    # 2. EPS 剪刀差
    eps_scissors = calculate_eps_scissors()
    
    # 3. 输出
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "capex_second_derivative": capex_results,
        "eps_scissors": eps_scissors,
    }
    
    with open(FINANCIAL_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print("✅ CapEx 二阶导:")
    for ticker, data in capex_results.items():
        latest = data['latest']
        print(f"   {latest['signal']} {data['name']}: {latest['yoy_growth']}% YoY, 二阶导 {latest['second_derivative']} ({latest['trend']})")
    
    if eps_scissors:
        print(f"\n✅ PE 剪刀差: 重资产 {eps_scissors['heavy_asset_pe']} vs 轻资产 {eps_scissors['light_asset_pe']}")
        print(f"   {eps_scissors['interpretation']}")
        print(f"   Earnings Yield 差距: {eps_scissors['yield_gap']} 百分点")
    
    print(f"\n✅ 结果已保存：{FINANCIAL_JSON}")
    print("=" * 60)


if __name__ == "__main__":
    main()
