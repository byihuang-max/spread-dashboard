# rates — 全球利率与汇率

## 概述

跟踪中美10Y国债利率、中美利差、人民币汇率（在岸+离岸），判断外部环境压力。

## 文件说明

| 文件 | 用途 |
|------|------|
| `rates_data.py` | 拉取中国10Y(yc_cb)、美债(us_tycr)、汇率(iFind实时) → cache/ |
| `rates_calc.py` | 计算中美利差、汇率趋势 → rates.json |
| `rates.html` | 利率汇率面板 HTML |
| `rates.json` | 计算产物 |

## 数据流

```
rates_data.py
  ↓
cache/cn10y.csv, cache/us_treasury.csv, cache/fx_realtime.csv
  ↓
rates_calc.py（利差计算 + 汇率趋势）
  ↓
rates.json → macro_score.py + alerts_calc.py + overview_calc.py
```

## 数据源

- Tushare: yc_cb（中国国债收益率曲线）、us_tycr（美国国债收益率）
- iFind: USDCNY/USDCNH 实时汇率

## 运行

```bash
python3 rates_data.py
python3 rates_calc.py
```
