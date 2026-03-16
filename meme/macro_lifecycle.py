#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观 Meme 叙事生命周期模型（增量版）
=============================
核心逻辑：
  舆情热度（每日关键词频次打分）→ 多周均线趋势 → 生命周期阶段判断

与题材交易的本质区别：
  - 题材交易关注"事件波"（1-5天尖峰）
  - 宏观 Meme 交易关注"热度趋势"（数周到数月的积累与消退）
  - 核心问题：这个叙事是否正在成为"共识"？共识化 = 机会关闭

四个阶段：
  🌱 新兴  — 热度刚从低位升起，市场尚未定价，最大配置窗口
  🔥 积累  — 持续升温，价格开始跟随，窗口收窄中
  ⚡ 共识  — 热度高位稳定，已成市场共识，慎追
  📉 消退  — 热度下行，叙事衰退，关注反向机会

增量模式：
  - 读取 lifecycle_output.json 获取上次处理的最新日期
  - 只对新增日期进行分析
  - 追加写 lifecycle_history.csv（不覆盖旧数据）
  - 覆盖写 lifecycle_output.json（最新快照）

输出文件：
  meme/lifecycle_output.json    — 最新一次所有叙事的完整快照
  meme/lifecycle_history.csv    — 全量历史时序（每行=某天某叙事的指标）
