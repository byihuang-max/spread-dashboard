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
    "AI_CapEx":   [
        "英伟达", "NVIDIA", "博通", "Broadcom", "AMD",
        "H100", "H200", "B200", "B100", "GB200", "Blackwell", "Hopper",
        "HBM", "CoWoS", "AI芯片", "GPU集群", "算力集群",
        "AI数据中心", "AI资本开支", "AI CapEx",
        "AWS算力", "Azure AI", "谷歌TPU",
        "OpenAI融资", "Anthropic", "大模型训练", "推理算力",
    ],
    "去美元化":   [
        "央行购金", "黄金储备", "去美元化", "黄金ETF",
        "BRICS结算", "人民币国际化", "储备货币多元化",
        "美元霸权", "SWIFT替代", "抛售美债",
        "金价创新高", "黄金价格",
    ],
    "全球再武装":  [
        "国防预算", "军费增加", "北约", "NATO",
        "欧洲军备", "德国军费", "防务支出", "军事开支",
        "洛克希德", "雷神", "军工股", "武器出口",
        "军备竞赛", "防务预算",
    ],
    "财政主导":   [
        "美国国债", "美国赤字", "美国债务上限", "DOGE", "美联储资产负债表",
        "特别国债", "地方政府债务", "城投债", "中国财政赤字",
        "YCC", "日本国债", "植田和男", "日本央行政策",
        "收益率曲线控制", "财政扩张",
    ],
    "地缘风险":   [
        "以色列", "伊朗", "哈马斯", "加沙", "黎巴嫩真主党",
        "俄乌", "乌克兰", "泽连斯基",
        "台海", "台湾军事", "台海紧张",
        "朝鲜导弹", "朝鲜核",
        "出口管制", "贸易战", "关税报复",
        "军事打击", "空袭", "停火协议", "地缘政治风险",
    ],
    "美国衰退":   [
        "非农就业", "美国失业率", "初请失业金",
        "美国GDP收缩", "美国经济衰退", "美国消费者信心",
        "科技裁员", "大规模裁员", "美国消费疲软",
        "ISM制造业", "美国零售销售下滑",
    ],
    "中国刺激":   [
        "降息", "降准", "PBOC宽松", "中国货币政策",
        "消费补贴", "以旧换新", "房地产救市", "限购取消",
        "两会GDP", "政府工作报告增长目标", "中国PMI", "中国社零",
        "中国经济刺激",
    ],
    "通胀通缩":   [
        "美国CPI", "美国PCE", "美国PPI", "核心通胀", "服务通胀", "薪资通胀",
        "美联储加息", "美联储降息", "FOMC", "美联储利率",
        "日本央行加息", "日银加息", "日本利率", "植田和男通胀",
        "中国CPI", "中国PPI", "中国通缩", "中国物价",
        "能源通胀", "大宗商品通胀", "供应链通胀", "粮食价格",
        "通胀预期", "通缩压力", "滞涨", "再通胀", "盈亏平衡通胀率",
    ],
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
    """
    与 narrative_monitor.py 完全相同的评分逻辑（v2）
    1. 跨源去重（按标题）
    2. 标题命中 ≥1 个关键词 → 匹配
    3. 标题未命中，正文命中 ≥2 个关键词 → 才算匹配
    """
    if not news_list:
        return {k: 0 for k in NARRATIVES}

    # 跨源去重
    seen_titles, deduped = set(), []
    for news in news_list:
        title = str(news.get("title", "")).strip()
        if not title or title == "nan":
            continue
        if title not in seen_titles:
            seen_titles.add(title)
            deduped.append(news)

    if not deduped:
        return {k: 0 for k in NARRATIVES}

    results = {}
    for key, keywords in NARRATIVES.items():
        matched = 0
        for news in deduped:
            title   = str(news.get("title",   "")).strip().lower()
            content = str(news.get("content", "")).strip().lower()

            title_hits = sum(1 for kw in keywords if kw.lower() in title)
            if title_hits >= 1:
                matched += 1
                continue

            content_hits = sum(1 for kw in keywords if kw.lower() in content)
            if content_hits >= 2:
                matched += 1

        ratio = matched / max(len(deduped), 1) * 100
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
