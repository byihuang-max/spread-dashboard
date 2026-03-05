#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观 Meme 叙事生命周期模型
=============================
核心逻辑：
  舆情热度（每日关键词频次打分）→ 多周均线趋势 → 生命周期阶段判断

与题材交易的本质区别：
  - 题材交易关注"事件波"（1-5天尖峰）
  - 宏观 Meme 交易关注"热度趋势"（数周到数月的积累与消退）
  - 核心问题：这个叙事是否正在成为"共识"？共识化=机会关闭

四个阶段：
  🌱 新兴  — 热度刚从低位升起，市场尚未定价，最大配置窗口
  🔥 积累  — 持续升温，价格开始跟随，窗口收窄中
  ⚡ 共识  — 热度高位稳定，已成市场共识，慎追
  📉 消退  — 热度下行，叙事衰退，注意反向信号

判断维度（加权投票）：
  1. 历史分位（热度在自身历史中的位置）
  2. 动量（MA7斜率，用周均线过滤噪声）
  3. 持续时长（连续活跃天数）
  4. 价格确认（叙事热但价格未动 = 窗口期；价格已动 = 共识期）

数据来源：
  narrative_history.json（narrative_monitor.py 每日写入）
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime

# ==================== 路径配置 ====================
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# 读取叙事历史（由 narrative_monitor.py 每日生成）
HISTORY_FILE = PROJECT_ROOT / "daily_report" / "meme交易" / "cache" / "narrative_history.json"

# 输出文件
OUTPUT_FILE = SCRIPT_DIR / "lifecycle_output.json"

# 活跃阈值：得分 >= ACTIVE_THRESHOLD 才算"活跃"
ACTIVE_THRESHOLD = 4

# 各叙事对应资产（用于生命周期报告的提示）
NARRATIVE_ASSETS = {
    "AI_CapEx":   {"name": "AI CapEx 超级周期", "assets": "纳指/半导体ETF/铜"},
    "去美元化":    {"name": "去美元化",          "assets": "黄金/BTC"},
    "全球再武装":  {"name": "全球再武装",         "assets": "国防股/稀有金属"},
    "财政主导":    {"name": "财政主导",           "assets": "黄金/实物资产"},
    "地缘风险":    {"name": "地缘风险",           "assets": "黄金/原油"},
    "美国衰退":    {"name": "美国衰退预期",        "assets": "美债/黄金"},
    "中国刺激":    {"name": "中国刺激预期",        "assets": "A股/港股/铜"},
    "通胀通缩":    {"name": "通胀/通缩预期",       "assets": "黄金/大宗商品"},
}


# ==================== 数据加载 ====================
def load_history() -> dict:
    """加载叙事历史，返回 {date: {narrative_key: score}}"""
    if not HISTORY_FILE.exists():
        print(f"⚠️  历史文件不存在: {HISTORY_FILE}")
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_series(history: dict) -> dict:
    """
    将历史数据转换为各叙事的时序得分列表
    返回 {narrative_key: [(date, score), ...]} 按日期升序
    """
    all_dates = sorted(history.keys())
    series = {}

    for date in all_dates:
        day_data = history[date]
        for key, score in day_data.items():
            if key not in series:
                series[key] = []
            series[key].append((date, float(score)))

    return series


# ==================== 指标计算 ====================
def calc_ma(scores: list, window: int) -> list:
    """计算移动平均（不足 window 天时用现有数据均值）"""
    result = []
    for i in range(len(scores)):
        start = max(0, i - window + 1)
        result.append(np.mean(scores[start:i+1]))
    return result


def calc_hist_percentile(scores: list, current_val: float) -> float:
    """
    计算 current_val 在 scores 序列中的历史分位
    分位越高 = 热度越罕见（越接近历史高峰）
    """
    if len(scores) < 3:
        return 50.0  # 数据不足时返回中位
    return float(np.mean([s <= current_val for s in scores])) * 100


def calc_duration_active(series_scores: list, threshold: float) -> int:
    """
    从序列末尾往前数，连续高于阈值的天数
    = 本次"活跃事件"已持续多少天
    """
    count = 0
    for s in reversed(series_scores):
        if s >= threshold:
            count += 1
        else:
            break
    return count


def calc_momentum(ma7_series: list, lookback: int = 7) -> float:
    """
    MA7 的近期斜率（每天平均涨/跌多少分）
    用最小二乘法拟合，避免端点噪声
    """
    window = min(lookback, len(ma7_series))
    if window < 2:
        return 0.0
    y = np.array(ma7_series[-window:])
    x = np.arange(window)
    slope = np.polyfit(x, y, 1)[0]
    return round(float(slope), 3)


