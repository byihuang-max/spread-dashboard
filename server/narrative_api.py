#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
叙事监控数据API
"""
from flask import jsonify
import json
from pathlib import Path
from datetime import datetime

def get_latest_narrative():
    """获取最新的叙事监控数据"""
    cache_dir = Path(__file__).parent.parent / "daily_report" / "meme交易" / "cache"
    
    # 找到最新的narrative文件
    narrative_files = sorted(cache_dir.glob("narrative_*.json"))
    if not narrative_files:
        return jsonify({"error": "No data available"}), 404
    
    latest_file = narrative_files[-1]
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 提取时间戳
    filename = latest_file.stem  # narrative_20260316_2315
    timestamp = filename.split('_')[1] + ' ' + filename.split('_')[2]
    timestamp = datetime.strptime(timestamp, '%Y%m%d %H%M').strftime('%Y-%m-%d %H:%M')
    
    # 格式化数据
    result = {
        "timestamp": timestamp,
        "news_count": data.get("news_count", 0),
        "fixed_analysis": data.get("fixed_analysis", {}),
        "dynamic_themes": data.get("dynamic_themes", [])
    }
    
    return jsonify(result)

def register_narrative_routes(app):
    """注册叙事监控路由"""
    @app.route('/api/narrative_latest')
    def narrative_latest():
        return get_latest_narrative()
