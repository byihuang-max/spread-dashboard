# option_sentiment — 期权情绪面板

## 概述

基于沪深300/上证50/中证500ETF/中证1000期权数据，计算隐含波动率(IV)、PCR、OI分布，检测异常信号。

## 文件说明

| 文件 | 用途 |
|------|------|
| `option_data.py` | 拉取期权合约信息(opt_basic) + 日线(opt_daily) + 标的价格 → cache/ |
| `option_calc.py` | BS模型反算IV + 期限结构 + PCR + OI分布 + 异常检测 → option_sentiment.json |
| `option_sentiment.html` | 期权情绪面板 HTML |
| `option_sentiment.json` | 计算产物 |

## 核心计算

| 指标 | 方法 |
|------|------|
| 隐含波动率(IV) | Black-Scholes + Brent求根法 |
| IV期限结构 | 按到期月分组 + 20日滚动分位 |
| PCR(OI) | Put持仓量/Call持仓量 |
| 异常检测 | IV突变 + OI激增 |

## 数据流

```
option_data.py（4个标的 × opt_basic + opt_daily + 标的日线）
  ↓
cache/opt_basic.csv, cache/opt_daily_*.csv, cache/*_price.csv
  ↓
option_calc.py（BS反算IV → 期限结构 → PCR → 异常检测）
  ↓
option_sentiment.json → macro_score.py + alerts_calc.py + overview_calc.py
```

## 数据源

- Tushare: opt_basic, opt_daily, index_daily, fund_daily

## 依赖

- `scipy`（norm, brentq 用于 BS 模型求解 IV）

## 运行

```bash
python3 option_data.py
python3 option_calc.py
```
