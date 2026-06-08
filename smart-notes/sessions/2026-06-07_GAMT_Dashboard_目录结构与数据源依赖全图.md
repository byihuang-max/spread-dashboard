# GAMT Dashboard 目录结构与数据源依赖全图

**日期**: 2026-06-07
**标签**: #GAMT Dashboard #数据源依赖 #模块架构 #调度批次 #iFind #系统运维

---

## 摘要

整理了 GAMT Dashboard 七层模块的目录树、各模块数据源（iFind/Tushare/UQER/akshare）及批次调度逻辑。重点标注了 iFind token 到期、EDB 月额度耗尽、crowding.json 静默失效等五个关键检修风险点。

## 正文

GAMT Dashboard 目录结构与数据源依赖图（2026-06-07 整理）

## 目录树（服务器 /home/ubuntu/gamt-dashboard/）

宏观层(macro/): fundamentals基本面 / liquidity流动性 / rates利率汇率 / global_calendar全球日历 / halo_trade / meme叙事 / score宏观打分
中观层(meso/): chain_prosperity产业链景气 / ai_computing_rotation AI算力轮动
微观资金层(micro_flow/): crowding行业拥挤度 / patient_capital耐心资本 / option_sentiment期权情绪
策略适配层(env_fit/): quant_stock量化股票 / momentum_stock强势股 / commodity_cta商品CTA / cb_env转债 / option_vol期权卖权 / arbitrage套利
风格轧差(size_spread/): 风格因子+Barra
接龙股票池(stock-pool/): 服务器自跑，render.py生成
基金财报(fund-asset-recommend / fund_analysis / financial_risk)
预警(alerts/)
工具(factor-forge因子实验室 / chip_query筹码查询 / zsxq知识星球)
调度(server/update_all.py + module_registry.py)

## 数据源依赖

全局优先级：iFind（宏观/财报/行业）/ Tushare（行情/资金/期权/日历）/ UQER优矿（日线周线/Barra，stock-pool专用）/ akshare（仅HALO）/ 读JSON（无API，依赖上游产出）

各模块数据源：
- 宏观fundamentals: PMI/CPI/PPI走Tushare；工业产值/社融/FAI/地产等24个指标走iFind EDB（月度，当前因月额度-4318暂停，等7月重置）
- 宏观liquidity/rates: Tushare+iFind
- macro/halo_trade: Tushare+iFind+akshare三源
- macro/meme/antifragile反脆弱: iFind唯一源
- 中观chain_prosperity/ai_computing_rotation: Tushare+iFind（ai_computing也调EDB）
- micro_flow/crowding行业拥挤度: Tushare，LATE批次21:00；⚠️被stock-pool依赖（题材热度的crowding.json和sw_member_map.csv）
- env_fit所有策略模块: Tushare为主；⚠️全部前置依赖size_spread/fund_nav/fund_nav_data.py（产品净值）
- stock-pool接龙股票池: UQER（日线/周线）+ Tushare（30分钟）；⚠️依赖micro_flow/crowding/crowding.json
- env_fit/option_vol: 写env_fit_signals.json，被宏观打分读取（关键下游）
- 宏观打分macro_score: 读JSON（无API），只用PMI/美林时钟/CPI-PPI，不依赖EDB停更字段，安全
- overview仪表盘汇总: 读所有模块JSON，最后跑

## 批次调度
am 8:20: 宏观/日历/基础数据
close 17:00: 行情收盘后：风格/量化/CTA/转债/期权/套利/预警/HALO
late 21:00: 需T+1数据：Barra/拥挤度/强势股/耐心资本/并购池/汇总
手动: stock-pool（接龙名单更新）/ 财报 / 基金优选

## 关键检修入口
1. iFind token到期2026-07-20：影响宏观/HALO/财报/反脆弱/中观景气/并购池
2. iFind EDB月额度-4318：影响fundamentals的24个指标（月度低频，月底重置）；7月1日提醒已设
3. UQER token失效：影响stock-pool+Barra，用DataAPI.MktEqudAdjGet探针验证
4. crowding.json不跑：stock-pool题材热度静默变空表，不报错
5. env_fit_signals.json写失败：宏观打分会用旧数据，不阻断但数据过期
