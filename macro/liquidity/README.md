# liquidity — 境内流动性

## 概述

跟踪境内资金面核心指标：Shibor期限结构、DR007、逆回购、M1/M2，判断流动性松紧。

## 文件说明

| 文件 | 用途 |
|------|------|
| `liquidity_data.py` | 增量拉取 Shibor/DR007/货币供应 → cache/ |
| `liquidity_calc.py` | 计算期限结构、趋势信号 → liquidity.json |
| `liquidity.html` | 流动性面板 HTML |
| `liquidity.json` | 计算产物 |

## 数据流

```
liquidity_data.py（增量追加CSV）
  ↓
cache/shibor.csv, cache/dr007.csv, cache/money_supply.csv
  ↓
liquidity_calc.py（期限结构 + O/N趋势 + M1-M2剪刀差）
  ↓
liquidity.json → macro_score.py + alerts_calc.py + overview_calc.py
```

## 数据源

- Tushare: shibor（Shibor各期限）、repo_daily（DR007/R007）、cn_m（M1/M2货币供应）

## 运行

```bash
python3 liquidity_data.py
python3 liquidity_calc.py
```
