#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试LLM主题发现功能
"""
import tushare as ts
from datetime import datetime, timedelta
import json
import requests

# ==================== 配置 ====================
TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
OPENAI_API_KEY = "sk-nPKqBvGbB3I0aewJoZQBLLUDtU6N8pl7JlXn5qxMwt2bbWm0"
OPENAI_BASE_URL = "https://aicanapi.com/v1"
OPENAI_MODEL = "gpt-5.4"  # 你的中转服务支持的模型

# ==================== 拉取新闻 ====================
def fetch_news(hours=12):
    """拉取最近N小时的新闻"""
    pro = ts.pro_api(TUSHARE_TOKEN)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    all_news = []
    sources = ['wallstreetcn', 'cls']
    
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
                            'title': title,
                            'time': row['datetime']
                        })
        except Exception as e:
            print(f'拉取 {src} 失败: {e}')
    
    # 去重
    seen = set()
    deduped = []
    for n in all_news:
        if n['title'] not in seen:
            seen.add(n['title'])
            deduped.append(n)
    
    return deduped

# ==================== LLM调用 ====================
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
    
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    result = resp.json()
    
    # 调试：打印返回结果
    if "choices" not in result:
        print(f"❌ API返回错误: {result}")
        return None
    
    return result["choices"][0]["message"]["content"]

# ==================== 主题发现 ====================
def discover_themes(news_list, top_n=5):
    """从新闻中发现主题"""
    if len(news_list) < 10:
        return []
    
    # 只取前200条标题
    titles = [n["title"] for n in news_list[:200]]
    
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
    
    print("🔄 正在调用LLM分析...")
    response = call_llm(prompt)
    
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
        print(f"❌ 解析失败: {e}")
        print(f"原始响应:\n{response}")
        return []

# ==================== 主函数 ====================
def main():
    print("📰 拉取最近12小时的新闻...")
    news = fetch_news(hours=12)
    print(f"✅ 拉取到 {len(news)} 条新闻（去重后）\n")
    
    print("🔍 开始发现新兴主题...\n")
    themes = discover_themes(news, top_n=5)
    
    if not themes:
        print("❌ 未发现主题")
        return
    
    print(f"\n{'='*60}")
    print(f"🆕 今日新兴主题 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print(f"{'='*60}\n")
    
    for i, theme in enumerate(themes, 1):
        print(f"{i}. {theme['theme']} ({theme['count']}条)")
        print(f"   关键词: {', '.join(theme['keywords'])}")
        print(f"   代表性标题:")
        for ex in theme['examples']:
            print(f"   - {ex}")
        print()

if __name__ == '__main__':
    main()
