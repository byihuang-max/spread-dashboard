# alerts — 红灯预警

## 概述

5维度综合风险评分系统，汇总全看板关键风险信号，输出 0-100 危险度评分。

## 文件说明

| 文件 | 用途 |
|------|------|
| `alerts_data.py` | 数据拉取：估值(index_dailybasic)、涨跌停(limit_list_d)、成交额(daily)，复用其他模块 cache |
| `alerts_calc.py` | 5维风险计算 + 综合评分 → alerts.json |
| `alerts.html` | 预警面板 HTML（前端渲染） |
| `alerts.json` | 计算产物：各维度评分 + 综合风险等级 |

## 5维风险

| 维度 | 数据来源 | 指标 |
|------|----------|------|
| 💧 流动性 | DR007/Shibor（复用 macro/liquidity/cache） | DR007绝对值 + R-D价差 |
| 📊 估值 | index_dailybasic（自有cache） | 上证/沪深300/创业板 PE分位 |
| 🎭 情绪 | 涨跌停统计 + 成交额（自有cache） | 跌停数 + 成交额萎缩度 |
| 🌍 外部冲击 | 复用 macro/rates + micro_flow/option_sentiment | 中美利差 + PCR异常 |
| 📉 微观恶化 | 复用 micro_flow/crowding | 行业拥挤度 + 两融变化 |

## 数据流

```
alerts_data.py（拉取自有数据 + 复用其他模块cache）
  ↓
cache/（估值CSV + 涨跌停CSV + 成交额CSV）
  ↓
alerts_calc.py（5维评分 → 加权合成）
  ↓
alerts.json → overview_calc.py 读取 → 概览页红灯
```

## 数据源

- Tushare: index_dailybasic, limit_list_d, daily
- 复用: macro/liquidity, macro/rates, micro_flow/crowding, micro_flow/option_sentiment

## 运行

```bash
python3 alerts_data.py
python3 alerts_calc.py
```
