#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
叙事监控系统 V2 - 4个固定叙事 + LLM动态发现
每天 08:30 和 20:30 推送到飞书
"""
import tushare as ts
import json
import requests
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 ====================
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
FEISHU_APP_ID = "cli_a91c36caf5785cb2"
FEISHU_APP_SECRET = "HWhYR833N0xObKumrjNCKdRSHq3jg0zi"
RONI_OPEN_ID = "ou_4f9c4d14f2e27f4863a5e2743dba3482"

# LLM配置（aicanapi中转）
OPENAI_API_KEY = "sk-nPKqBvGbB3I0aewJoZQBLLUDtU6N8pl7JlXn5qxMwt2bbWm0"
OPENAI_BASE_URL = "https://aicanapi.com/v1"
OPENAI_MODEL = "gpt-5.4"

# 路径
SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
HISTORY_FILE = CACHE_DIR / "narrative_history.json"

pro = ts.pro_api(TUSHARE_TOKEN)

# ==================== 4个核心固定叙事 ====================
NARRATIVES = {
    "地缘风险": {
        "keywords": [
            "以色列", "伊朗", "哈马斯", "加沙", "黎巴嫩真主党",
            "俄罗斯", "乌克兰", "普京", "泽连斯基",
            "台海", "南海", "朝鲜", "金正恩",
            "霍尔木兹海峡", "石油禁运", "制裁",
        ],
        "description": "战争、冲突、制裁"
    },
    "AI_CapEx": {
        "keywords": [
            "英伟达", "NVIDIA", "博通", "Broadcom", "AMD",
            "H100", "H200", "B200", "Blackwell", "Hopper",
            "HBM", "CoWoS", "AI芯片", "GPU集群", "算力集群",
            "AI数据中心", "AI资本开支", "AI CapEx",
            "OpenAI融资", "Anthropic", "大模型训练",
        ],
        "description": "算力、芯片、大模型"
    },
    "中国政策": {
        "keywords": [
            "国务院常务会议", "政治局会议", "中央经济工作会议",
            "降准", "降息", "LPR", "MLF", "逆回购",
            "特别国债", "地方政府债务", "城投债",
            "房地产新政", "保交楼", "三道红线",
            "消费刺激", "以旧换新", "家电补贴",
        ],
        "description": "刺激、地产、货币财政"
    },
    "全球央行": {
        "keywords": [
            "美联储", "鲍威尔", "FOMC", "加息", "降息", "点阵图",
            "欧央行", "拉加德", "ECB",
            "日本央行", "植田和男", "YCC", "日元干预",
            "英国央行", "加拿大央行", "澳洲联储",
        ],
        "description": "美联储、欧央行、日央行加息降息"
    },
}

# ==================== 拉取新闻 ====================
def fetch_news(hours=12):
    """拉取最近N小时的新闻"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    all_news = []
    sources = ['wallstreetcn', 'cls', 'sina']

    for src in sources:
        try:
            df = pro.news(
                src=src,
                start_date=start_time.strftime('%Y-%m-%d %H:%M:%S'),
                end_date=end_time.strftime('%Y-%m-%d %H:%M:%S')
            )
            if len(df) > 0:
                for _, row in df.iterrows():
                    title = str(row.get('title', '')).strip()
                    if title and title != 'nan':
                        all_news.append({
                            "time": row['datetime'],
                            "title": title,
                            "content": str(row.get('content', '')).strip(),
                            "source": src
                        })
        except Exception as e:
            print(f"拉取 {src} 失败: {e}")

    # 按标题去重
    seen_titles, deduped = set(), []
    for news in all_news:
        if news['title'] not in seen_titles:
            seen_titles.add(news['title'])
            deduped.append(news)

    # 按时间倒序
    deduped.sort(key=lambda x: x['time'], reverse=True)
    return deduped

