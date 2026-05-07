#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海外要闻归纳推送（Opus 4.7）

工作流：
  1. 调 news_email_fetcher 增量抓取
  2. 取今天所有新闻 + 昨天下半天（覆盖 12h 窗口）
  3. 规则筛选 Top 15 候选
  4. Claude Opus 4.7 精筛 Top 3 + 一句话归纳 + 风险等级
  5. 推飞书卡片
  6. 写 overseas_digest_latest.json 供看板读取
"""
import json
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "email_config.json"
CACHE_DIR = SCRIPT_DIR / "cache"
DB_FILE = CACHE_DIR / "email_news_db.json"

# 飞书配置（从 narrative_monitor 复用）
FEISHU_APP_ID = "cli_a91c36caf5785cb2"
FEISHU_APP_SECRET = "HWhYR833N0xObKumrjNCKdRSHq3jg0zi"
RONI_OPEN_ID = "ou_4f9c4d14f2e27f4863a5e2743dba3482"  # 与 narrative_monitor 共用的旧 open_id（当前 app cli_a91c... 对应）

# ==================== 来源权重 ====================
SOURCE_WEIGHT = {
    "彭博社": 10, "Bloomberg": 10,
    "路透社": 10, "Reuters": 10,
    "华尔街日报": 10, "WSJ": 10, "Wall Street Journal": 10,
    "金融时报": 9, "FT": 9,
    "纽约时报": 7, "NYT": 7,
    "CNBC": 7, "BBC": 7,
    "Dow Jones": 8, "道琼斯": 8,
}

# ==================== 高权重关键词（规则层） ====================
HIGH_WEIGHT_KEYWORDS = {
    # 宏观流动性
    "美联储": 5, "Fed": 5, "鲍威尔": 5, "FOMC": 5, "降息": 5, "加息": 5,
    "美债": 4, "收益率": 3, "点阵图": 5,
    "ECB": 3, "日本央行": 3, "BOJ": 3,
    # 中国相关
    "中国": 3, "北京": 2, "中美": 5, "关税": 5, "制裁": 5,
    "习近平": 4, "特朗普": 4, "峰会": 3,
    "人民币": 4, "汇率": 2,
    # 地缘
    "以色列": 4, "伊朗": 4, "俄罗斯": 4, "乌克兰": 3,
    "台湾": 4, "南海": 4, "朝鲜": 3,
    "战争": 4, "冲突": 3, "袭击": 3,
    # 产业链
    "英伟达": 4, "NVIDIA": 4, "台积电": 4, "TSMC": 4,
    "AI芯片": 4, "HBM": 3, "OpenAI": 3,
    # 能源与大宗
    "OPEC": 3, "原油": 3, "油价": 3, "黄金": 2,
}

# ==================== 加载配置 ====================
def load_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_recent_news(hours=12):
    """取最近 N 小时的邮件新闻"""
    if not DB_FILE.exists():
        return []
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        db = json.load(f)

    cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat()
    items = [
        v for v in db["items"].values()
        if v.get("received_at", "") >= cutoff
    ]
    items.sort(key=lambda x: x.get("received_at", ""), reverse=True)
    return items

# ==================== 规则层候选评分 ====================
def rule_score(item):
    """给每条新闻打分，选 Top 15 给 LLM"""
    score = 0
    # 来源权重
    source = item.get("source", "")
    score += SOURCE_WEIGHT.get(source, 3)

    # 关键词权重
    text = f"{item.get('title','')} {item.get('summary','')}"
    for kw, w in HIGH_WEIGHT_KEYWORDS.items():
        if kw in text:
            score += w

    return score

def rule_filter_candidates(news_list, top_n=30):
    scored = [(rule_score(n), n) for n in news_list]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in scored[:top_n]]

# ==================== LLM 精筛（Claude Opus 4.7） ====================
def call_claude(prompt, cfg):
    """Anthropic Messages API"""
    llm = cfg["llm"]
    url = f"{llm['base_url']}/v1/messages"
    headers = {
        "x-api-key": llm["api_key"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": llm["model"],
        "max_tokens": llm.get("max_tokens", 2000),
        "system": "你是一个中国 FOF 基金经理的研究助理，擅长从海外一手财经新闻中提炼对中国资产配置最有参考价值的核心事件。输出必须严格的 JSON，不加任何解释文字。",
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    # Anthropic 响应结构
    if "content" in data and data["content"]:
        return data["content"][0].get("text", "")
    raise RuntimeError(f"LLM 返回异常: {data}")

def parse_json_output(text):
    """容错解析 LLM 输出的 JSON"""
    text = text.strip()
    # 去掉 ```json ... ```
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
    # 找第一个 [ 或 {
    m = re.search(r'[\[{]', text)
    if m:
        text = text[m.start():]
    return json.loads(text)

def llm_pick_top10(candidates, cfg):
    """让 Opus 4.7 从候选里选最多 Top 10（动态数量，只选真正有价值的）"""
    if not candidates:
        return []

    lines = []
    for i, n in enumerate(candidates, 1):
        lines.append(f"{i}. [{n['source']}] {n['title']}")
        if n.get('summary'):
            lines.append(f"   摘要: {n['summary'][:200]}")

    prompt = f"""以下是过去 12 小时的 {len(candidates)} 条海外财经一手新闻（彭博/路透/WSJ 等）。

