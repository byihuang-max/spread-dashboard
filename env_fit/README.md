# env_fit — 策略环境适配度

## 概述

评估各策略类型当前市场环境的友好程度，每个子模块输出 0-100 环境评分。`env_fit_signals.py` 汇总所有子模块信号。

## 子模块

| 目录 | 策略 | 核心指标 |
|------|------|----------|
| `quant_stock/` | 宽基量化股票 | 因子表现、基差成本、波动率 |
| `momentum_stock/` | 强势股 | 赚钱效应、连板高度、北向流入 |
| `commodity_cta/` | 商品CTA | 趋势品种数、CTA环境、宏观比价 |
| `cb_env/` | 转债指增 | 活跃度、估值水位、DELTA股性、债底 |
| `arbitrage/` | 套利 | 股指基差、商品比价、期权波动率 |

## 文件说明

| 文件 | 用途 |
|------|------|
| `env_fit_signals.py` | 汇总所有子模块 JSON → env_fit_signals.json（供概览页读取） |

## 数据流

```
各子模块独立运行 → 各自输出 JSON
  ↓
env_fit_signals.py（读取所有子模块JSON，生成一句话信号摘要）
  ↓
env_fit_signals.json → overview_calc.py
```