# ==================== 固定叙事分析 ====================
def analyze_fixed_narratives(news_list):
    """分析4个固定叙事"""
    results = {}

    for key, narrative in NARRATIVES.items():
        keywords = narrative['keywords']
        matched_news = []

        for news in news_list:
            title = news['title'].lower()
            content = news.get('content', '').lower()

            # 标题命中任意1个关键词
            title_hits = sum(1 for kw in keywords if kw.lower() in title)
            if title_hits >= 1:
                matched_news.append((news, title_hits + 10))
                continue

            # 正文命中至少2个关键词
            content_hits = sum(1 for kw in keywords if kw.lower() in content)
            if content_hits >= 2:
                matched_news.append((news, content_hits))

        # 按命中数排序
        matched_news.sort(key=lambda x: x[1], reverse=True)
        matched_count = len(matched_news)

        # 评分
        match_ratio = matched_count / max(len(news_list), 1) * 100
        score = min(10, int(match_ratio * 2))

        results[key] = {
            "score": score,
            "matched_count": matched_count,
            "total_news": len(news_list),
            "key_news": [
                n['title'][:60]
                for n, _ in matched_news[:3]
            ],
            "matched_news_objects": [n for n, _ in matched_news]  # 保存匹配的新闻对象
        }

    return results

# ==================== LLM动态主题发现 ====================
def call_llm(prompt):
    """调用LLM"""
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个金融新闻分析专家，擅长从大量新闻中提取核心主题。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1500
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        result = resp.json()

        if "choices" not in result:
            print(f"❌ LLM API错误: {result}")
            return None

        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ LLM调用失败: {e}")
        return None

def discover_dynamic_themes(unmatched_news, top_n=5):
    """从未匹配的新闻中发现动态主题"""
    if len(unmatched_news) < 10:
        return []
    
    # 只取前200条标题
    titles = [n["title"] for n in unmatched_news[:200]]
    
    prompt = f"""
以下是今天的{len(titles)}条财经新闻标题。请分析这些新闻，找出最热门的{top_n}个主题。

新闻标题：
{chr(10).join(f"{i+1}. {t}" for i, t in enumerate(titles))}

请以JSON格式返回，格式如下：
[
  {{
    "theme": "主题名称（简短精准，5-10个字）",
    "count": 相关新闻条数（估算）, 
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "examples": ["代表性标题1", "代表性标题2", "代表性标题3"]
  }}
]

要求：
1. 主题名要简短（5-10个字）
2. 只返回真正有热度的主题（至少5条相关新闻）
3. 主题之间不要重叠
4. 直接返回JSON数组，不要其他文字
"""
    
    response = call_llm(prompt)
    if not response:
        return []
    
    # 解析JSON
    try:
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
            response = response.strip()
        
        themes = json.loads(response)
        return themes
    except Exception as e:
        print(f"❌ 解析LLM响应失败: {e}")
        return []


def enrich_dynamic_themes(themes, unmatched_news, max_news=8):
    """为动态主题补充可展开的新闻列表"""
    enriched = []

    for theme in themes:
        keywords = [str(k).strip() for k in theme.get('keywords', []) if str(k).strip()]
        examples = [str(x).strip() for x in theme.get('examples', []) if str(x).strip()]
        scored = []

        for news in unmatched_news:
            title = str(news.get('title', '')).strip()
            content = str(news.get('content', '')).strip()
            haystack = f"{title} {content}".lower()

            score = 0
            for kw in keywords:
                kw_l = kw.lower()
                if kw_l in title.lower():
                    score += 3
                elif kw_l in haystack:
                    score += 1

            for ex in examples:
                if ex and title == ex:
                    score += 10

            if score > 0:
                scored.append((score, news))

        scored.sort(key=lambda x: (-x[0], x[1].get('time', '')), reverse=False)

        seen = set()
        news_items = []
        for _, news in scored:
            title = str(news.get('title', '')).strip()
            if not title or title in seen:
                continue
            seen.add(title)
            news_items.append({
                'title': title,
                'time': news.get('time', ''),
                'source': news.get('source', ''),
            })
            if len(news_items) >= max_news:
                break

        theme = dict(theme)
        theme['news_list'] = news_items
        theme['news_count_real'] = len(news_items)
        enriched.append(theme)

    return enriched

