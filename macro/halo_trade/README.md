# HALO 交易观察模块

## 目标
追踪高盛 HALO 策略（重资产范式转移）的核心验证指标，生成可视化看板。

## 数据源设计

### 1. 超大规模 CapEx 追踪（核心）
- **数据来源：** 季报财务数据（微软/亚马逊/谷歌/Meta）
- **关键指标：** 
  - CapEx 绝对值（单季 + TTM）
  - CapEx 同比增速
  - **CapEx 二阶导**（增速的变化率，判断加速/平稳/转负）
- **获取方式：** 
  - 优先：iFind API `THS_BasicData` 获取 CapEx
  - 备选：yfinance 获取季报 cash flow statement

### 2. 重资产 vs 轻资产 EPS 对比
- **数据来源：** 行业 EPS 增速数据
- **关键指标：**
  - 公用事业/能源/国防 EPS 增速（重资产代表）
  - 软件/互联网 EPS 增速（轻资产代表）
  - 增速差值（重资产 - 轻资产）
- **获取方式：** 
  - iFind 行业 EPS 数据
  - 或用代表性 ETF（XLU/XLE/ITA vs XLK/IGV）的成分股 EPS 加权

### 3. 电力需求 & 价格
- **数据来源：** 
  - Henry Hub 天然气价格（yfinance: NG=F）
  - 美国电价指数（EIA API 或 yfinance 电力 ETF）
- **关键指标：**
  - 天然气价格走势
  - 电力 ETF（如 XLU）价格 vs 标普500相对强弱

### 4. 地缘风险 & 国防订单
- **数据来源：**
  - 叙事监控系统：地缘风险 + 全球再武装热度分数
  - 国防股价格：LMT（洛克希德）、RTX（雷神）
- **关键指标：**
  - 叙事热度 MA7
  - 国防股相对标普500超额收益

### 5. 标的股价追踪
- **核心标的：**
  - 能耗：CEG（Constellation）、GEV（GE Vernova）、ETN（伊顿）、NEE（NextEra）
  - 国防：LMT、RTX
  - 价值：XOM（埃克森）、JPM（摩根大通）
  - 过渡：MSFT（微软）
- **获取方式：** yfinance 或 iFind

## 输出设计

### 看板结构
```
HALO 交易仪表盘
├── 核心信号区
│   ├── CapEx 二阶导仪表（加速/平稳/转负）
│   ├── 重资产 vs 轻资产 EPS 剪刀差
│   └── 叙事热度雷达图（AI_CapEx / 全球再武装 / 地缘风险）
├── 三主线追踪
│   ├── AI 能耗主线：CEG/GEV/ETN/NEE 相对强弱 + 天然气价格
│   ├── 地缘重装主线：LMT/RTX 相对强弱 + 叙事热度
│   └── 盈利兑现主线：XOM/JPM 相对强弱 + 通胀预期
└── 场景判断
    └── 根据信号组合自动输出：逻辑强化 / 估值充分 / 逻辑受损
```

### 文件输出
- `halo_data.json`：所有原始数据 + 计算指标
- `halo_dashboard.html`：可视化看板（echarts）
- `halo_signal.txt`：当前场景判断 + 操作建议

## 实现步骤
1. `halo_data.py`：数据拉取 + 指标计算
2. `halo_calc.py`：CapEx 二阶导 + EPS 剪刀差 + 场景判断逻辑
3. `halo_render.py`：生成 HTML 看板
4. 集成到 GAMT 主看板（新增 HALO 交易 tab）

## 数据更新频率
- CapEx / EPS：季度更新（财报季）
- 股价 / 叙事热度：每日更新
- 天然气 / 电价：每日更新