请从中选出对中国 FOF 基金经理今日配置决策**有参考价值的事件**，**最多 10 条**。

重要原则：
- **宁缺毋滥**：如果真正有价值的只有 4 条，就返回 4 条；不要为了凑满 10 条而放低标准
- **去重合并**：同一事件被多家报道的，合并选最全面的一条
- **按重要性降序排列**
- **人名必须补齐职位/身份**：路透彭博翻译稿往往只写人名不带官职，归纳时要主动补齐。示例：
  - "特朗普" → "美国总统特朗普"
  - "习近平" → "中国国家主席习近平"
  - "普京" → "俄罗斯总统普京"
  - "鲍威尔" → "美联储主席鲍威尔"
  - "内塔尼亚胡" → "以色列总理内塔尼亚胡"
  - "拉加德" → "欧洲央行行长拉加德"
  - "马斯克" → "特斯拉/SpaceX CEO 马斯克"
  - "黄仁勋" → "英伟达 CEO 黄仁勋"
  - 企业高管、央行官员、议员、党派领袖同理，中国读者一眼能认清身份
  - 不确定身份时宁可不简化也不要错标，可查知识中已确定的公共人物

选择标准（按优先级）：
1. 对中国资产有直接影响（中美关系、关税、制裁、地缘）
2. 影响全球流动性（Fed/央行政策、美元、美债、利率）
3. 影响核心产业叙事（AI 算力链、半导体、能源、汽车出海）
4. 影响主要资产价格（原油、黄金、美股财报、大宗商品）

过滤掉：
- 单一公司的非核心动态（除非涉及核心产业链如英伟达/台积电）
- 娱乐/社会新闻
- 单纯数据发布（除非意外偏离预期）

新闻列表：
{chr(10).join(lines)}

输出严格 JSON 数组（不要任何其他文字），格式：
[
  {{
    "index": 候选编号（1-{len(candidates)}）,
    "theme": "主题名（5-10字，如 Fed降息、中美关税）",
    "summary": "一句话归纳（30-50字，只讲事实+影响）",
    "risk_level": "高/中/低",
    "affected_assets": ["美债", "人民币", "港股", "半导体"]
  }}
]