# ==================== 历史管理 ====================
def load_history():
    """加载历史数据"""
    if not HISTORY_FILE.exists():
        return {}
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_history(analysis):
    """保存当前评分到历史"""
    history = load_history()
    today = datetime.now().strftime('%Y-%m-%d')

    history[today] = {
        key: data['score'] for key, data in analysis.items()
    }

    # 只保留最近400天
    dates = sorted(history.keys())
    if len(dates) > 400:
        for old_date in dates[:-400]:
            del history[old_date]

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_trend(key, days=7):
    """计算叙事趋势"""
    history = load_history()
    dates = sorted(history.keys())[-days:]

    if len(dates) < 2:
        return "➡️", 0

    scores = [history[d].get(key, 0) for d in dates]
    change = scores[-1] - scores[0]

    if change > 2:
        return "📈", change
    elif change < -2:
        return "📉", change
    else:
        return "➡️", change

# ==================== 生成报告 ====================
def generate_report(fixed_analysis, dynamic_themes, news_count):
    """生成飞书报告"""
    now = datetime.now().strftime("%m-%d %H:%M")

    report = f"📊 叙事监控 V2 {now} | 分析 {news_count} 条新闻\n\n"

    # 固定叙事
    report += "🔖 固定叙事监控\n"
    sorted_fixed = sorted(
        fixed_analysis.items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )

    for key, data in sorted_fixed:
        score = data['score']
        trend_emoji, trend_val = get_trend(key, days=7)

        report += f"{key}: {score}/10 {trend_emoji}\n"
        # 显示前3条代表性新闻
        if score >= 3 and data['key_news']:
            for news_title in data['key_news'][:3]:
                if news_title:
                    report += f"  📌 {news_title}\n"

    # 动态主题
    if dynamic_themes:
        report += f"\n🆕 今日新兴主题（LLM发现）\n"
        for i, theme in enumerate(dynamic_themes, 1):
            report += f"{i}. {theme['theme']} ({theme['count']}条)\n"
            report += f"   关键词: {', '.join(theme['keywords'][:3])}\n"
            # 显示前3条代表性新闻
            for ex in theme['examples'][:3]:
                if ex:
                    report += f"   📌 {ex}\n"

    return report

