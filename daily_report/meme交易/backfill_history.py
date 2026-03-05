#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史叙事热度回填脚本
====================
向前回填最多 N 天的新闻关键词频次数据，
与 narrative_monitor.py 使用完全相同的评分逻辑，
结果增量写入 narrative_history.json。

用法：
  python3 backfill_history.py           # 默认回填 365 天
  python3 backfill_history.py --days 90 # 回填 90 天
"""

import tushare as ts
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 ====================
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
SCRIPT_DIR    = Path(__file__).parent
HISTORY_FILE  = SCRIPT_DIR / "cache" / "narrative_history.json"
CACHE_DIR     = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 每次批量拉取的天数窗口（减少 API 调用次数）
CHUNK_DAYS = 7
# 请求间隔（秒）
SLEEP_SEC  = 1.5

NARRATIVES = {
    "AI_CapEx":   ["AI", "人工智能", "英伟达", "NVIDIA", "算力", "芯片", "半导体", "HBM", "数据中心", "CapEx", "资本开支"],
    "去美元化":   ["美元", "去美元化", "人民币", "黄金", "央行购金", "储备货币", "SWIFT", "BRICS", "货币贬值", "通胀"],
    "全球再武装":  ["国防", "军费", "武器", "军工", "北约", "军事", "国防预算", "军备"],
    "财政主导":   ["财政赤字", "国债", "财政政策", "实际利率", "收益率曲线", "QE", "量化宽松", "央行"],
    "地缘风险":   ["俄乌", "中东", "台海", "伊朗", "以色列", "战争", "冲突", "制裁", "地缘政治"],
    "美国衰退":   ["衰退", "经济放缓", "失业率", "非农", "GDP", "消费疲软", "企业盈利", "裁员"],
    "中国刺激":   ["中国", "刺激", "降息", "降准", "财政政策", "基建", "房地产", "消费券", "政策宽松"],
    "通胀通缩":   ["通胀", "通缩", "CPI", "PPI", "物价", "价格", "通胀预期", "通缩风险"],
}
SOURCES = ["wallstreetcn", "cls", "sina"]


# ==================== 工具函数 ====================
def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def score_day(news_list: list) -> dict:
    """与 narrative_monitor.py 完全相同的评分逻辑"""
    if not news_list:
        return {k: 0 for k in NARRATIVES}

    results = {}
    for key, keywords in NARRATIVES.items():
        matched = 0
        for news in news_list:
            title   = str(news.get("title", ""))
            content = str(news.get("content", ""))
            if title == "nan" or not title.strip():
                continue
            text = (title + " " + content).lower()
            if any(kw.lower() in text for kw in keywords):
                matched += 1
        ratio = matched / max(len(news_list), 1) * 100
        results[key] = min(10, int(ratio * 2))
    return results


def fetch_chunk(pro, start_dt: datetime, end_dt: datetime) -> dict:
    """
    拉取 [start_dt, end_dt) 范围内所有来源的新闻，
    按日期分组，返回 {date_str: [news, ...]}
    """
    day_news: dict = {}
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str   = end_dt.strftime("%Y-%m-%d %H:%M:%S")

    for src in SOURCES:
        try:
            df = pro.news(src=src, start_date=start_str, end_date=end_str)
            if df is None or len(df) == 0:
                continue
            for _, row in df.iterrows():
                dt_str = str(row.get("datetime", ""))
                if len(dt_str) < 10:
                    continue
                date_key = dt_str[:10]   # "YYYY-MM-DD"
                if date_key not in day_news:
                    day_news[date_key] = []
                day_news[date_key].append({
                    "title":   row.get("title", ""),
                    "content": row.get("content", ""),
                    "source":  src,
                })
        except Exception as e:
            print(f"  ⚠️  {src} 拉取失败: {e}")

    return day_news


# ==================== 主逻辑 ====================
def backfill(days: int = 365):
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    history = load_history()
    existing_dates = set(history.keys())
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 生成需要处理的日期（跳过已有数据的日期）
    all_dates = [
        (today - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, days + 1)     # 从昨天往前
    ]
    needed = [d for d in all_dates if d not in existing_dates]

    if not needed:
        print("✅ 所有日期已有数据，无需回填")
        return

    print(f"📅 需要回填 {len(needed)} 天（共 {days} 天，已有 {len(existing_dates)} 天）")

    # 按 CHUNK_DAYS 分批拉取
    # 将需要的日期倒序排列（从近到远），按 chunk 切割
    needed_sorted = sorted(needed, reverse=True)   # 从最近到最远

    chunks = []
    i = 0
    while i < len(needed_sorted):
        chunk_dates = needed_sorted[i: i + CHUNK_DAYS]
        # chunk 起止：chunk 中最早日期的 00:00 ～ 最晚日期的 23:59
        start = datetime.strptime(min(chunk_dates), "%Y-%m-%d")
        end   = datetime.strptime(max(chunk_dates), "%Y-%m-%d") + timedelta(days=1)
        chunks.append((start, end, chunk_dates))
        i += CHUNK_DAYS

    print(f"🔄 分 {len(chunks)} 批拉取（每批 ≤{CHUNK_DAYS} 天）\n")

    total_filled = 0
    for idx, (start_dt, end_dt, chunk_dates) in enumerate(chunks, 1):
        print(f"[{idx:3d}/{len(chunks)}] {start_dt.date()} ~ {(end_dt-timedelta(days=1)).date()} ...", end=" ", flush=True)

        day_news = fetch_chunk(pro, start_dt, end_dt)

        filled = 0
        for date_str in chunk_dates:
            news = day_news.get(date_str, [])
            scores = score_day(news)
            history[date_str] = scores
            filled += 1

        total_filled += filled
        news_count = sum(len(v) for v in day_news.values())
        print(f"新闻 {news_count:4d} 条 → {filled} 天评分完成")

        # 每批保存一次（防中断丢数据）
        save_history(history)

        if idx < len(chunks):
            time.sleep(SLEEP_SEC)

    print(f"\n✅ 回填完成！新增 {total_filled} 天数据，历史共 {len(history)} 天")
    print(f"   文件: {HISTORY_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365, help="回填天数（默认365）")
    args = parser.parse_args()
    backfill(args.days)
