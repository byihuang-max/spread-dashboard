#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO 交易计算模块
- 计算相对强弱（标的 vs 本地基准）
- 整合叙事热度
- 生成场景判断
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================

DATA_DIR = Path(__file__).parent / "data"
PRICE_CSV = DATA_DIR / "halo_prices.csv"
OUTPUT_JSON = DATA_DIR / "halo_analysis.json"

# 叙事监控系统输出路径
LIFECYCLE_JSON = Path(__file__).parent.parent / "meme" / "lifecycle_output.json"

# 标的 → 基准映射
TICKER_TO_BENCHMARK = {
    # 美股 → SPY
    "CEG": "SPY", "GEV": "SPY", "NEE": "SPY", "ETN": "SPY",
    "LMT": "SPY", "RTX": "SPY",
    "XOM": "SPY", "JPM": "SPY",
    
    # 日股 → 日经225
    "9501.T": "^N225", "9503.T": "^N225",
    "7011.T": "^N225", "7012.T": "^N225",
    "8058.T": "^N225", "8306.T": "^N225",
    
    # 韩股 → KOSPI
    "015760.KS": "^KS11", "012450.KS": "^KS11", "009540.KS": "^KS11",
    "005490.KS": "^KS11", "105560.KS": "^KS11",
    
    # A股 → 沪深300
    "600900.SS": "000300.SS", "601985.SS": "000300.SS",
    "600150.SS": "000300.SS", "600760.SS": "000300.SS",
    "601857.SS": "000300.SS", "600036.SS": "000300.SS",
}


# ==================== 数据加载 ====================

def load_prices():
    """加载价格数据"""
    df = pd.read_csv(PRICE_CSV, parse_dates=["date"])
    print(f"✅ 加载价格数据：{len(df)} 行")
    return df


def load_narrative_scores():
    """从叙事监控系统读取最新热度分数"""
    if not LIFECYCLE_JSON.exists():
        print("⚠️  叙事监控数据不存在，跳过")
        return {}
    
    with open(LIFECYCLE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    results = data.get("results", {})
    scores = {
        "AI_CapEx": results.get("AI_CapEx", {}).get("score", 0),
        "全球再武装": results.get("全球再武装", {}).get("score", 0),
        "地缘风险": results.get("地缘风险", {}).get("score", 0),
        "通胀通缩": results.get("通胀通缩", {}).get("score", 0),
    }
    print(f"✅ 叙事热度：AI={scores['AI_CapEx']}, 再武装={scores['全球再武装']}, 地缘={scores['地缘风险']}, 通胀={scores['通胀通缩']}")
    return scores


# ==================== 相对强弱计算 ====================

def calculate_relative_strength(df, window=20):
    """
    计算相对强弱：标的 vs 基准
    - 相对强弱 = (标的涨跌幅 - 基准涨跌幅) 的累计
    - window: 计算窗口（天）
    """
    print(f"⏳ 计算相对强弱（窗口={window}天）...")
    
    # 透视表：date × ticker
    pivot = df.pivot(index="date", columns="ticker", values="close")
    
    # 计算收益率
    returns = pivot.pct_change()
    
    results = []
    for ticker, benchmark in TICKER_TO_BENCHMARK.items():
        if ticker not in returns.columns or benchmark not in returns.columns:
            continue
        
        # 相对收益 = 标的收益 - 基准收益
        rel_return = returns[ticker] - returns[benchmark]
        
        # 填充 NaN（不同市场休市日不同）
        rel_return = rel_return.fillna(0)
        
        # 滚动窗口累计相对强弱
        rel_strength = rel_return.rolling(window, min_periods=1).sum() * 100  # 转为百分比
        
        # 最新值
        latest = rel_strength.iloc[-1] if not rel_strength.empty else 0
        
        # 获取标的信息
        stock_info = df[df["ticker"] == ticker].iloc[0]
        
        results.append({
            "ticker": ticker,
            "name": stock_info["name"],
            "theme": stock_info["theme"],
            "benchmark": benchmark,
            "rel_strength_20d": round(float(latest), 2) if pd.notna(latest) else 0,
            "latest_price": round(float(pivot[ticker].iloc[-1]), 2) if pd.notna(pivot[ticker].iloc[-1]) else None,
        })
    
    print(f"✅ 完成 {len(results)} 只标的")
    return results


# ==================== 场景判断 ====================

def judge_scenario(rel_strength_data, narrative_scores):
    """
    根据相对强弱 + 叙事热度判断 HALO 场景
    
    场景定义：
    - 逻辑强化：AI_CapEx热度>7 且 能耗主线相对强弱>0
    - 估值充分：相对强弱平稳但未转负
    - 逻辑受损：叙事热度<3 或 相对强弱转负
    """
    # 按主线分组计算平均相对强弱
    theme_strength = {}
    for theme in ["AI能耗", "地缘重装", "价值兑现"]:
        stocks = [s for s in rel_strength_data if s["theme"] == theme]
        if stocks:
            avg = sum(s["rel_strength_20d"] for s in stocks) / len(stocks)
            theme_strength[theme] = round(avg, 2)
        else:
            theme_strength[theme] = 0
    
    # 判断逻辑
    ai_hot = narrative_scores.get("AI_CapEx", 0) > 7
    defense_hot = narrative_scores.get("全球再武装", 0) > 5 or narrative_scores.get("地缘风险", 0) > 5
    
    energy_strong = theme_strength.get("AI能耗", 0) > 0
    defense_strong = theme_strength.get("地缘重装", 0) > 0
    
    if ai_hot and energy_strong:
        scenario = "逻辑强化"
        action = "继续持有，能耗主线可加仓"
    elif defense_hot and defense_strong:
        scenario = "逻辑强化"
        action = "地缘重装主线受益，关注国防标的"
    elif theme_strength.get("AI能耗", 0) < -5:
        scenario = "逻辑受损"
        action = "能耗主线转弱，考虑减仓"
    else:
        scenario = "估值充分"
        action = "等待盈利兑现或新催化"
    
    return {
        "scenario": scenario,
        "action": action,
        "theme_strength": theme_strength,
        "narrative_scores": narrative_scores,
    }


# ==================== 主流程 ====================

def main():
    print("=" * 60)
    print("HALO 交易分析")
    print("=" * 60)
    
    # 1. 加载数据
    df = load_prices()
    narrative_scores = load_narrative_scores()
    
    # 2. 计算相对强弱
    rel_strength = calculate_relative_strength(df, window=20)
    
    # 3. 场景判断
    judgment = judge_scenario(rel_strength, narrative_scores)
    
    # 4. 输出
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scenario": judgment["scenario"],
        "action": judgment["action"],
        "theme_strength": judgment["theme_strength"],
        "narrative_scores": judgment["narrative_scores"],
        "stocks": rel_strength,
    }
    
    # 将 NaN 转为 None（JSON 中的 null）
    import json
    output_str = json.dumps(output, ensure_ascii=False, indent=2, default=lambda x: None if pd.isna(x) else x)
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        f.write(output_str)
    
    print("=" * 60)
    print(f"✅ 场景判断：{judgment['scenario']}")
    print(f"   操作建议：{judgment['action']}")
    print(f"   主线强弱：{judgment['theme_strength']}")
    print(f"✅ 结果已保存：{OUTPUT_JSON}")
    print("=" * 60)


if __name__ == "__main__":
    main()
