# fund_nav — 基金净值跟踪

## 概述

拉取各策略代表性私募产品净值，对比基准指数，计算超额收益，为每个策略 tab 提供净值曲线。

## 文件说明

| 文件 | 用途 |
|------|------|
| `fund_nav_data.py` | 拉取产品净值 + 基准指数 → 各策略 JSON |
| `fund_nav.html` | 净值面板 HTML |
| `fund_nav.json` | 汇总产物 |
| `fund_nav_*.json` | 各策略单独 JSON（quant-stock/momentum-stock/cta/convertible/arbitrage） |

## 跟踪产品

| Tab | 产品 | 基准 |
|-----|------|------|
| quant-stock | 中证1000指增代表产品 | 中证1000 |
| momentum-stock | 强势股代表产品 | 上证指数 |
| cta | CTA代表产品 | 南华商品指数 |
| convertible | 转债代表产品 | 中证转债指数 |
| arbitrage | 套利代表产品 | 上证指数 |

## 数据流

```
fund_nav_data.py（火富牛API拉净值 + 基准指数）
  ↓
cache/（原始净值数据）
  ↓
fund_nav_*.json（各策略净值+基准+超额）
```

## 数据源

- 火富牛 (fof99): FundCompanyPrice / FundPrice（私募净值）、IndexPrice（基准指数）

## 依赖

- `fof99`（安装在 /tmp/fof99_pkg）

## 运行

```bash
python3 fund_nav_data.py
```
