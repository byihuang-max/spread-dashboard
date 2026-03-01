# chain_prosperity — 中观产业链景气度

## 概述

跟踪4条核心产业链（科技芯片/创新药/周期/消费）的景气度：ETF价格动量、ETF份额变化、商品期货走势。

## 文件说明

| 文件 | 用途 |
|------|------|
| `chain_data.py` | 拉取行业ETF日线 + 份额 + 商品期货数据 → cache/ |
| `chain_calc.py` | 计算各链景气度（涨跌幅/归一化/份额变化） → chain_prosperity.json |
| `chain_prosperity.html` | 产业链景气面板 HTML（4个Tab） |
| `chain_prosperity.json` | 计算产物 |

## 4条产业链

| 链 | 代表ETF | 辅助数据 |
|----|---------|----------|
| 科技芯片 | 芯片ETF/消费电子ETF/科创50ETF | — |
| 创新药 | 创新药ETF/医药ETF | — |
| 周期 | 基建ETF/房地产ETF | 铜/铝/铁矿/煤炭/螺纹等期货 |
| 消费 | 白酒ETF/消费ETF | 生猪/大豆/棕榈油期货 |

## 数据流

```
chain_data.py（ETF日线+份额 + 商品期货）
  ↓
cache/etf_price.csv, cache/etf_share.csv, cache/futures.csv
  ↓
chain_calc.py（归一化 + 涨跌幅 + 份额变化趋势）
  ↓
chain_prosperity.json → overview_calc.py
```

## 数据源

- Tushare: fund_daily（ETF日线）、fund_share（ETF份额）、fut_daily（商品期货）
- iFind: 行业高频数据补充

## 运行

```bash
python3 chain_data.py
python3 chain_calc.py
```