"""

import json
import csv
import numpy as np
from pathlib import Path
from datetime import datetime

# ==================== 路径配置 ====================
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

HISTORY_FILE     = PROJECT_ROOT / "daily_report" / "meme交易" / "cache" / "narrative_history.json"
OUTPUT_JSON      = SCRIPT_DIR / "lifecycle_output.json"
OUTPUT_CSV       = SCRIPT_DIR / "lifecycle_history.csv"

ACTIVE_THRESHOLD = 4   # 得分 >= 此值才算"活跃"

CSV_FIELDS = [
    "date", "narrative_key", "narrative_name",
    "score", "ma7", "ma28",
    "hist_pct", "momentum", "duration_days",
    "stage", "stage_emoji", "confidence", "action",
]

NARRATIVE_ASSETS = {
    "AI_CapEx":   {"name": "AI CapEx 超级周期",   "assets": "纳指/半导体ETF/铜"},
    "去美元化":    {"name": "去美元化",             "assets": "黄金/BTC"},
    "全球再武装":  {"name": "全球再武装",            "assets": "国防股/稀有金属"},
    "财政主导":    {"name": "财政主导",              "assets": "黄金/实物资产"},
    "地缘风险":    {"name": "地缘风险",              "assets": "黄金/原油"},
    "美国衰退":    {"name": "美国衰退预期",           "assets": "美债/黄金"},
    "中国刺激":    {"name": "中国刺激预期",           "assets": "A股/港股/铜"},
    "通胀通缩":    {"name": "通胀/通缩预期",          "assets": "黄金/大宗商品"},
}


# ==================== 数据加载 ====================
def load_history() -> dict:
    if not HISTORY_FILE.exists():
        print(f"⚠️  历史文件不存在: {HISTORY_FILE}")
        return {}
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_key_news() -> dict:
    """
    从最新的 narrative_YYYYMMDD_HHMM.json 读取每条叙事的：
    - key_news：重点新闻标题（最多3条，已去重）
    - matched_count：命中条数（原始舆情强度）
    - total_news：当日去重总新闻量（分母）
    返回 {narrative_key: {"key_news": [...], "matched_count": N, "total_news": N}}
    """
    cache_dir = HISTORY_FILE.parent
    files = sorted(cache_dir.glob("narrative_2*.json"), reverse=True)
    if not files:
        return {}
    try:
        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        # V2版本用 fixed_analysis，兼容旧版 analysis
        analysis = data.get("fixed_analysis") or data.get("analysis", {})
        result = {}
        for key, val in analysis.items():
            # V2版本 key_news 是对象列表，旧版是字符串列表
            raw = val.get("key_news", [])
            seen, deduped = set(), []
            for item in raw:
                # 兼容新旧格式
                if isinstance(item, dict):
                    title = item.get("title", "")
                else:
                    title = str(item)
                t = title.strip()
                if t and t != "nan" and t not in seen:
                    seen.add(t)
                    deduped.append(t)
                if len(deduped) >= 3:
                    break
            result[key] = {
                "key_news":      deduped,
                "matched_count": val.get("matched_count", None),
                "total_news":    data.get("news_count", None),
            }
        return result
    except Exception as e:
        print(f"⚠️  读取 key_news 失败: {e}")
        return {}


def load_last_processed_date() -> str | None:
    """从 lifecycle_output.json 读取上次处理的最新日期"""
    if not OUTPUT_JSON.exists():
        return None
    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("latest_date")
    except Exception:
        return None


def load_existing_csv_dates() -> set:
    """读取 CSV 中已写入的 (date, key) 集合，避免重复写入"""
    existing = set()
    if not OUTPUT_CSV.exists():
        return existing
    with open(OUTPUT_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing.add((row["date"], row["narrative_key"]))
    return existing


def build_series(history: dict) -> dict:
    """返回 {narrative_key: [(date, score), ...]} 按日期升序"""
    all_dates = sorted(history.keys())
    series: dict = {}
    for date in all_dates:
        for key, score in history[date].items():
            if key not in series:
                series[key] = []
            series[key].append((date, float(score)))
    return series


# ==================== 指标计算 ====================
def calc_ma(scores: list, window: int) -> list:
    result = []
    for i in range(len(scores)):
        start = max(0, i - window + 1)
        result.append(np.mean(scores[start:i+1]))
    return result


def calc_hist_percentile(series: list, current_val: float) -> float:
    if len(series) < 3:
        return 50.0
    return float(np.mean([s <= current_val for s in series])) * 100


def calc_duration_active(scores: list, threshold: float) -> int:
    count = 0
    for s in reversed(scores):
        if s >= threshold:
            count += 1
        else:
            break
    return count


def calc_momentum(ma7_series: list, lookback: int = 7) -> float:
    window = min(lookback, len(ma7_series))
    if window < 2:
        return 0.0
    y = np.array(ma7_series[-window:])
    x = np.arange(window)
    slope = np.polyfit(x, y, 1)[0]
    return round(float(slope), 3)


# ==================== 生命周期判断 ====================
def determine_stage(hist_pct, momentum, duration, ma7, ma28) -> dict:
    # 消退优先判
    if momentum < -0.3 and hist_pct > 40:
        return {
            "stage": "消退", "stage_emoji": "📉",
            "action": "叙事降温，关注对应资产反向机会",
            "confidence": "高" if momentum < -0.5 else "中",
        }
    # 共识
    if hist_pct >= 70 and abs(momentum) <= 0.3 and duration >= 10:
        return {
            "stage": "共识", "stage_emoji": "⚡",
            "action": "市场已定价，慎追；等待消退后反向或等下一波新兴",
            "confidence": "高" if hist_pct >= 80 else "中",
        }
    # 新兴
    if hist_pct < 45 and momentum > 0.1 and duration <= 10:
        return {
            "stage": "新兴", "stage_emoji": "🌱",
            "action": "最佳配置窗口，市场尚未充分定价，关注对应资产",
            "confidence": "高" if (momentum > 0.3 and duration <= 5) else "中",
        }
    # 积累
    if momentum >= 0 and ma7 >= ACTIVE_THRESHOLD:
        return {
            "stage": "积累", "stage_emoji": "🔥",
            "action": "窗口收窄中，仍可参与但需控制仓位",
            "confidence": "中",
        }
    # 低温观察
    return {
        "stage": "观察", "stage_emoji": "🔍",
        "action": "热度偏低，暂无明确信号",
        "confidence": "低",
    }


# ==================== 全量历史计算 ====================
def compute_all_rows(history: dict) -> list[dict]:
    """
    计算所有历史日期的每条叙事指标
    返回：[{date, narrative_key, ..., stage, ...}, ...]  按日期升序
    """
    series_map = build_series(history)
    all_dates  = sorted(history.keys())
    rows = []

    for key, datapoints in series_map.items():
        dates  = [d for d, _ in datapoints]
        scores = [s for _, s in datapoints]
        info   = NARRATIVE_ASSETS.get(key, {"name": key, "assets": "-"})

        ma7_series  = calc_ma(scores, 7)
        ma28_series = calc_ma(scores, 28)

        for i, (date, score) in enumerate(datapoints):
            if i < 1:
                continue   # 至少需要前1天才能算动量/分位

            current_ma7  = ma7_series[i]
            current_ma28 = ma28_series[i]
            hist_pct     = calc_hist_percentile(ma7_series[:i+1], current_ma7)
            momentum     = calc_momentum(ma7_series[:i+1], lookback=7)
            duration     = calc_duration_active(scores[:i+1], ACTIVE_THRESHOLD)
            stage_info   = determine_stage(hist_pct, momentum, duration, current_ma7, current_ma28)

            rows.append({
                "date":           date,
                "narrative_key":  key,
                "narrative_name": info["name"],
                "score":          score,
                "ma7":            round(current_ma7, 2),
                "ma28":           round(current_ma28, 2),
                "hist_pct":       round(hist_pct, 1),
                "momentum":       momentum,
                "duration_days":  duration,
                **stage_info,
            })

    return sorted(rows, key=lambda r: (r["date"], r["narrative_key"]))


# ==================== 增量写 CSV ====================
def append_new_rows_to_csv(all_rows: list[dict], existing_pairs: set):
    """只追加 CSV 中还没有的 (date, key) 行"""
    new_rows = [
        r for r in all_rows
        if (r["date"], r["narrative_key"]) not in existing_pairs
    ]
    if not new_rows:
        return 0

    write_header = not OUTPUT_CSV.exists() or OUTPUT_CSV.stat().st_size == 0

    with open(OUTPUT_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for row in new_rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})

    return len(new_rows)


# ==================== 写 JSON 快照 ====================
def write_json_snapshot(all_rows: list[dict], history: dict):
    """取最新日期的所有叙事写入 JSON（含重点新闻 + 舆情强度）"""
    if not all_rows:
        return
    latest_date = max(r["date"] for r in all_rows)
    latest_rows = [r for r in all_rows if r["date"] == latest_date]

    # 加载最新重点新闻 + 匹配条数
    latest_info = load_latest_key_news()

    results = {}
    for r in latest_rows:
        k = r["narrative_key"]
        info = latest_info.get(k, {})
        results[k] = {
            **r,
            "key_news":      info.get("key_news", []),       # 重点事件（最多3条，已去重）
            "matched_count": info.get("matched_count"),       # 命中条数（原始舆情强度）
            "total_news":    info.get("total_news"),          # 当日去重总新闻量
        }

    snapshot = {
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_date":     latest_date,
        "days_of_history": len(history),
        "results":         results,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


# ==================== 控制台报告 ====================
def print_report(all_rows: list[dict]):
    if not all_rows:
        print("⚠️  无数据可展示")
        return

    latest_date = max(r["date"] for r in all_rows)
    latest_rows = [r for r in all_rows if r["date"] == latest_date]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*62}")
    print(f"  宏观 Meme 叙事生命周期报告  {now}")
    print(f"  最新数据日期：{latest_date}")
    print(f"{'='*62}")

    stage_order = {"新兴": 0, "积累": 1, "共识": 2, "消退": 3, "观察": 4}
    latest_rows.sort(key=lambda x: stage_order.get(x["stage"], 5))

    for r in latest_rows:
        info = NARRATIVE_ASSETS.get(r["narrative_key"], {"name": r["narrative_key"], "assets": "-"})
        print(f"\n{r['stage_emoji']} 【{r['stage']}】 {info['name']}")
        print(f"   资产：{info['assets']}")
        print(f"   得分 {r['score']}/10  MA7:{r['ma7']}  MA28:{r['ma28']}")
        print(f"   历史分位:{r['hist_pct']}%  动量:{r['momentum']:+.2f}/天  持续:{r['duration_days']}天")
        print(f"   置信度:{r['confidence']}  |  {r['action']}")

    print(f"\n{'='*62}\n")


# ==================== 主入口 ====================
def main():
    print("[宏观生命周期·增量] 加载历史数据...")
    history = load_history()
    if not history:
        print("❌ 无历史数据，请先运行 narrative_monitor.py 或 backfill_history.py")
        return

    dates = sorted(history.keys())
    print(f"✅ 历史 {len(history)} 天（{dates[0]} ~ {dates[-1]}）")

    # 计算所有历史行
    print("⏳ 计算生命周期指标...")
    all_rows = compute_all_rows(history)
    print(f"✅ 计算完成，共 {len(all_rows)} 行数据")

    # 增量追加 CSV
    existing_pairs = load_existing_csv_dates()
    added = append_new_rows_to_csv(all_rows, existing_pairs)
    print(f"✅ CSV 新增 {added} 行 → {OUTPUT_CSV}")

    # 写 JSON 快照
    write_json_snapshot(all_rows, history)
    print(f"✅ JSON 快照已更新 → {OUTPUT_JSON}")

    # 打印报告
    print_report(all_rows)


if __name__ == "__main__":
    main()
