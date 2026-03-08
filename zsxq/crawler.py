#!/usr/bin/env python3
"""
知识星球爬虫系统
功能：抓取订阅的知识星球内容，保存为结构化数据
"""
import os
import json
import requests
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / 'config.json'
DATA_DIR = SCRIPT_DIR / 'data' / 'raw'
CACHE_DIR = SCRIPT_DIR / 'cache'

# 知识星球API端点
API_BASE = 'https://api.zsxq.com/v2'


def load_config():
    """加载配置"""
    if not CONFIG_FILE.exists():
        print("❌ 配置文件不存在，请先配置 config.json")
        return None
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if not config.get('cookie'):
        print("❌ 请先在 config.json 中配置 cookie")
        return None
    
    return config


def get_headers(config):
    """构建请求头"""
    return {
        'Cookie': config['cookie'],
        'User-Agent': config['user_agent'],
        'Accept': 'application/json',
        'Origin': 'https://wx.zsxq.com',
        'Referer': 'https://wx.zsxq.com/'
    }


def fetch_planet_topics(planet_id, config, limit=50):
    """获取星球主题列表"""
    url = f"{API_BASE}/groups/{planet_id}/topics"
    params = {'count': limit}
    headers = get_headers(config)
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ 获取星球 {planet_id} 失败: {e}")
        return None


def save_topics(planet_name, topics_data):
    """保存主题数据"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = DATA_DIR / f"{planet_name}_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(topics_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 保存到: {filename}")


def main():
    print("=" * 50)
    print("知识星球爬虫系统")
    print("=" * 50)
    
    config = load_config()
    if not config:
        return
    
    for planet in config['planets']:
        if not planet.get('enabled', True):
            continue
        
        planet_id = planet['id']
        planet_name = planet['name']
        
        print(f"\n抓取星球: {planet_name} ({planet_id})")
        
        data = fetch_planet_topics(planet_id, config, config.get('fetch_limit', 50))
        if data:
            save_topics(planet_name, data)
    
    print("\n✓ 抓取完成")


if __name__ == '__main__':
    main()
