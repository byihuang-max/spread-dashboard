# fundamentals — 经济基本面

## 概述

跟踪 PMI/CPI/PPI 宏观指标，判定美林时钟阶段，输出经济动能信号。

## 文件说明

| 文件 | 用途 |
|------|------|
| `fundamentals_data.py` | 增量拉取 PMI/CPI/PPI 月度数据 → cache/ |
| `fundamentals_calc.py` | 计算美林时钟阶段 + 生成信号 → fundamentals.json |
| `fundamentals.html` | 基本面面板 HTML |
| `fundamentals.json` | 计算产物 |

## 数据流

```
fundamentals_data.py（按月增量拉取）
  ↓
cache/pmi.csv, cache/cpi.csv, cache/ppi.csv
  ↓
fundamentals_calc.py（PMI趋势 + CPI/PPI交叉 → 美林时钟）
  ↓
fundamentals.json → macro_score.py + overview_calc.py
```

## 数据源

- Tushare: cn_pmi（制造业PMI）、cn_cpi（CPI）、cn_ppi（PPI）

## 运行

```bash
python3 fundamentals_data.py
python3 fundamentals_calc.py
```
