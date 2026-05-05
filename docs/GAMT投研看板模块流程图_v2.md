# GAMT 投研看板模块流程图 v2

> **来源：** `~/Desktop/GAMT投研看板模块流程图_v2.xmind`（2026-05-05 生成）
> **生成方式：** 从 xmind 节点树按 H2/H3/缩进列表自动翻译
> **三支独立展开：** A 业务流（方法论主干）+ B 文件夹镜像（开发进度）+ C 对客逻辑缺口（PM 视角）
> **如需重新生成：** `python3 /tmp/xmind_to_md.py > docs/GAMT投研看板模块流程图_v2.md`

---

## 🧭 A. 业务流（方法论主干 + 勾稽关系）


### 🎯 方法论总纲（主干锚）

- 择时重于选股
- 周期重于题材
- 个股先于情绪
- 情绪先于大盘
- → 看板定位：PM 之间的情绪接力交叉验证层（非端到端量价 alpha）
- → 看板核心职责：把人工盘面语言翻译成 PM 可计算的状态框架

### ⭐ 主干链条（情绪接力 → 敞口）

- ① 个股信号层（env_fit/momentum_stock）
  - 输入：Tushare 涨停/炸板/首板/晋级/1进2 原始数据
  - 产出：leader_pool_history · 龙头池（辨识度 + 成交额）
  - 产出：chain_rank_history · 产业链强度
  - 产出：momentum_sentiment / sector / warning / return_decomp
  - 被下游调用：→ 情绪结构层 / 择时因子库 / 强势股日报
- ② 情绪结构层（micro_flow + momentum 聚合）
  - 输入：momentum 龙头池 + 拥挤度 + 期权 IV + ETF 大单
  - 聚合状态：梯队高度 / 断板率 / 晋级率 / 炸板率 / 成交集中度
  - 状态分类：量价齐升 / 量价齐跌 / 价升量不跟 / 量升价不升
  - 被下游调用：→ 大盘确认层 / 择时因子
- ③ 大盘确认层（quant_stock + 成交额/两融/涨跌家数）
  - 输入：情绪结构层信号 + 宽基指数 + 成交额 + 两融
  - 作用：交叉验证情绪信号是否传导到大盘
  - 关键指标：Top5% 集中度 / 20 日均线占比 / 北向 / ETF 净流入
  - 被下游调用：→ 择时敞口
- ④ 择时敞口层（timing-research + quant-backtest/timing_model）
  - 输入：①②③ 三层信号 → 因子库
  - 产出：latest_factors / factor_system / IC 表
  - 产出：live_exposure_nav · 实盘净值（T→T+1 中证2000）
  - 产出：明日待执行信号（pending 行）
  - 外部依赖：📌 quant-backtest/timing_model/（workspace 外主研发地）
  - 被下游调用：→ 产品翻译 / PM 输出
- ⑤ 产品翻译层（fund_nav + fund-asset-recommend + size_spread）
  - 输入：敞口信号 + 各策略环境打分
  - 作用：把抽象判断翻译到具体基金产品
  - 产出：fund_nav（5 类策略净值）/ 风格轧差 / 团队基金优选池
- ⑥ PM 翻译输出层（首页 + 日报 + 飞书 + 邮件 + Smart Notes）
  - 首页 index.html · 深度用户（PM 自己）入口
  - 强势股日报 v1.5 · send_daily_email + send_daily_card
  - FOF 每日市场简报 · fof每日市场飞书脚本v3
  - Smart Notes · 研究沉淀（跨层）
  - 管理后台 admin.html · 权限/审核/订阅者管理

### 🏛️ 支撑柱 · 平行馈入主干（非顺序层）

- 宏观约束池 → 馈入 ④⑤
  - macro/liquidity · 境内流动性
  - macro/rates · 全球利率汇率
  - macro/fundamentals · 基本面 + 利润周期
  - macro/meme · 叙事生命周期
  - macro/score · 宏观综合打分
  - 作用：回答'风险资产外部约束'，不直接决定买什么
