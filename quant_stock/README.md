# quant_stock — 宽基量化股票指标模块

## 概述

拉取 A 股宽基量化相关的四类指标数据（近一年），生成图表注入到主看板的"宽基量化股票"tab，用于观察市场流动性、资金结构、对冲成本和因子表现。

## 文件说明

| 文件 | 用途 |
|------|------|
| `quant_stock_data.py` | 数据拉取脚本，输出 quant_stock_data.json |
| `inject_quant_stock.py` | 注入脚本，将数据生成 HTML/JS 注入到 index.html |

## 数据流

```
Tushare API（index_daily + fut_daily）
  ↓ quant_stock_data.py
quant_stock_data.json
  ↓ inject_quant_stock.py
index.html（宽基量化股票 tab）
```

## quant_stock_data.py — 数据拉取

回溯约400天，自动限流（每次 API 调用间隔 ≥1.5s）。

### 四个指标

| 指标 | 数据源 | 说明 |
|------|--------|------|
| 全市场成交额 | 中证全指(000985.CSI) index_daily.amount | 日成交额（亿元），反映整体流动性 |
| 宽基成交额占比 | 300/500/1000/2000/科创50+创业板指 各自 amount / 全A amount | 各宽基占全A成交额比例(%)，观察资金主战场迁移 |
| 股指期货年化基差 | IF/IC/IM.CFX fut_daily.close vs 现货 index_daily.close | (期货-现货)/现货 × 12 × 100，负值=贴水(对冲成本) |
| 因子超额收益 | 价值(399371.SZ)、成长(399370.SZ)、红利(000922.CSI)、小盘(932000.CSI) vs 基准(000985.CSI) | 各因子指数相对全A的日度超额收益累计净值 |

运行：`python3 quant_stock_data.py`

## inject_quant_stock.py — 注入脚本

这是整个看板的"骨架注入脚本"，除了注入宽基量化数据图表外，还负责：
- 创建策略环境适配度模块的完整 HTML 结构（含策略 tab 导航）
- 定义所有策略 tab 的占位页面（强势股、CTA、转债、套利）
- 注入 Chart.js CDN 引用
- 注入策略 tab 切换的 CSS 和 JS 逻辑
- 注入4个 Chart.js 图表（成交额、占比、基差、因子）

生成的4个图表：
1. 全市场成交额折线图（含 MA20）
2. 宽基成交额占比多线图（5条线）
3. IF/IC/IM 年化基差折线图（含零线）
4. 因子超额收益净值折线图（含基准线1.0）

注入方式：用正则替换 `<!-- ========== 策略环境适配度 ========== -->` 到 `<!-- ========== 占位模块 ========== -->` 之间的内容。

运行：`python3 inject_quant_stock.py`（注意：此脚本的 html_path 指向 `quant_stock/index.html`，实际使用时需确认路径）

## 完整更新流程

```bash
cd ~/Desktop/gamt-dashboard/quant_stock
python3 quant_stock_data.py      # 1. 拉取数据
python3 inject_quant_stock.py    # 2. 注入到主看板
```

## 注意事项

- inject_quant_stock.py 是最早写的注入脚本，后续的强势股、CTA、转债模块都是在它创建的 tab 框架上追加注入的
- 如果需要重建整个策略环境模块，应先跑这个脚本建骨架，再依次跑其他模块的注入脚本
