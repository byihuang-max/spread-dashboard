#!/usr/bin/env python3
"""
卖权窗口信号 - 时序监控

输出：
- 最近60天的卖权友好度走势
- 当前综合评分 + 环境判断
- 关键指标：IV分位 / IV-RV spread / 市场环境
"""

import json
import os
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'sell_window_signal.json')


def main():
    # 读取现有数据
    regime_path = os.path.join(BASE, 'mod9_composite_score.json')
    if not os.path.exists(regime_path):
        print("⚠️ mod9_composite_score.json 不存在，跳过")
        return
    
    with open(regime_path) as f:
        regime_data = json.load(f)
    
    # 提取当前评分
    regime = regime_data.get('regime', {})
    avg_score = regime.get('avg_composite_score', regime.get('avg_sell_score', 0))
    label = regime.get('label', 'NEUTRAL')
    n_sellable = regime.get('n_sellable', 0)
    
    # 生成时序数据（暂时用模拟数据，等 Tushare 历史数据到位后替换）
    today = datetime.now()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(60, -1, -1)]
    
    # 模拟历史评分（实际应从历史数据计算）
    import random
    random.seed(42)
    scores = [max(30, min(90, avg_score + random.randint(-15, 15))) for _ in dates]
    scores[-1] = avg_score  # 最后一天用真实值
    
    # 判断当前窗口
    if avg_score >= 80:
        window = '系统性窗口'
        color = 'green'
        emoji = '🟢'
    elif avg_score >= 60:
        window = '精选窗口'
        color = 'yellow'
        emoji = '🟡'
    elif avg_score >= 40:
        window = '中性观察'
        color = 'gray'
        emoji = '⚪'
    else:
        window = '不宜开仓'
        color = 'red'
        emoji = '🔴'
    
    result = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'module': 'sell_window_signal',
            'version': 'v1',
        },
        'current': {
            'score': round(avg_score, 1),
            'window': window,
            'color': color,
            'emoji': emoji,
            'n_sellable': n_sellable,
            'label': label,
        },
        'timeseries': {
            'dates': dates,
            'scores': [round(s, 1) for s in scores],
        },
        'components': {
            'iv_percentile': None,  # 待 Tushare IV 数据接入
            'iv_rv_spread': None,
            'market_regime': regime.get('description', ''),
        }
    }
    
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 卖权窗口信号: {window} {emoji} (评分 {avg_score:.1f})")
    print(f"   输出: {OUT}")


if __name__ == '__main__':
    main()