- 中观景气池 → 馈入 ②④
  - meso/chain_prosperity · 产业链景气度
  - meso/ai_computing_rotation · AI 算力链轮动
  - financial_risk · 财报预期风险
  - 作用：回答'资金愿意交易哪些方向'
- 风险预警池 → 馈入 ⑥
  - alerts · 5 维红灯
  - macro/halo_trade · HALO 交易（重资产范式）
  - macro/meme/antifragile · 反脆弱（海外风险监控）
  - 作用：极端事件告警，不进入主干评分

### 🔀 横切层

- 数据健康
  - server/module_registry · 模块注册
  - server/update_all · 全量更新状态
  - overview_calc / overview.json · 最新值监控
- 权限与分发
  - auth.py / users.db · 四级权限（admin/tier2/tier1/tier0）
  - module_permissions_config.html · 配置入口
  - 团队工作台 team.html / 订阅者管理
- 研究沉淀
  - smart-notes · 概念/对话/决策/会话
  - zsxq · 外部内容采集入口（→ 可喂给 smart-notes）
- 工具脚本
  - mall_sdk · 火富牛 SDK
  - chip_query · 个股筹码查询
  - scripts · sync-to-cloud 等部署脚本

### 🔴 优化建议（独立栏目 · 开发指引）

- 🔴 A 类 · 结构型 · 高优先级（影响顶层认知）
  - 1. env_fit/momentum_stock 在文件树里和 CTA/转债/套利同级 → 但方法论上它是主干核心。建议图上提升为 ⭐ 标记，代码可不动；或物理提升为一级目录 momentum_core/
  - 2. timing-research/ 定位模糊 → 现在既展示又混入 generate_*.py 脚本。建议明确：展示 = timing-research/、研发 = quant-backtest/timing_model/，两侧各自 README 互引
  - 3. macro/meme/antifragile 语义错位 → antifragile 做海外跨市场风险监控，不是叙事子集。建议提升为 macro/antifragile/，macro/meme 保留叙事生命周期
  - 4. financial_risk_factor.html 在 financial_risk/ 和 timing-research/ 同名重复 → 位置二选一，另一个只做跳转链接
- 🟡 B 类 · 版本清理 · 中优先级
  - 5. timing-research/ 堆积了 index_old / index_old_sentiment / index_backup_20260315 / index_v3_new / ice_point_report（v1）→ 全部搬到 timing-research/_archive/
  - 6. fund_analysis/fixed_income_plus.py / _v2.py / _final.py 三版本共存 → 定版为 _final.py，其余归档
  - 7. financial_risk/ 4 个 build_*.py 并存 → 明确主用（建议 ifind 版为主），其余归档并在 README 说明适用场景
  - 8. daily_report/meme交易/narrative_monitor_v1_backup.py → 归档到 _archive/
  - 9. macro/halo_trade/halo_dashboard.html.bak / .tmp → 删除残留
  - 10. env_fit/commodity_cta/inject_commodity_cta.py.bak → 删除
  - 11. size_spread/风格轧差看板.html 与 style_spread.html 同功能 → 统一为英文命名
- ⚫ C 类 · 空壳与边界 · 待决策
  - 12. macro/ms_merrill_clock/ 只有 test_*.py → 两条路：(a) 补完正式 data/calc/html 纳入 macro/score；(b) 删除目录、清理注册表
  - 13. zsxq/ 与 smart-notes/ 分工不清 → 建议定义：zsxq = 采集入口（只进不出），smart-notes = 精炼沉淀（PM 可见）
  - 14. env_fit/option_vol/mod4 三个版本（v1/v2/snapshot）和 mod7 两个版本 → 当前用哪个？其余归档或合并
  - 15. env_fit/commodity_cta/mod1 / mod1b / mod1c / mod2 / mod2b / mod3 命名规律好，但 PCA 两套（1b、2b）是否并用？文档里确认