严格按重要性降序，最多 10 条。不够 10 条就少返回。"""

    response = call_claude(prompt, cfg)
    try:
        picks = parse_json_output(response)
        # 回填原始新闻信息
        for pick in picks:
            idx = pick.get("index", 0) - 1
            if 0 <= idx < len(candidates):
                src = candidates[idx]
                pick["source"] = src.get("source", "")
                pick["original_title"] = src.get("title", "")
                pick["url"] = src.get("url", "")
        return picks[:10]  # 硬上限 10 条
    except Exception as e:
        print(f"⚠️ LLM 输出解析失败: {e}")
        print(f"原始输出: {response[:500]}")
        return []

# ==================== 飞书推送 ====================
def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET
    })
    return resp.json()["tenant_access_token"]

def risk_badge(level):
    if level == "高":
        return "高"
    if level == "中":
        return "中"
    if level == "低":
        return "低"
    return level

def build_card(picks, total_count):
    now = datetime.now().strftime("%m-%d %H:%M")
    elements = [
        {"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**海外要闻速递** · {now} · 分析 {total_count} 条 · 精选 {len(picks)} 条"
        }},
        {"tag": "hr"},
    ]

    if not picks:
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "_今日无重大海外事件_"
        }})
    else:
        for i, pick in enumerate(picks, 1):
            content = (
                f"**{i}. {pick.get('theme','?')}** · {risk_badge(pick.get('risk_level','?'))}\n"
                f"{pick.get('summary','')}\n"
            )
            assets = pick.get('affected_assets') or []
            if assets:
                content += f"_影响：{' / '.join(assets)}_\n"
            src = pick.get('source', '')
            url = pick.get('url', '')
            if url:
                content += f"[{src} 原文]({url})"
            elif src:
                content += f"_来源：{src}_"
            elements.append({"tag": "div", "text": {
                "tag": "lark_md", "content": content
            }})
            if i < len(picks):
                elements.append({"tag": "hr"})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"海外要闻 Top {len(picks)}"},
            "template": "indigo",
        },
        "elements": elements,
    }
    return card

def send_feishu_card(card):
    token = get_feishu_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "receive_id": RONI_OPEN_ID,
        "msg_type": "interactive",
        "content": json.dumps(card),
    }
    params = {"receive_id_type": "open_id"}
    resp = requests.post(url, headers=headers, json=payload, params=params)
    return resp.json()

# ==================== 主流程 ====================
def run(push=True):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 海外要闻归纳启动")
    cfg = load_config()

    # 1. 先抓一次增量
    try:
        from news_email_fetcher import run as fetch_run
        fetch_run(mode="incremental")
    except Exception as e:
        print(f"⚠️ 抓取失败，使用现有库: {e}")

    # 2. 取 12h 内的新闻
    lookback = cfg.get("fetch", {}).get("lookback_hours", 12)
    news = load_recent_news(hours=lookback)
    print(f"最近 {lookback}h 共 {len(news)} 条新闻")

    if not news:
        print("⚠️ 无数据，退出")
        return

    # 3. 规则筛选（扩大候选池到 30）
    candidates = rule_filter_candidates(news, top_n=30)
    print(f"规则筛选候选: {len(candidates)} 条")

    # 4. Claude 精筛（最多 10，允许动态少返）
    picks = llm_pick_top10(candidates, cfg)
    print(f"LLM 选出 Top {len(picks)}")
    for p in picks:
        print(f"   - [{p.get('risk_level')}] {p.get('theme')}: {p.get('summary')}")

    # 5. 落盘
    out = {
        "updated_at": datetime.now().isoformat(),
        "lookback_hours": lookback,
        "total_news": len(news),
        "candidates_count": len(candidates),
        "top3": picks,  # 字段名保留 top3 以保持前端/历史兼容，实际承载 Top10
        "picks_count": len(picks),
    }
    latest = CACHE_DIR / "overseas_digest_latest.json"
    snapshot = CACHE_DIR / f"overseas_digest_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(snapshot, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已保存: {latest.name}")

    # 6. 推飞书
    if push and picks:
        card = build_card(picks, len(news))
        result = send_feishu_card(card)
        print(f"飞书推送: code={result.get('code')} msg={result.get('msg')}")

    # 7. 触发反脆弱看板重新渲染（把海外要闻区块刷到页面）
    try:
        import subprocess
        antifragile_dir = SCRIPT_DIR.parent.parent / "macro" / "meme" / "antifragile"
        if (antifragile_dir / "render_html.py").exists():
            r = subprocess.run(
                ["python3", "render_html.py"],
                cwd=str(antifragile_dir),
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                print("反脆弱看板已重新渲染")
            else:
                print(f"⚠️ 渲染失败: {r.stderr[:200]}")
    except Exception as e:
        print(f"⚠️ 触发渲染异常: {e}")

    print("完成")

if __name__ == '__main__':
    import sys
    push = "--no-push" not in sys.argv
    run(push=push)
