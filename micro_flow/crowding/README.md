# crowding — 拥挤度监控

## 概述

三路资金流向（北向/ETF/两融）+ 申万一级行业三维拥挤度评估（价格动量/资金验证/成交偏离）。

## 文件说明

| 文件 | 用途 |
|------|------|
| `crowding_data.py` | 拉取北向资金、ETF份额、两融余额、申万行业日线、行业ETF份额 → cache/ |
| `crowding_calc.py` | 三路资金合成 + 行业热力图 + 拥挤度信号 → crowding.json |
| `crowding.html` | 拥挤度面板 HTML |
| `crowding.json` | 计算产物 |

## 三维拥挤度（每个申万一级行业）

| 维度 | 计算 |
|------|------|
| 价格动量 | 5日累计涨跌幅 |
| 资金验证 | 行业ETF份额5日变化 |
| 拥挤度 | 成交额/MA20偏离度 |

## 数据流

```
crowding_data.py
  ↓
cache/northbound.csv, cache/etf_flow.csv, cache/margin.csv,
cache/sw_daily.csv, cache/industry_etf.csv
  ↓
crowding_calc.py（三路资金 + 行业三维评估）
  ↓
crowding.json → macro_score.py + alerts_calc.py + overview_calc.py
```

## 数据源

- Tushare: moneyflow_hsgt（北向）、fund_share（ETF份额）、margin_detail（两融）、sw_daily（申万行业）

## 运行

```bash
python3 crowding_data.py
python3 crowding_calc.py
```