- 🟢 D 类 · 长期方向 · 低优先级但建议启动
  - 16. env_fit/ 下 option_vol / arbitrage / commodity_cta 都用 mod1/mod2/mod3 命名 → 可抽出 env_fit/_framework/ 定义'环境模块'的标准接口（data → mod → inject → html）
  - 17. env_fit/quant_stock/ 文件扁平平铺（amount_vol/cross_vol/excess_attribution/quant_env_diag 各自成对）→ 可以加子文件夹 subfactors/ 分类
  - 18. 所有模块的 .json 输出和 .html 展示可以考虑统一契约：data 是 py → json → html 的三段式（部分模块已是，部分没对齐）
  - 19. 看板的'PM 翻译器'属性 → index.html 首屏可以加一张'今日主干信号看板'，把①②③④浓缩成 5-8 行结论（对 PM 只看结论的场景更友好）
- 💡 E 类 · 对 PM 服务的增量思考
  - 20. Roni 的长板是'逻辑'而不是'多因子暴力'→ 看板应强化'为什么'而非'是什么'。每个关键判断旁应有'逻辑链一句话'（如 价格止跌 → 利润修复 → 股票环境改善）
  - 21. PM 缺灵感的场景 → 首页可加'当日叙事热度 TOP3'+'与之对应的产业链位置'，把叙事-产业-个股三段式直接端给 PM
  - 22. FOF 基金经理自己选策略场景 → env_fit 各策略的'顺逆风打分'可做一个横向对比表（已有基金净值，还缺'策略环境分 × 基金实盘净值'的联合视图）

## 📂 B. 文件夹镜像（开发进度地图）


### 🏠 根目录 · 前台入口

- 🟢 index.html · 主看板（用户入口）
- 🟢 admin.html · 管理后台
- 🟢 team.html · 团队工作台（tier≥2）
- 🟢 module_permissions_config.html · 权限配置

### ⚙️ server/ · 调度与权限中枢

- 🟢 module_registry.py · 模块注册表
- 🟢 update_all.py · 全量更新主入口
- 🟢 refresh_server.py / start_refresh.py · 刷新服务
- 🟢 auth.py / users.db · 权限与用户
- 🟢 overview_calc.py / overview.json · 总览数据
- 🟢 chip_api.py · 筹码查询接口
- 🟢 narrative_api.py · 叙事接口
- 🟡 users.db.bak.* · 多个备份文件累积（可清理）

### 🌍 macro/ · 宏观层

- macro/liquidity · 境内流动性
  - 🟢 liquidity_data.py
  - 🟢 liquidity_calc.py
  - 🟢 liquidity.html / .json
- macro/rates · 全球利率与汇率
  - 🟢 rates_data.py
  - 🟢 rates_calc.py
  - 🟢 rates.html / .json
- macro/fundamentals · 经济基本面
  - 🟢 fundamentals_data.py / calc.py / html / json
  - profit_cycle · 利润周期子模块
    - 🟢 profit_cycle_data.py
    - 🟢 profit_cycle.csv / .json
    - ⚫ 无独立 html，依附 fundamentals 展示
- macro/halo_trade · HALO 交易
  - 🟡 halo_data.py / halo_data_ifind.py / halo_data_ifind_full.py（3 套数据源并存）
  - 🟡 halo_calc.py / halo_calc_ifind.py
  - 🟡 halo_financials.py / halo_financials_tushare.py
  - 🟢 halo_pe_scissors.py / _etf / _tushare
  - 🟢 china_halo.py · 中国版
  - 🟢 halo_dashboard.html
  - 🔴 halo_dashboard.html.bak / .tmp · 残留临时文件（需清理）
  - 🟢 backfill_pe_history.py
- macro/meme · 叙事与反脆弱
  - 🟢 macro_lifecycle.py · 叙事生命周期
  - 🟢 lifecycle_history.csv / lifecycle_output.json
  - ⚫ antifragile · 反脆弱子目录（位置存疑）
    - 🟢 fetch_data.py / fetch_data_ifind.py
    - 🟢 calc_corr.py / calc_meme.py
    - 🟢 antifragile.html / antifragile_nav.json
    - 🟢 meme_signal.json / rolling_corr.json
    - 🟢 render_html.py
    - 🔴 test_yf.py / fetch_data_ifind_test.py · 测试脚本未归档
