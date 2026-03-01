# arbitrage — 套利策略环境

## 概述

监控三类套利机会的市场环境：股指基差、商品跨品种/跨期价差、期权波动率。

## 文件说明

| 文件 | 用途 |
|------|------|
| `fetch_incremental.py` | 统一增量数据拉取（CSV真相源 + JSON cache） |
| `mod1_index_arb.py` | 股指套利：IF/IH/IC/IM 期现基差监控 |
| `mod2_commodity_arb.py` | 商品套利：跨品种比价（螺纹/铁矿、豆油/棕榈油等）+ 跨期价差 |
| `mod3_option_arb.py` | 期权套利：PCR、HV20、成交量/持仓量趋势 |
| `arbitrage.html` | 套利面板 HTML |
| `arb_cache.json` | 增量缓存（供 mod1/2/3 快速读取） |
| `mod[1-3]_*.json` | 各模块计算结果 |
| `_opt_cp_map.json` | 期权Call/Put映射缓存 |

## 数据流

```
fetch_incremental.py（增量拉取）
  ↓ CSV（5类：股指期货/现货/商品/期权/HV）+ arb_cache.json
mod1_index_arb.py → mod1_index_arb.json（股指基差30日序列）
mod2_commodity_arb.py → mod2_commodity_arb.json（4组比价 + 跨期状态）
mod3_option_arb.py → mod3_option_arb.json（PCR + HV20）
```

## 数据源

- Tushare: fut_daily（股指/商品期货）、index_daily（现货指数）、opt_daily（期权日线）、opt_basic（合约信息）
- 复用: commodity_cta/fut_daily.csv（商品连续合约）

## 依赖

无特殊依赖，标准 requests + pandas。

## 运行

```bash
python3 fetch_incremental.py   # 增量拉取
python3 mod1_index_arb.py --incremental
python3 mod2_commodity_arb.py --incremental
python3 mod3_option_arb.py --incremental
```