# ==================== 飞书推送 ====================
def get_feishu_token():
    """获取飞书 access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    }
    resp = requests.post(url, json=payload)
    return resp.json()["tenant_access_token"]

def generate_feishu_card(fixed_analysis, dynamic_themes, news_count):
    """生成飞书交互式卡片"""
    now = datetime.now().strftime("%m-%d %H:%M")

    # 卡片元素列表
    elements = []

    # 标题
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📊 叙事监控 V2** {now} | 分析 {news_count} 条新闻"
        }
    })

    elements.append({"tag": "hr"})

    # 固定叙事
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "**🔖 固定叙事监控**"
        }
    })

    sorted_fixed = sorted(
        fixed_analysis.items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )

    for key, data in sorted_fixed:
        score = data['score']
        trend_emoji, _ = get_trend(key, days=7)

        # 构建内容
        content = f"**{key}**: {score}/10 {trend_emoji}\n"

        # 如果有新闻，直接添加到内容里
        if score >= 3 and data['key_news']:
            for i, news_title in enumerate(data['key_news'][:3], 1):
                if news_title:
                    # 获取完整新闻内容
                    news_obj = next((n for n in data.get('matched_news_objects', []) if n['title'] == news_title), None)
                    news_content = news_obj.get('content', '') if news_obj else ''

                    # 截取内容前150字
                    if news_content and news_content != 'nan':
                        preview = news_content[:150] + "..." if len(news_content) > 150 else news_content
                        content += f"  {i}. {news_title}\n     _{preview}_\n"
                    else:
                        content += f"  {i}. {news_title}\n"

        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content
            }
        })

    elements.append({"tag": "hr"})

    # 动态主题
    if dynamic_themes:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**🆕 今日新兴主题（LLM发现）**"
            }
        })

        for i, theme in enumerate(dynamic_themes, 1):
            # 构建内容
            content = f"**{i}. {theme['theme']}** ({theme['count']}条)\n"
            content += f"关键词: {', '.join(theme['keywords'][:3])}\n"

            # 添加新闻列表
            for j, ex in enumerate(theme['examples'][:3], 1):
                if ex:
                    content += f"  {j}. {ex}\n"

            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content
                }
            })

    # 构建完整卡片
    card = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "📊 叙事监控 V2"
            },
            "template": "blue"
        },
        "elements": elements
    }

    return card

def send_to_feishu_card(fixed_analysis, dynamic_themes, news_count):
    """推送交互式卡片到飞书"""
    token = get_feishu_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    card = generate_feishu_card(fixed_analysis, dynamic_themes, news_count)

    payload = {
        "receive_id": RONI_OPEN_ID,
        "msg_type": "interactive",
        "content": json.dumps(card)
    }

    params = {"receive_id_type": "open_id"}
    resp = requests.post(url, headers=headers, json=payload, params=params)
    return resp.json()

def send_to_feishu(report):
    """推送报告到飞书（纯文本，保留作为备用）"""
    token = get_feishu_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "receive_id": RONI_OPEN_ID,
        "msg_type": "text",
        "content": json.dumps({"text": report})
    }

    params = {"receive_id_type": "open_id"}
    resp = requests.post(url, headers=headers, json=payload, params=params)
    return resp.json()

# ==================== 主函数 ====================
def main():
    print(f"[{datetime.now()}] 开始叙事监控 V2...")

    # 1. 拉取新闻
    news = fetch_news(hours=12)
    print(f"✅ 拉取到 {len(news)} 条新闻（去重后）")

    # 2. 分析固定叙事
    fixed_analysis = analyze_fixed_narratives(news)
    print(f"✅ 完成固定叙事分析")

    # 3. 找出未匹配的新闻
    matched_titles = set()
    for data in fixed_analysis.values():
        for n in data.get('matched_news_objects', []):
            matched_titles.add(n['title'])

    unmatched_news = [n for n in news if n['title'] not in matched_titles]
    print(f"✅ 未匹配新闻: {len(unmatched_news)} 条")

    # 4. LLM发现动态主题
    print(f"🔍 LLM分析中...")
    dynamic_themes = discover_dynamic_themes(unmatched_news, top_n=5)
    dynamic_themes = enrich_dynamic_themes(dynamic_themes, unmatched_news)
    print(f"✅ 发现 {len(dynamic_themes)} 个动态主题")

    # 5. 保存历史
    save_history(fixed_analysis)
    print(f"✅ 保存历史数据")

    # 6. 生成报告（纯文本，用于保存）
    report = generate_report(fixed_analysis, dynamic_themes, len(news))
    print(f"✅ 生成报告")

    # 7. 推送飞书交互式卡片
    result = send_to_feishu_card(fixed_analysis, dynamic_themes, len(news))
    print(f"✅ 推送飞书卡片: {result.get('code')}")

    # 8. 保存到本地
    cache_file = CACHE_DIR / f"narrative_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    latest_file = CACHE_DIR / "narrative_latest.json"

    output_data = {
        "fixed_analysis": {k: {**v, 'matched_news_objects': None} for k, v in fixed_analysis.items()},
        "dynamic_themes": dynamic_themes,
        "report": report,
        "news_count": len(news)
    }

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # 同时保存最新版本供前端读取
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 完成！")

if __name__ == '__main__':
    main()