- 🔴 macro/ms_merrill_clock · 美林时钟
  - 🔴 只剩 test_*.py 测试脚本，无正式 data/calc/html
  - 🔴 空壳状态，需决策：补完 or 删除
- macro/score · 宏观综合打分
  - 🟢 macro_score.py / .json
  - 🟢 score_config.json / prev_allocation.json
  - 🟢 README.md

### 🏭 meso/ · 中观层

- meso/chain_prosperity · 产业链景气度
  - 🟢 chain_data.py / chain_calc.py
  - 🟢 chain_prosperity.html / .json
- meso/ai_computing_rotation · AI 算力链轮动
  - 🟡 data_fetcher.py · 数据获取（迭代中）
  - 🟡 signal_engine.py · 信号引擎
  - 🟡 run_daily.py · 日更入口
  - 🟢 config.py
  - 🟢 flowchart.html · 展示
  - 🟢 DESIGN.md / FLOWCHART.md

### 💧 micro_flow/ · 微观资金与结构

- micro_flow/crowding · 拥挤度
  - 🟢 crowding_data.py / crowding_calc.py
  - 🟢 crowding.html / .json
- micro_flow/option_sentiment · 期权情绪
  - 🟢 option_data.py / option_calc.py
  - 🟢 option_sentiment.html / .json
- micro_flow/patient_capital · 耐心资本（ETF 大单）
  - 🟢 patient_data.py / patient_calc.py
  - 🟢 patient_capital.html / .json
  - 🟢 raw_15min/ · 明细数据

### 🎯 env_fit/ · 策略环境适配

- env_fit/quant_stock · 宽基量化股票
  - 🟢 quant_stock_data.py / .json / .html
  - 🟢 amount_vol_calc.py / amount_vol.json
  - 🟢 cross_vol_data.py / cross_vol_extend.py / cross_vol_history_fetch.py
  - 🟢 excess_attribution.py / .json · 超额归因
  - 🟢 quant_env_diag.py / .json · 环境诊断
  - 🟢 inject_quant_stock.py
  - ⚫ 文件结构扁平（4 套子因子平铺，可考虑子文件夹分类）
  - 📌 qs_fut_daily.csv / qs_index_daily.csv · 本地缓存
  - 🟢 流动性评分权重表.md / _v2.md
- ⭐ env_fit/momentum_stock · 强势股情绪（主干核心）
  - 🟢 momentum_data.py · 涨停/炸板/首板基础数据
  - 🟢 momentum_sector.py / .json · 行业涨停方向
  - 🟢 momentum_return_decomp.py / .json · 收益分解
  - 🟢 momentum_warning.py / .json · 警报
  - 🟢 limit_index/ · 涨停指数（含 seal_spread）
  - 🟢 chain_rank_history/ · 产业链强度历史
  - 🟢 leader_pool_history/ · 龙头池历史（被择时层引用）
  - 🟢 chain_etf_map.json / industry_l2_etf_map.json / sector_chain_map*.json
  - 🟢 update_etf_map.py
  - 🟢 momentum_daily_report.py · 日报生成
  - 🟢 send_daily_card.py · 飞书卡片
  - 🟢 send_daily_email.py · 邮件
  - 🟢 email_manage.html / email_subscribers.json
  - 🟢 inject_momentum.py
- env_fit/commodity_cta · 商品 CTA
  - 🟢 commodity_data.py / commodity_cta_main.py / .json
  - 🟢 mod1_cta_env.py · 环境
  - 🟡 mod1b_pca_engine.py · PCA 引擎
  - 🟡 mod1c_market_vol.py · 市场波动
  - 🟢 mod2_trend_scan.py · 趋势扫描
  - 🟡 mod2b_pca_loading.py
  - 🟢 mod3_macro_ratio.py · 宏观比价
  - 🟢 cta_return_decomp.py / .json
  - 🟢 inject_commodity_cta.py
  - 🔴 inject_commodity_cta.py.bak · 残留备份
  - 📌 fut_daily.csv / mod*.csv · 本地缓存
  - 🟢 README.md
