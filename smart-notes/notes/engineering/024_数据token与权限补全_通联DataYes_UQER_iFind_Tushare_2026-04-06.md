# 数据 token 与权限补全（通联 DataYes / UQER / iFind / Tushare）

## 背景

到 2026-04-06，GAMT / quant-backtest 这套研究链路里，已经不再只有 Tushare 和 iFind 两个数据入口，而是逐步补成四条线：

1. **Tushare**：A 股基础与部分衍生数据的长期兜底
2. **iFind**：海外行情、宏观、基金等更广覆盖的数据源
3. **通联 DataYes（HTTP）**：偏 Barra 风险模型的专项接口
4. **UQER / 优矿（SDK）**：更完整的股票 / 基金 / Barra 数据入口

这条笔记的目标不是讲 API 教程，而是把 **现有 token、权限边界、适合用途** 一次性记清楚，避免以后只记得“好像能用”，却忘了到底哪把钥匙开哪扇门。

---

## 当前可用数据源总览

| 数据源 | 体系 | 当前状态 | 更适合干什么 |
|---|---|---|---|
| Tushare | HTTP API | 可用 | A 股基础日频、交易日历、常规研究兜底 |
| iFind | 终端/API | 可用（另有到期时间） | 海外行情、宏观、基金、补 Tushare 不足 |
| DataYes | HTTP API | 可用，但偏专项 | **Barra CNE6 风险模型** |
| UQER | SDK / 优矿 | 可用 | **股票 + 基金 + Barra** 的统一研究入口 |

---

## 1. Tushare

### 现有配置
- Token：`33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd`
- 私有地址：`http://lianghua.nanyangqiankun.top`
- 状态：可用

### 当前定位
Tushare 不是最豪华的数据源，但它最大的价值是：

> **稳、熟、够用、适合做日常研究兜底。**

适合：
- A 股日线/基础行情
- 交易日历
- 指数基础数据
- 常规因子研究底表
- 当别的数据源权限不明时，先顶上

### 经验口径
- 公有 `https://api.tushare.pro` 直连通常更稳
- 开代理时容易超时，尤其 `trade_cal`
- Cloudflare 要走代理时，Tushare 反而更适合关代理直连

---

## 2. iFind

### 现有配置
- 账号：`glmssf001`
- Token 过期：`2026-04-07 19:04:12`

### 当前定位
iFind 这条线更像：

> **覆盖面更广的补充源，尤其适合 Tushare 覆盖不好的海外 / 宏观 / 基金口径。**

当前已知用途：
- SOXX 费城半导体
- 汇率等海外实时行情
- 宏观 / 基金等更广数据补位

---

## 3. 通联 DataYes（HTTP token）

### token
`5f8b8de95e7651d3c1f9ff491bde902e0e3587c546d44fc211adb755216139f5`

### 权限判断
这个 token 已确认：
- **能走 HTTP 方式访问 Barra 相关接口**
- **不能当作 UQER SDK token 使用**
- 用 UQER SDK 登录时会报：`无UQER SDK权限`

所以当前最准确的定位是：

> **这是通联 / DataYes 体系里的 Barra 专项 HTTP token，不是完整 UQER 账号 token。**

### 已知能拿的数据
主要是 Barra CNE6 风险模型五件套：
- `exposure`
- `factor_return`
- `specific_return`
- `covariance`
- `specific_risk`

### 更适合干什么
- 风格暴露分析
- 风格收益归因
- 协方差矩阵
- 特质风险 / 特质收益
- 组合风险拆解
- 未来做 Barra 约束回测

### 不适合默认指望什么
- 大而全股票行情库
- 全基金数据
- 普通 UQER SDK 扫库式研究

一句话：

> **这把钥匙主要是开 Barra 风险模型那扇门。**

---

## 4. UQER / 优矿（SDK token）

### token
`6b1c26f10036171bf12fa225d2bb98046db6a88b5999b0110c7fcfe574e810ce`

### 权限判断
这个 token 已确认：
- 可以用 `uqer.Client(token=...)` 正常登录
- 登录账号显示：`10693187@wmcloud.com`
- 不是纯 Barra 专项，而是 **完整 UQER / 优矿 SDK token**

### 已实测能拿的数据
#### 股票
- `MktEqudAdjGet`：A 股复权行情 ✅
- `SecIDGet`：证券主数据 ✅

#### Barra
- `RMExposureDayGet` ✅
- `RMFactorRetDayGet` ✅
- `RMSpecificRetDayGet` ✅
- `RMCovarianceDayGet` ✅
- `RMSriskDayGet` ✅

#### 基金
- `MktFunddGet`：ETF 日行情 ✅（如 `510300`）
- `FundNavGet`：公募基金净值 ✅（如 `110027 易方达安心回报债券A`）

### 当前最合理的定位

> **这是股票 + 基金 + Barra 三层都能打通的主力研究 token。**

### 更适合干什么
- A 股日频研究
- 股票池和因子研究
- 基金净值 / ETF 行情研究
- 固收+基金研究的净值序列补充
- Barra 风格暴露与风险归因
- 给 `quant-backtest` 做统一研究入口

一句话：

> **如果 DataYes token 是 Barra 专项刀，那 UQER token 更像一把多用途瑞士军刀。**

---

## 实操分工建议

### 最稳的分工
#### Tushare
- 做基础兜底
- 适合常规 A 股研究和日常稳定更新

#### iFind
- 做海外 / 宏观 / 基金 / 更广覆盖补位
- 尤其适合 Tushare 不够的部分

#### DataYes / 通联 HTTP token
- 专门做 Barra 五件套
- 不要拿它去幻想全库权限

#### UQER token
- 做主力探索入口
- 股票、基金、Barra 都优先从这边接

---

## 对当前研究链路的意义

现在这套配置补齐后，Roni 这边的数据能力已经从“两个源勉强拼起来”变成：

> **Tushare 兜底 + iFind 补广度 + DataYes 补 Barra 专项 + UQER 补股票/基金/Barra 一体化。**

这意味着后面几条线都更顺了：
- `quant-backtest`：Barra 约束 / 风格归因 / 基础股票研究
- GAMT：风格暴露解释层、基金净值补充、更多统一数据入口
- 固收+：基金净值与产品横向比较更容易落地

---

## 注意事项

- 这些 token 不要乱扫库，尤其是朋友账号，优先走 **少量调用 + 本地缓存**。
- DataYes 和 UQER 不是同一种权限体系，不能混着理解。
- “能登录”不等于“全库都开了”；但当前已知，UQER 这把 token 的研究价值已经很高。

---

## 一句话总结

到 2026-04-06 为止，这套数据底盘可以这么记：

> **Tushare 管基础兜底，iFind 管广覆盖补位，通联 DataYes 管 Barra 专项，UQER 管股票 + 基金 + Barra 的主力接入。**
