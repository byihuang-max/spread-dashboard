#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态主题发现 - 从未匹配新闻中提取新兴热点
使用 OpenAI API 或 Claude API
"""
import json
import requests
from datetime import datetime

# ==================== 配置 ====================
# 使用 aicanapi 中转服务
LLM_PROVIDER = "openai"  # 使用OpenAI兼容接口

# aicanapi 配置（OpenAI兼容）
OPENAI_API_KEY = "sk-nPKqBvGbB3I0aewJoZQBLLUDtU6N8pl7JlXn5qxMwt2bbWm0"
OPENAI_BASE_URL = "https://aicanapi.com/v1"  # 中转服务地址
OPENAI_MODEL = "gpt-4o-mini"  # 便宜快速，适合这个任务

# ==================== LLM调用 ====================
def call_openai(prompt):
    """调用OpenAI API（通过aicanapi中转）"""
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
        "temperature": 0.3,  # 低温度，更稳定
        "max_tokens": 1000
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    result = resp.json()
    return result["choices"][0]["message"]["content"]


def call_claude(prompt):
    """调用Claude API"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1000,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    result = resp.json()
    return result["content"][0]["text"]


def discover_themes(unmatched_news, top_n=5):
    """
    从未匹配的新闻中发现新兴主题
    
    Args:
        unmatched_news: 未匹配的新闻列表 [{"title": "...", "time": "..."}, ...]
        top_n: 返回前N个主题
    
    Returns:
        [
            {
                "theme": "主题名",
                "count": 估计相关新闻数,
                "keywords": ["关键词1", "关键词2"],
                "examples": ["标题1", "标题2", "标题3"]
            },
            ...
        ]
    """
    if len(unmatched_news) < 10:
        return []  # 新闻太少，不值得分析
    
    # 只取标题（节省token）
    titles = [n["title"] for n in unmatched_news[:200]]  # 最多200条，避免超token
    
    # 构造prompt
    prompt = f"""
以下是今天的{len(titles)}条财经新闻标题。请分析这些新闻，找出最热门的{top_n}个主题。

新闻标题：
{chr(10).join(f"{i+1}. {t}" for i, t in enumerate(titles))}

请以JSON格式返回，格式如下：
[
  {{
    "theme": "主题名称（简短精准，如'日本央行加息预期'）",
    "count": 相关新闻条数（估算）,
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "examples": ["代表性标题1", "代表性标题2", "代表性标题3"]
  }},
  ...
]

要求：
1. 主题名要简短（5-10个字）
2. 只返回真正有热度的主题（至少5条相关新闻）
3. 主题之间不要重叠
4. 直接返回JSON，不要其他文字
"""
    
    # 调用LLM
    if LLM_PROVIDER == "openai":
        response = call_openai(prompt)
    else:
        response = call_claude(prompt)
    
    # 解析JSON
    try:
        # 去掉可能的markdown代码块标记
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        
        themes = json.loads(response)
        return themes
    except Exception as e:
        print(f"❌ 解析LLM响应失败: {e}")
        print(f"原始响应: {response}")
        return []


# ==================== 主函数 ====================
def main():
    """测试：从最近的narrative文件中提取未匹配新闻"""
    from pathlib import Path
    
    # 读取最新的narrative文件
    cache_dir = Path(__file__).parent / "cache"
    latest_file = sorted(cache_dir.glob("narrative_*.json"))[-1]
    
    print(f"📂 读取文件: {latest_file.name}")
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取所有新闻
    all_news = data.get("news", [])
    print(f"📰 总新闻数: {len(all_news)}")
    
    # 获取已匹配的新闻（从analysis中统计）
    matched_count = sum(
        v.get("matched_count", 0) 
        for v in data["analysis"].values()
    )
    print(f"✅ 已匹配: {matched_count} 条")
    print(f"❓ 未匹配: {len(all_news) - matched_count} 条")
    
    # 简化：假设未匹配的新闻就是all_news（实际应该过滤掉已匹配的）
    # 这里为了演示，直接用all_news
    unmatched = all_news[:200]  # 取前200条
    
    print(f"\n🔍 开始发现新兴主题...")
    themes = discover_themes(unmatched, top_n=5)
    
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