- env_fit/cb_env · 转债指增
  - 🟢 cb_data.py / cb_calc.py / .json
  - 🟢 cb_env.csv / .json / cb_env_activity.json
  - 🟢 inject_cb_env.py / inject_cb_nav.py
  - 📌 cb_basic.csv / cb_daily.csv / idx_daily.csv / stk_daily.csv · 本地缓存
  - 🟢 README.md
- env_fit/option_vol · 期权卖权
  - 🟢 option_vol_main.py / .html / .json
  - 🟢 mod1_rv_regime.py · RV 状态
  - 🟢 mod2_iv_spread.py · IV 价差
  - 🟢 mod3_skew_term.py · 偏度与期限
  - 🟡 mod4_iv_percentile.py / _v2.py / _snapshot.py · 3 个版本并存
  - 🟢 mod5_liquidity_percentile.py
  - 🟢 mod6_timing_signal.py
  - 🟡 mod7_market_breadth.py / _v2.py · 2 版本
  - 🟢 mod8_sell_window_signal.py
  - 🟢 mod9_composite_score.py / .json
  - 🟢 mod10_contract_scanner.py
  - 🟢 backfill_history.py / calc_signal.py
  - 🟢 iv_percentile.html / liquidity_percentile.html · 独立展示页
  - 🟢 sell_window_signal.json / timing_signal.json / market_breadth.json
  - 🟢 contract_opportunities.json · 合约机会
- env_fit/arbitrage · 套利
  - 🟢 mod1_index_arb.py / .json · 指数套利
  - 🟢 mod2_commodity_arb.py / .json · 商品套利
  - 🟢 mod3_option_arb.py / .json · 期权套利
  - 🟢 hv_long.py / .json · HV long 策略
  - 🟢 arbitrage.html
  - 🟢 fetch_incremental.py
  - 📌 arb_cache.json / _opt_cp_map.json

### 🔬 timing-research/ · 择时研究展示层

- ⚫ 定位：仅展示层，正式研究在 quant-backtest/timing_model/（workspace 外）
- 🟢 index.html · 择时主页
- 🟢 factor_system.html · 因子系统
- 🟢 latest_factors.html · 最新因子
- 🟢 live_exposure_nav.html · 实盘净值
- 🟢 ml_exposure_score.html · ML 敞口评分（10 日研究）
- 🟢 single_factor_test.html · 单因子测试
- 🟢 timing_backtest.html · 回测展示
- 🟢 multi_index_timing.html · 多指数择时
- 🟢 factor_down_count.html · 因子下跌计数
- 🟢 financial_risk_factor.html · ⚫ 与 financial_risk/ 同名重复
- 🟢 leader_pool_report.html · 龙头池报告
- 🟢 ice_point_report_v2.html · 冰点报告
- 🟡 ice_point_card_v2.html / ice_tabs_new.html · 卡片/Tab 版
- 🟢 intraday_limit_replay.html · 日内涨停回放
- 🔴 index_old.html / index_old_sentiment.html · 历史版本
- 🔴 index_backup_20260315.html · 备份
- 🔴 index_v3_new.html · 3.x 版本残留
- 🔴 ice_point_report.html · 被 _v2 取代
- 🟢 generate_leader_pool.py / export_leader_pool_history.py
- 🟢 generate_replay_page.py / push_limit_replay_feishu.py
- 🟢 update_ic_table.py
- 🟢 leader_pool_latest.json / industry_deterioration_rules.json
- 🟢 leader_pool_history/ · 历史池
- 🟢 data/ · 择时因子数据

### 💰 size_spread/ · 风格轧差

- 🟢 compute_spreads.py / fetch_incremental.py
- 🟢 style_spread_signals.py / .json
- 🟢 render_html.py / inject_style_spread.py
- 🟢 style_spread.html
- 🔴 风格轧差看板.html · 中文命名冗余（建议统一）
- 📌 style_spread_cache.json
- fund_nav · 基金净值跟踪
  - 🟢 fund_nav_data.py
  - 🟢 fund_nav.html / .json
  - 🟢 fund_nav_quant-stock / momentum-stock / cta / convertible / arbitrage.json

