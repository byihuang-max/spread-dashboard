# cb_env — 转债指增策略环境模块

## 概述

评估可转债市场对"转债指增"策略的友好程度，输出 0-100 综合评分（转债友好度），并生成图表注入到主看板。

## 文件说明

| 文件 | 用途 |
|------|------|
| `cb_data.py` | 数据拉取脚本（CSV增量模式） |
| `cb_calc.py` | 计算模块，读取 cb_data.json 输出 cb_env.json |
| `inject_cb_env.py` | 注入脚本，将计算结果生成 HTML/JS 注入到 index.html 的转债 tab |

## 数据流

```
Tushare API
  ↓ cb_data.py（增量拉取，写入4个CSV）
cb_daily.csv / stk_daily.csv / idx_daily.csv / cb_basic.csv
  ↓ cb_data.py（从CSV重建）
cb_data.json
  ↓ cb_calc.py（计算4个维度指标）
cb_env.json
  ↓ inject_cb_env.py（生成HTML/JS）
index.html（转债 tab）
```

## cb_data.py — 数据拉取

- 数据源：Tushare 私有 API（cb_daily 转债日行情、daily 正股行情、index_daily 指数行情、cb_basic 转债基本信息）
- 增量策略：4个CSV文件作为持久化存储，每次只拉CSV中没有的新日期
- 首次运行时自动从已有 cb_data.json 迁移到CSV
- 回溯窗口：90个交易日
- 指数：中证1000(000852.SH)、中证2000(932000.CSI)
- 输出：cb_data.json（供 cb_calc.py 使用）
- 编码：CSV 用 gb18030

运行：`python3 cb_data.py`

## cb_calc.py — 计算模块

读取 cb_data.json，计算4个维度指标，输出 cb_env.json。

### 四个维度

| 模块 | 指标 | 计算方式 | 权重 |
|------|------|----------|------|
| Mod1 市场活跃度 | 转债成交额变化与中证1000/2000涨跌幅的20日滚动相关系数 | rolling_corr(cb_amt_pct, idx_pct, 20) | 25% |
| Mod2 估值水位 | 成交量前50%转债的平均价格历史分位数 + 平均转股溢价率 | percentile_rank + (cb_price - conv_value) / conv_value | 25% |
| Mod3 DELTA股性 | 成交量前50%转债涨跌幅 vs 正股涨跌幅的20日回归斜率中位数 | rolling_beta(cb_rets, stk_rets, 20) 取中位数 | 25% |
| Mod4 债底跟踪 | 全市场转债价格中位数 + 破面值(<100元)占比 | median(prices), count(price<100)/total | 25% |

### 综合评分

```
转债友好度 = 0.25 × 活跃度分 + 0.25 × 估值分 + 0.25 × DELTA分 + 0.25 × 债底分
```

- 活跃度：相关系数 (-1~1) 映射到 0~100
- 估值：(100 - 价格分位) × 0.5 + (100 - 溢价率) × 0.5，越低越好
- DELTA：delta × 100，越高越好
- 债底：100 - 破面值占比，越少越好

运行：`python3 cb_calc.py`

## inject_cb_env.py — 注入脚本

读取 cb_env.json，生成包含以下内容的 HTML/JS：
- 总览卡片：转债友好度、活跃转债数、成交额、DELTA中位数、均价分位、数据日期
- 分项评分卡片：活跃度/估值/DELTA/债底 四维评分
- 4个 Chart.js 图表：成交额&相关性、均价分位&溢价率、DELTA走势、债底走势
- 指标说明面板

注入方式：找到 `<div class="strat-page" id="strat-convertible">` 替换其内容，并在 tab 切换事件中添加 `initCbCharts()` 延迟初始化。

运行：`python3 inject_cb_env.py`

## 完整更新流程

```bash
cd ~/Desktop/gamt-dashboard/cb_env
python3 cb_data.py          # 1. 拉取/更新数据
python3 cb_calc.py          # 2. 计算指标
python3 inject_cb_env.py    # 3. 注入到主看板
```

## 缓存目录

`_cache/` — cb_data.py 的 JSON 缓存（按日期存储原始API响应），用于避免重复拉取。