# ==================== 生命周期判断 ====================
def determine_stage(
    hist_pct: float,
    momentum: float,
    duration: int,
    ma7: float,
    ma28: float,
) -> dict:
    """
    四维加权投票，判断生命周期阶段

    维度投票规则：
      hist_pct  → 位置投票（高分位=成熟/共识，低分位=新兴）
      momentum  → 方向投票（上升=早期，下降=消退）
      duration  → 时长投票（短=新兴，长=成熟）
      ma7/ma28  → 趋势确认（MA7 > MA28 = 上行趋势）

    返回：{stage, stage_emoji, action, confidence}
    """
    # --- 消退：最优先判断（动量下行 + 曾经高位）---
    if momentum < -0.3 and hist_pct > 40:
        return {
            "stage": "消退",
            "stage_emoji": "📉",
            "action": "叙事降温，关注对应资产反向机会",
            "confidence": "高" if momentum < -0.5 else "中",
        }

    # --- 共识：高位稳定，机会窗口关闭 ---
    if hist_pct >= 70 and abs(momentum) <= 0.3 and duration >= 10:
        return {
            "stage": "共识",
            "stage_emoji": "⚡",
            "action": "市场已定价，慎追；等待消退后反向或等下一波新兴",
            "confidence": "高" if hist_pct >= 80 else "中",
        }

    # --- 新兴：热度刚升起，最大配置窗口 ---
    if hist_pct < 45 and momentum > 0.1 and duration <= 10:
        return {
            "stage": "新兴",
            "stage_emoji": "🌱",
            "action": "最佳配置窗口，市场尚未充分定价，关注对应资产",
            "confidence": "高" if (momentum > 0.3 and duration <= 5) else "中",
        }

    # --- 积累：持续升温中 ---
    if momentum >= 0 and ma7 >= ACTIVE_THRESHOLD:
        return {
            "stage": "积累",
            "stage_emoji": "🔥",
            "action": "窗口收窄中，仍可参与但需控制仓位",
            "confidence": "中",
        }

    # --- 默认：低温观察 ---
    return {
        "stage": "观察",
        "stage_emoji": "🔍",
        "action": "热度偏低，暂无明确信号",
        "confidence": "低",
    }


# ==================== 主分析函数 ====================
def analyze_lifecycle(history: dict) -> dict:
    """
    对所有叙事计算生命周期指标
    返回完整分析结果
    """
    series = build_series(history)
    results = {}

    for key, datapoints in series.items():
        dates = [d for d, _ in datapoints]
        scores = [s for _, s in datapoints]

        # 需要至少3天数据
        if len(scores) < 2:
            results[key] = {
                "stage": "数据不足",
                "stage_emoji": "⏳",
                "action": "需要至少3天历史数据",
                "confidence": "低",
                "metrics": {"days_of_data": len(scores)},
            }
            continue

        # 计算均线
        ma7_series  = calc_ma(scores, 7)
        ma28_series = calc_ma(scores, 28)

        current_score = scores[-1]
        current_ma7   = ma7_series[-1]
        current_ma28  = ma28_series[-1]

        # 历史分位（用MA7序列，更平滑）
        hist_pct = calc_hist_percentile(ma7_series, current_ma7)

        # 动量（MA7斜率）
        momentum = calc_momentum(ma7_series, lookback=7)

        # 持续活跃天数
        duration = calc_duration_active(scores, ACTIVE_THRESHOLD)

        # 阶段判断
        stage_info = determine_stage(hist_pct, momentum, duration, current_ma7, current_ma28)

        results[key] = {
            **stage_info,
            "metrics": {
                "current_score": current_score,
                "ma7":           round(current_ma7,  2),
                "ma28":          round(current_ma28, 2),
                "hist_pct":      round(hist_pct, 1),
                "momentum":      momentum,
                "duration_days": duration,
                "days_of_data":  len(scores),
                "latest_date":   dates[-1],
            },
        }

    return results


# ==================== 报告生成 ====================
def print_report(results: dict):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  宏观 Meme 叙事生命周期报告  {now}")
    print(f"{'='*60}")

    # 按阶段权重排序（新兴/积累优先展示）
    stage_order = {"新兴": 0, "积累": 1, "共识": 2, "消退": 3, "观察": 4, "数据不足": 5}
    sorted_items = sorted(
        results.items(),
        key=lambda x: stage_order.get(x[1].get("stage", "观察"), 5)
    )

    for key, data in sorted_items:
        info = NARRATIVE_ASSETS.get(key, {"name": key, "assets": "-"})
        m = data.get("metrics", {})

        print(f"\n{data['stage_emoji']} 【{data['stage']}】 {info['name']}")
        print(f"   资产映射: {info['assets']}")

        if m.get("days_of_data", 0) >= 2:
            print(f"   当日得分: {m.get('current_score')}/10  "
                  f"MA7: {m.get('ma7')}  MA28: {m.get('ma28')}")
            print(f"   历史分位: {m.get('hist_pct')}%  "
                  f"动量: {m.get('momentum'):+.2f}/天  "
                  f"持续: {m.get('duration_days')}天")
            print(f"   置信度: {data.get('confidence')}  |  {data.get('action')}")
        else:
            print(f"   {data.get('action')}")

    print(f"\n{'='*60}")
    print("⚠️  注意：宏观Meme交易关注周级别趋势，建议数据积累≥14天后参考")
    print(f"{'='*60}\n")


# ==================== 主入口 ====================
def main():
    print("[宏观生命周期] 加载历史数据...")
    history = load_history()

    if not history:
        print("❌ 无历史数据，请先运行 narrative_monitor.py 积累数据")
        return

    print(f"✅ 加载 {len(history)} 天历史数据（{sorted(history.keys())[0]} ~ {sorted(history.keys())[-1]}）")

    results = analyze_lifecycle(history)

    # 打印报告
    print_report(results)

    # 写出 JSON
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days_of_history": len(history),
        "results": results,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 结果已保存: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