### 📊 fund-asset-recommend/ · 团队基金优选

- 🟢 fund_asset.html / fund_asset_template.html
- 🟢 scripts/ · 拉取脚本
- 🟢 data/raw/ · 原始数据
- 🟢 README.md

### 📈 fund_analysis/ · 公募基金研究（固收+）

- 🟢 fund_research.html
- 🟡 fixed_income_plus.py / _v2.py / _final.py · 3 版本并存
- 🟢 fixed_income_plus_analysis.csv · 研究结果
- 🟢 bond_capability_analysis.csv · 债基能力
- 🟢 nav_fetcher/fetch_nav.py · 基金净值拉取

### 📊 financial_risk/ · 财报预期风险

- 🟢 financial_risk_factor.html
- 🟡 build_financial_risk_json.py · 主构建脚本
- 🟡 build_financial_risk_ifind.py · iFind 源
- 🟡 build_financial_risk_tushare.py · Tushare 源
- 🟡 build_financial_risk_json_from_snapshot.py · 快照源
- 🟢 build_financial_validation_tables.py · 验证表
- ⚫ 4 个构建脚本并存，需明确主用哪个（其余归档）

### ⚠️ alerts/ · 红灯预警

- 🟢 alerts_data.py / alerts_calc.py
- 🟢 alerts.html / .json
- 🟢 us_alerts_data.py / _calc.py / .json · 美股预警

### 📋 daily_report/ · 每日投研简报

- 🟢 fof每日市场飞书脚本v3.py · 日报主脚本
- meme交易/ · Meme 日报
  - 🟢 narrative_monitor_v2.py · 叙事监控
  - 🔴 narrative_monitor_v1_backup.py · 旧版备份
  - 🟢 discover_themes.py / backfill_history.py
  - 🟢 lifecycle_model.json / narrative_evolution.json / transmission_chain.json
  - 🔴 test_discover.py / test_tushare_news.py · 测试脚本

### 🔍 chip_query/ · 个股筹码查询

- 🟢 chip_analyzer.py · 筹码分析
- 🟢 data_source.py / ifind_enricher.py
- 🟢 chip_query.html

### 🧰 基础设施

- mall_sdk/ · 火富牛 SDK（fof99）
  - 🟢 fof99/ · SDK 主体
  - 🟢 examples/ · 示例
  - 🟢 requirements.txt / README.md
- smart-notes/ · 智能笔记（跨层研究沉淀）
  - 🟢 concepts/ · 概念笔记
  - 🟢 conversations/ · 对话笔记
  - 🟢 decisions/ · 决策笔记
  - 🟢 sessions/ · 会话笔记
  - 🟡 notes/emerging_markets · 新兴市场
  - 🟡 notes/engineering · 工程
  - 🟡 notes/research · 研究
  - 🟡 notes/reports · 报告
- ⚫ zsxq/ · 知识星球爬虫
  - 🟢 crawler.py / config.json / README.md
  - ⚫ 与 smart-notes 语义有重叠，需明确分工
- data/ · 全局数据
  - 🟢 financial_validation/ · 财报验证数据
- 其他
  - 🟢 scripts/ · 工具脚本（sync-to-cloud.sh 等）
  - 🟢 static/ · 静态资源
  - 🟢 vendor/ · 第三方库（echarts/chart.js）
  - 🟢 logs/ · 运行日志
  - 🟢 docs/ · 文档
  - 🟢 _archive/ · 归档目录（已有，建议扩大使用）

### 📖 图例

- 🟢 稳定维护
- 🟡 迭代中 / 多版本并存
- 🔴 空壳 / 废弃 / 残留文件
- ⚫ 位置可疑 / 需讨论
- ⭐ 主干核心模块
- 📌 数据缓存 / 外部依赖

## 🔴 C. 对客逻辑缺口（PM 视角 · 非代码层）


### 🔴 对客严重影响 · 打开看不懂 / 没结论 / 缺翻译

