# commodity_cta — 商品CTA策略环境模块

## 概述

评估全市场期货品种对CTA（趋势跟踪）策略的友好程度，包含三个子模块：CTA整体环境、品种趋势扫描、宏观比价信号。输出 0-100 CTA友好度综合评分。

## 文件说明

| 文件 | 用途 |
|------|------|
| `commodity_data.py` | 数据层：从 Tushare 拉取全市场期货连续合约日线数据（CSV增量模式） |
| `mod1_cta_env.py` | 模块一：CTA整体环境指标（波动率、趋势占比、成交量比 → CTA友好度） |
| `mod2_trend_scan.py` | 模块二：品种趋势扫描（每品种趋势评分、信号计数） |
| `mod3_macro_ratio.py` | 模块三：宏观比价信号（铜金比、油金比、工业品/农产品比） |
| `commodity_cta_main.py` | 集成脚本：依次运行三个模块，合并输出 commodity_cta.json |
| `inject_commodity_cta.py` | 注入脚本（新版）：读取 commodity_cta.json 注入到 index.html 的 CTA tab |
| `inject_commodity.py` | 注入脚本（旧版）：读取旧格式 commodity_cta.json 注入，含时序图表 |

## 数据流

```
Tushare fut_daily API
  ↓ commodity_data.py（增量拉取，写入CSV）
fut_daily.csv（全市场期货连续合约日线）
  ↓ mod1 / mod2 / mod3（各自从CSV读取计算）
mod1_cta_env.json + .csv
mod2_trend_scan.json + .csv
mod3_macro_ratio.json + .csv
  ↓ commodity_cta_main.py（合并）
commodity_cta.json
  ↓ inject_commodity_cta.py（生成HTML/JS）
index.html（CTA tab）
```

## commodity_data.py — 数据层

- 数据源：Tushare fut_daily（期货连续合约，如 RB.SHF、CU.SHF）
- 增量策略：fut_daily.csv 作为持久化存储，每次只拉新日期
- 首次运行自动从 `_cache/` 目录迁移已有 JSON 缓存
- 回溯窗口：150个交易日
- 覆盖品种：黑色系(8)、有色金属(9)、贵金属(2)、能源化工(21)、农产品(20)，共60个品种
- 筛选规则：只保留连续合约（正则 `^[A-Z]+\.[A-Z]+$`）
- 编码：CSV 用 gb18030

运行：`python3 commodity_data.py`

## mod1_cta_env.py — CTA整体环境

从 fut_daily.csv 读取数据，计算每品种指标并汇总。

### 每品种指标

| 指标 | 计算方式 |
|------|----------|
| vol_20d | 近20日涨跌幅标准差 × √252 / 100（年化波动率） |
| ma20_slope | (MA20今日 - MA20昨日) / MA20昨日 × 100 |
| trend_dir | 多头(slope>0.5%) / 空头(<-0.5%) / 震荡 |
| volume_ratio | 成交额MA20 / 成交额MA60 |

### CTA友好度

```
CTA友好度 = (0.40 × 趋势品种占比 + 0.30 × 波动率分位 + 0.30 × 成交量比标准化) × 100
```

- 活跃品种筛选：日均成交额 > 500万
- 波动率分位：avg_vol_20d 在 0.10~0.40 区间线性映射
- 成交量比标准化：avg_volume_ratio 在 0.7~1.3 区间线性映射

输出：mod1_cta_env.json + mod1_cta_env.csv（含公式列）

## mod2_trend_scan.py — 品种趋势扫描

从 fut_daily.csv 读取数据，对每个活跃品种计算趋势评分。

### 品种评分

```
trend_score = 0.40 × |chg_20d|标准化 + 0.30 × vol_pctile_60d + 0.30 × volume_ratio标准化
```

| 指标 | 说明 |
|------|------|
| chg_20d | 20日涨跌幅 |
| trend_dir | MA20斜率判定（多头/空头/震荡） |
| vol_20d | 20日年化波动率 |
| vol_pctile_60d | 当前波动率在近60日滚动波动率序列中的分位数 |
| vol_trend | 当前波动率 > 6天前波动率 |
| volume_ratio | 成交额MA20 / MA60 |
| signal_count | 满足条件数：趋势确认 + 波动放大 + 放量(>1.2) |

每品种附带 `industry_drivers` 产业驱动因素文字说明（硬编码字典）。

输出：mod2_trend_scan.json + mod2_trend_scan.csv（含公式列），按 trend_score 降序排列。

## mod3_macro_ratio.py — 宏观比价信号

从 fut_daily.csv 读取数据，计算三组宏观比价。

| 比价 | 公式 | 含义 |
|------|------|------|
| 铜金比 | CU连续 / AU连续 | 上升=经济预期改善，下降=避险升温 |
| 油金比 | SC原油连续 / AU连续 | 上升=通胀预期/需求强，下降=衰退预期 |
| 工业品/农产品 | 工业篮子等权净值 / 农产品篮子等权净值 | 上升=工业品相对强势(经济扩张) |

- 工业篮子：RB, CU, AL, MA, TA, EG（等权归1复利）
- 农产品篮子：M, P, SR, C, OI, CF（等权归1复利）

每组比价输出：最新值、20日变化%、60日分位数、MA5斜率趋势（上升/下降/横盘）、完整时间序列。

输出：mod3_macro_ratio.json + mod3_macro_ratio.csv（含公式列）

## commodity_cta_main.py — 集成脚本

- `--run` 参数：完整运行（依次执行 mod1→mod2→mod3 + 合并）
- 无参数：仅合并已有的三个模块 JSON 为 commodity_cta.json
- 合并后打印汇总：CTA友好度、Top5趋势品种、宏观比价

运行：
```bash
python3 commodity_cta_main.py --run   # 完整运行
python3 commodity_cta_main.py         # 仅合并
```

## inject_commodity_cta.py — 注入脚本（新版）

读取 commodity_cta.json，生成包含以下内容的 HTML/JS 注入到 index.html：
- 总览卡片：CTA友好度、活跃品种数、趋势品种占比、平均波动率、成交量比、数据日期
- 宏观比价表格 + 三个比价走势图（铜金比、油金比、工业品vs农产品篮子净值）
- 品种趋势扫描 Top15 表格（含信号星级标记）
- 板块趋势分布卡片
- 指标说明面板

注入方式：找到 `<div class="strat-page" id="strat-cta">` 到 `<div class="strat-page" id="strat-convertible">` 之间替换。

## inject_commodity.py — 注入脚本（旧版）

与新版功能类似，但读取的 JSON 格式不同（旧版有 environment/scan/ratios/latest/meta 结构），包含 CTA友好度&趋势占比时序图、波动率&成交量比时序图。注入点为 `strat-cta` 到 `strat-arbitrage`。

## 完整更新流程

```bash
cd ~/Desktop/gamt-dashboard/commodity_cta
python3 commodity_data.py              # 1. 拉取/更新期货数据
python3 commodity_cta_main.py --run    # 2. 运行三个模块 + 合并
python3 inject_commodity_cta.py        # 3. 注入到主看板
```

## 缓存目录

`_cache/` — commodity_data.py 的 JSON 缓存（按日期存储 fut_daily API 响应），避免重复拉取。
