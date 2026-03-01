# macro_score — 宏观综合打分 + 策略适配度

## 概述

纯读取模块，汇总所有宏观/微观 JSON，输出宏观环境总分 + 每个策略的环境适配度评分。零 API 调用。

## 文件说明

| 文件 | 用途 |
|------|------|
| `macro_score.py` | 读取各模块 JSON → 宏观打分 + 策略适配度 → macro_score.json |
| `score_config.json` | 权重配置（宏观5维权重 + 各策略子指标权重） |
| `macro_score.json` | 计算产物 |

## 打分维度

### 宏观总分（5维加权）

| 维度 | 权重 | 数据来源 |
|------|------|----------|
| 流动性 | 25% | macro/liquidity/liquidity.json |
| 经济基本面 | 25% | macro/fundamentals/fundamentals.json |
| 利率汇率 | 15% | macro/rates/rates.json |
| 期权情绪 | 20% | micro_flow/option_sentiment/option_sentiment.json |
| 拥挤度 | 15% | micro_flow/crowding/crowding.json |

### 策略适配度

为每个策略（quant_stock/momentum_stock/commodity_cta/cb_env/arbitrage）基于宏观环境 + 策略专属指标计算适配度评分。

## 数据流

```
各模块 JSON（liquidity/fundamentals/rates/option/crowding/env_fit各子模块）
  ↓
macro_score.py（加权打分）
  ↓
macro_score.json → 前端展示
```

## 运行

```bash
python3 macro_score.py
```
