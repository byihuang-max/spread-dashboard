# patient_capital — 耐心资本持筹

## 概述

通过宽基ETF 15分钟K线大单分析，追踪机构"耐心资本"的建仓/减仓行为，推算滚动持仓成本。

## 文件说明

| 文件 | 用途 |
|------|------|
| `patient_data.py` | 按月批量拉取ETF 15min K线 → raw_15min/ |
| `patient_calc.py` | 基线分离 → 买卖判定 → 滚动成本 → patient_capital.json + CSV |
| `patient_capital.html` | 耐心资本面板 HTML |
| `patient_capital.json` | 计算产物 |

## 跟踪标的

沪深300/上证50/创业板指/科创50/创业板50/中证1000/中证500/中证A500，每个指数覆盖多只ETF。

## 核心算法

1. **基线分离**: 20日滚动中位成交量作为基线
2. **异常判定**: 超过基线1.5倍视为大单
3. **买卖方向**: 结合K线涨跌判定
4. **滚动成本**: 按大单成交额加权平均价

## 数据流

```
patient_data.py（ETF 15min K线，按月批量拉取）
  ↓
raw_15min/（按日期缓存JSON）
  ↓
patient_calc.py（基线分离 → 大单识别 → 成本计算）
  ↓
patient_capital.json + patient_capital.csv → overview_calc.py
```

## 数据源

- Tushare: stk_mins（ETF 15分钟K线）、index_daily（指数日线用于折算）

## 运行

```bash
python3 patient_data.py
python3 patient_calc.py
```
