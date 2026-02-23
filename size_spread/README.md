# size_spread — 风格轧差分析模块

## 概述

用两个指数（或指数篮子）的涨跌幅之差来衡量某种风格的相对强弱，归1复利做成策略净值。覆盖6种风格维度，输出 Excel + HTML 看板 + JSON。

## 文件说明

| 文件 | 用途 |
|------|------|
| `style_spread.py` | 主脚本：拉取数据、计算轧差、输出 Excel + HTML + JSON |
| `style_spread.xlsx` | 数据产出（4个 sheet） |
| `风格轧差看板.html` | 独立 HTML 看板（6 tab，Chart.js 图表） |
| `_archive/` | 旧版文件归档 |
| `_archive/size_spread.py` | 旧版：iFind 版大小盘轧差脚本（已弃用） |
| `_archive/gen_html.py` | 旧版：从 Excel 生成 HTML 的脚本（已弃用） |

## 数据流

```
Tushare API（index_daily 宽基指数 + sw_daily 申万行业指数）
  ↓ style_spread.py
style_spread.xlsx（4个sheet）
风格轧差看板.html（独立看板）
~/Desktop/gamt-dashboard/data/style_spread.json（供主看板使用）
  ↓ inject_style_spread.py（根目录）
index.html（风格轧差模块）
```

## style_spread.py — 主脚本

回溯约400天数据，一次性拉取所有需要的指数和行业数据，计算4类轧差。

### Sheet1：风格轧差（3对）

| 多头 | 空头 | 含义 |
|------|------|------|
| 中证红利(000922.CSI) | 科创50(000688.SH) | 正值 = 红利跑赢科创 |
| 国证微盘股(399303.SZ) | 中证全指(000985.CSI) | 正值 = 微盘跑赢全A |
| 中证2000(932000.CSI) | 沪深300(000300.SH) | 正值 = 小盘跑赢大盘 |

计算方式：每日轧差 = 多头涨跌幅 - 空头涨跌幅，净值 = 归1复利累乘 ∏(1 + spread/100)

### Sheet2：双创等权

创业板指(399006.SZ) + 科创50(000688.SH) 等权平均涨跌幅，归1复利净值。

### Sheet3：经济敏感轧差

- 周期篮子：有色金属(801050.SI) + 煤炭(801950.SI) + 钢铁(801040.SI) 等权
- 防御篮子：食品饮料(801120.SI) + 医药生物(801150.SI) 等权
- 轧差 = 周期 - 防御，正值 = 周期跑赢

### Sheet4：动量轧差（拥挤-反身性）

- 样本：申万31个一级行业指数
- 每天滚动计算过去20个交易日的：
  - 指标A：平均成交额 → 从高到低排名
  - 指标B：波动率(pct_chg标准差) → 从高到低排名
  - 复合得分 = 成交额排名 + 波动率排名
- Top6（高动量）vs Bot6（低动量）等权轧差
- 成分每天动态更新

### 输出

- `style_spread.xlsx`：4个 sheet 的完整数据
- `风格轧差看板.html`：独立 HTML 看板，含经济敏感轧差、拥挤度轧差、风格轧差净值、双创等权净值 4个图表区域
- `data/style_spread.json`：JSON 格式数据，供主看板注入使用

运行：`python3 style_spread.py`

## _archive/ — 旧版归档

| 文件 | 说明 |
|------|------|
| `size_spread.py` | 最早版本，用 iFind API 拉中证2000和沪深300做大小盘轧差，输出 CSV + HTML |
| `gen_html.py` | 从 style_spread.xlsx 读取数据生成3个独立 HTML 看板（红利-科创50、微盘-全指、双创等权） |

这两个文件已被 `style_spread.py` 完全替代。

## 注入到主看板

风格轧差模块通过根目录的 `inject_style_spread.py` 注入到 `index.html`：
- 从 `风格轧差看板.html` 提取 DATA 数组
- 原生嵌入 HTML/CSS/JS（替代了早期的 iframe 方式）
- 包含：6个子tab切换、统计卡片、净值曲线+MA20、每日轧差柱状图、特殊面板（双创/经济敏感/动量）、底部数据源注释

```bash
cd ~/Desktop/gamt-dashboard
python3 inject_style_spread.py
```

## 完整更新流程

```bash
cd ~/Desktop/gamt-dashboard/size_spread
python3 style_spread.py              # 1. 拉取数据 + 生成 Excel/HTML/JSON
cd ~/Desktop/gamt-dashboard
python3 inject_style_spread.py       # 2. 注入到主看板
```
