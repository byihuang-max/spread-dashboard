# momentum_stock — 强势股情绪指标模块

## 概述

基于 A 股涨跌停数据构建合成情绪指数（0-100），追踪市场短线情绪周期（冰点→回暖→加速→分歧→退潮），用于辅助强势股/打板策略的择时判断。

## 文件说明

| 文件 | 用途 |
|------|------|
| `momentum_data.py` | 数据拉取 + 指标计算脚本（CSV增量模式） |
| `inject_momentum.py` | 注入脚本，将情绪数据生成 HTML/JS 注入到 index.html 的强势股 tab |

## 数据流

```
Tushare limit_list_d API（涨停U/跌停D/炸板Z）
  ↓ momentum_data.py（增量拉取，写入CSV）
momentum_raw.csv（每日基础统计）
  ↓ momentum_data.py（计算指标）
momentum_sentiment.csv（完整数据 + 计算指标 + 公式列）
momentum_sentiment.json（供注入脚本使用）
  ↓ inject_momentum.py（生成HTML/JS）
index.html（强势股 tab）
```

## momentum_data.py — 数据拉取 + 计算

### 数据源

- Tushare `limit_list_d` 接口，分别拉取 U(涨停)、D(跌停)、Z(炸板) 三类
- 回溯窗口：120个交易日
- 每日数据缓存到 `_cache/{date}.json`

### 基础数据（每日）

| 字段 | 说明 |
|------|------|
| up_count | 涨停家数 |
| down_count | 跌停家数 |
| zha_count | 炸板家数（曾触及涨停但未封住） |
| max_height | 最高连板天数（limit_times 最大值） |
| lianban_count | 连板股数量（limit_times > 1） |
| shouban_count | 首板股数量（limit_times = 1） |
| seal_zero_count | 一字/秒板数量（open_times = 0） |

### 计算指标

| 指标 | 公式 | 说明 |
|------|------|------|
| promotion_rate | 今日涨停 ∩ 昨日涨停 / 昨日涨停总数 × 100 | 连板晋级率 |
| rate_1to2 | 昨日首板 ∩ 今日连板(limit_times≥2) / 昨日首板数 × 100 | 1进2晋级率 |
| zha_rate | zha_count / (up_count + zha_count) × 100 | 炸板率（越低越好） |
| ud_ratio | up_count / max(down_count, 1) | 涨跌停比 |
| seal_quality | (big_cap_up + 2*mega_cap_up) / up_count × 100 | 封板质量（大市值涨停加权占比，反映资金级别） |

### 合成情绪指数 v2（2026-03-01 优化）

标准化方式：120日滚动分位数排名（percentile rank, 0-100），替代旧版60日min-max。
分位数有绝对锚点，冰点期里的"相对高"不会被误判为加速。

加权合成 + 交互修正：

```
base = 0.20 × h_rank(空间高度)
     + 0.25 × p_rank(晋级率)
     + 0.20 × z_rank(1-炸板率)
     + 0.10 × u_rank(涨跌停比)
     + 0.25 × s_rank(封板质量)

交互修正1：高度×质量
  h>70 且 s<30（连板高但全小票）→ base × 0.85

交互修正2：赚亏对冲
  p>60 且 z<30（晋级率高但炸板也高=分歧）→ base × 0.90

sentiment = clip(base, 0, 100)
```

v2 vs v1 变化：
- 封板质量：一字板占比 → 大市值涨停占比（资金级别才是质量）
- 权重：封板质量从0.15提升到0.25（大资金参与是核心信号），涨跌停比从0.15降到0.10（易极端）
- 标准化：60日min-max → 120日分位数（有绝对锚点）
- 涨跌停比：clip到20（防跌停=0极端值）
- 新增交互修正（非线性，捕捉矛盾状态）

### 情绪周期标签

基于情绪指数的绝对水平和变化率自动判定：

| 标签 | 条件 |
|------|------|
| 冰点 | sentiment < 20 |
| 回暖 | sentiment < 35 且从低位上升 |
| 加速 | sentiment > 60 且继续上升 |
| 分歧 | sentiment > 50 且开始下降 |
| 退潮 | sentiment < 40 且从 >45 连续下降 |
| 震荡 | 其他情况 |

### CSV 输出

- `momentum_raw.csv`：基础数据（8列）
- `momentum_sentiment.csv`：完整数据（基础 + 计算指标 + 标准化因子 + 情绪指数 + 周期标签 + 公式列）

运行：`python3 momentum_data.py`

## inject_momentum.py — 注入脚本

读取 momentum_sentiment.json，展示最近60个交易日数据，生成：
- 总览卡片：合成情绪指数、情绪周期、最高连板、涨停/跌停/炸板、晋级率、炸板率/封板质量
- 合成情绪指数折线图（含 MA5、MA20）
- 子因子分解折线图（5个标准化因子）
- 涨停/跌停/炸板柱状图
- 连板高度柱状图 + 晋级率折线（双Y轴）
- 情绪周期时间线（彩色标签）
- 指标说明面板

注入方式：找到 `<div class="strat-page" id="strat-momentum-stock">` 到 `<div class="strat-page" id="strat-cta">` 之间替换。

运行：`python3 inject_momentum.py`

## 完整更新流程

```bash
cd ~/Desktop/gamt-dashboard/momentum_stock
python3 momentum_data.py      # 1. 拉取数据 + 计算指标
python3 inject_momentum.py    # 2. 注入到主看板
```

## 缓存目录

`_cache/` — 按日期存储 limit_list_d API 响应（{date}.json，含 U/D/Z 三类数据），避免重复拉取。