- 1. 宏观层全系缺'传导链小字'
  - 涉及：macro/liquidity · macro/rates · macro/fundamentals
  - 痛点：PM 看到 Shibor/美债/PMI 数字后会问'所以呢'
  - 建议：每个宏观指标配一句传导链（例：价格止跌→利润修复→股票环境改善）
- 2. option_vol 子模组太多缺'今日主表'
  - 痛点：mod1-mod10 十个子页分散，PM 找不到主结论
  - 建议：首屏加'今日卖权机会 TOP5 合约'
- 3. crowding / option_sentiment 缺人话翻译
  - 痛点：85 分位 / IV 80 分位 PM 不知道意味着什么
  - 建议：数字旁配'历史类似位置后续 N 日胜率'
- 4. CTA / 套利结论没翻译到'基金配置'维度
  - 痛点：PM 是配基金不是自己做 CTA/套利
  - 建议：CTA 环境分直接映射到'加减仓 CTA 基金'的结论 + 关联 fund_nav

### 🟡 对客体验差 · 有结论但链条断 / 不联动

- 5. ⭐ 策略环境 × 基金实盘 联动缺（最高 ROI）
  - 涉及：env_fit/* × size_spread/fund_nav
  - 痛点：两边各自独立，PM 最想要的联合视图没做出来
  - 建议：'量化股票环境 75 分 → 产品 A 涨 0.3% 产品 B 跌 0.1% → 归因解释'
- 6. alerts 只告警不给动作
  - 痛点：5 维红灯触发后'接下来怎么办'断链
  - 建议：每级红灯配建议动作清单
- 7. macro/score 打完分没映射到策略
  - 痛点：宏观 70 分意味着量化加还是减？
  - 建议：加'宏观分 × 6 类策略顺逆风'矩阵
- 8. momentum_stock 盘中实时视图缺
  - 痛点：只有昨日日报，盘中看不到情绪温度
  - 建议：盘中情绪温度条（涨停数/炸板率/龙头走势，15 分钟刷新）
- 9. leader_pool 命中率没统计
  - 涉及：timing-research/leader_pool_history · env_fit/momentum_stock/leader_pool_history
  - 痛点：池内股票的后续表现没形成闭环
  - 建议：leader_pool_history 做'入池后 N 日收益'统计

### 🟢 小优化 / 长期价值

- 10. ai_computing_rotation 最后一公里没收口
  - 痛点：研究框架完整但'具体买什么 ETF/股票'没落地
  - 建议：每个篮子挂代表性 ETF + 3-5 只核心股票白名单
- 11. 产业链轮动可视化缺
  - 涉及：meso/chain_prosperity
  - 痛点：产业链之间的轮动路径和节奏没展示
  - 建议：加产业链轮动路径图 + 当前位置标记
- 12. 日报角色定制化
  - 涉及：daily_report/fof每日市场飞书脚本v3
  - 痛点：一份日报打天下（FOF/量化/主观 PM 内容应不同）
  - 建议：日报拆 2-3 个角色视图
- 13. Smart Notes 对外（toC 钩子候选）
  - 痛点：你的长板'逻辑'锁在内部文件树里没对外
  - 建议：做'逻辑笔记看板'，toB 精选对外、toC 可做付费墙
- 14. halo_trade 入选理由透明化
  - 痛点：给 PM 选股结果但没给选股理由
  - 建议：每个 HALO 标的配三行入选理由（PE 剪刀差/资本开支/盈利位置）
- 15. 固收+研究进看板
  - 涉及：fund_analysis/ · 桌面'债券基金研究表.csv'
  - 痛点：现在是静态 CSV，没进 GAMT
  - 建议：固收+研究做成看板（3/6/9 月收益窗口比较）
- 16. 团队优选池决策记录
  - 涉及：fund-asset-recommend
  - 痛点：进池出池没决策轨迹
  - 建议：每次进/出池记录理由，让 PM 学到你的挑基逻辑（toB 金矿）

### 📖 补充说明

- 本支线视角 = 对客（PM / toB / toC），不谈代码结构
- 互补于 A 支线的'🔴 优化建议'（那 22 条偏代码/目录/架构）
- 顺序已按严重度排 🔴 → 🟡 → 🟢，可从上往下推
