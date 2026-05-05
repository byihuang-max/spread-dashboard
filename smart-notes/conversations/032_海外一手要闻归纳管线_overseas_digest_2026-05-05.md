# 海外一手要闻归纳管线（overseas_digest）

日期：2026-05-05
类型：对话 / 产品与工程设计落地
相关模块：GAMT 看板 → 宏观与流动性 → 反脆弱 / Murmur 交易 → 海外一手要闻

---

## 背景与需求演进

Roni 提出新想法：他的 QQ 邮箱（`854523290@qq.com`）订阅了一个上游服务（`hszxboss@qq.com`），对方会把彭博 / 路透 / 华尔街日报 等一手外媒自动翻译成中文并转发到邮箱。

这些内容是对现有中文财经新闻舆情池（`narrative_monitor` 基于 Tushare 三源）的天然补充——**一手 / 准一手 + 海外视角**。

### 需求层层明确（约 15 轮讨论）

1. **是否可以把邮件作为舆情源？** → 可以，且应独立成"海外舆情池"，不与国内叙事混池打分
2. **现有算法能否复用？** → 骨架可复用（固定叙事 + LLM 动态发现），但去重和关键词库需升级
3. **频率？** → Roni 明确"两次就够，不搞高截面"，与 `narrative_monitor` 同频 08:30 / 20:30
4. **核心诉求升级** → 不要搬原文，要"今天最重要的信息是什么 + 一两句话归纳"
5. **数量** → 一开始 Top 3，后改 Top 10 但动态数量（宁缺毋滥）
6. **LLM 升级** → 从 GPT-5.4 全部切到 Claude Opus 4.7（连带 `narrative_monitor` 一起切）
7. **部署** → 本地 / Gitee / 腾讯云三端对齐

---

## 最终落地架构

```
QQ邮箱 IMAP (854523290@qq.com)
       ↓ 过滤 FROM=hszxboss@qq.com
news_email_fetcher.py（抓取 + 入库 + 三级去重）
       ↓ 读 db
overseas_digest.py
       ↓ 规则筛选 Top 30（来源权重 + 关键词权重）
       ↓ Claude Opus 4.7 精筛（最多 Top 10，动态数量，宁缺毋滥）
       ↓
       ├─→ 飞书卡片推送 Roni
       ├─→ overseas_digest_latest.json（看板数据源）
       └─→ 自动触发 antifragile/render_html.py 重渲染看板
```

---

## 关键决策

### 1. 去重策略（三级）
- 一级：URL 完全匹配（WSJ/Reuters 链接带 hash 天然唯一）
- 二级：去 `XXX：` 源前缀后标题匹配（防同源多转发）
- 三级：摘要前 50 字符 hash（兜底）

### 2. LLM 全面切换到 Opus 4.7
- 原因：Roni 明确"原有的 GPT 都换成 Opus 4.7"
- `narrative_monitor.py` 同步切换，备份旧版为 `narrative_monitor_v2_gpt_backup.py`
- 协议差异：OpenAI `/v1/chat/completions` → Anthropic `/v1/messages`（system 独立字段，`max_tokens` 必填）
- API Key：`aicanapi-47`（sk-tl1Z...）
- 成本：一次请求约 ¥0.15，月成本 ¥10 以内，贵但质量好 5-10 倍

### 3. Top 3 → Top 10 动态数量
- Roni 反馈："Top 3 太少"
- 我的建议：动态上限 10，允许 LLM 自判宁缺毋滥（方案 A）
- 候选池从 15 → 30
- 实测：12 条新闻 → LLM 选出 9 条（没硬凑 10）

### 4. 自动触发看板渲染（修复边界 bug）
- 发现的问题：腾讯云 08:20 update_all 跑 render_html 时，`overseas_digest_latest.json` 还没生成（它 08:30 才跑），导致看板空白直到下次 update_all
- 修复：`overseas_digest.py` 跑完后 subprocess 调 `antifragile/render_html.py` 立刻重渲染

### 5. 配置分离与安全
- `email_config.json`（授权码 + LLM Key）放本地，**gitignore 掉**
- 两端独立维护：本地 Mac + 腾讯云各自有一份
- 数据库 `email_news_db.json` 也 gitignore，两端独立累积

---

## 数据规模实测

- 历史总量：`hszxboss@qq.com` 累计 3208 封
- 日频（抽样 4/24-4/30）：
  - 周末：10-20 条
  - 工作日：30-60 条（峰值 4/30 的 63 条）
- 12h 窗口典型值：10-25 条 → 规则筛 12-30 候选 → LLM 选 5-10 条

---

## 涉及文件

### 新增
- `daily_report/meme交易/news_email_fetcher.py`（IMAP 增量抓取 + 入库）
- `daily_report/meme交易/overseas_digest.py`（规则筛 + Opus 精筛 + 飞书 + 触发渲染）
- `daily_report/meme交易/email_config.json`（gitignored）

### 修改
- `daily_report/meme交易/narrative_monitor.py`（LLM 切 Opus 4.7）
- `macro/meme/antifragile/render_html.py`（新增"海外一手要闻"区块加载逻辑）
- `server/module_registry.py`（注册 `overseas_digest` + 更新 `macro_meme` 聚合）
- `.gitignore`（加 email_config.json + cache 文件）

### 备份
- `daily_report/meme交易/narrative_monitor_v2_gpt_backup.py`（原 GPT 版留档）

---

## Cron（腾讯云）
```cron
# 海外要闻归纳 - 工作日 08:30 / 20:30
30 8 * * 1-5 cd /home/ubuntu/gamt-dashboard/daily_report/meme交易 && ./venv/python3 overseas_digest.py >>/tmp/overseas_digest.log 2>&1
30 20 * * 1-5 cd /home/ubuntu/gamt-dashboard/daily_report/meme交易 && ./venv/python3 overseas_digest.py >>/tmp/overseas_digest.log 2>&1
```
日志：`/tmp/overseas_digest.log`

---

## 合规与展示原则

- 不在公开页面展示彭博 / 路透 / WSJ 原文全文
- 内部 cache 保留邮件摘要和链接（供 LLM 读取）
- 看板展示二次加工后的**主题 + 风险等级 + 一句话归纳 + 受影响资产**
- 未来 toC 时此模块**不可暴露为"免费财经新闻墙"**，只能暴露加工后的 FOF 决策信号

---

## 未办

- [ ] GitHub 推送（代理没开，Gitee 已经是主链，GitHub 是备份）
- [ ] 观察一周真实跑出来的质量，再决定是否加英文关键词库 / 调整规则权重
- [ ] 可选：加入 Murmur 交易专用的"主题同向 vs 背离"检测（新闻说 risk-off 但 DXY/纳指没跌 → 疑似假信号）

---

## 教训与经验

1. **需求澄清比实现重要**：一开始要写"改造设计稿"，Roni 说不靠谱，只要归档现状。后来再聊才明确真正诉求是"要闻归纳"。归档类笔记不塞改进建议。
2. **cron 调度顺序一定要想清楚**：新模块接入老链路要过一遍依赖链，不能只看自己跑通。
3. **三端对齐时 rebase 冲突常见**：腾讯云 cron 每天自己 commit 数据文件。处理方式：`git pull --no-rebase -X theirs` 让远端数据胜出。
4. **IMAP FETCH 解析结构复杂**：`RFC822 INTERNALDATE` 一起取时，response 结构是 `[(meta, body), INTERNALDATE_line]`，不能按单 tuple 假设；日期格式可能是 `1-May-2026` 或 `01-May-2026`，要两种都试。
5. **.gitignore 路径用 glob 匹配中文目录**：`daily_report/meme交易/email_config.json` 要写完整路径，`**/email_config.json` 也可但不如显式。
6. **Claude Opus 4.7 对 FOF 语境的理解明显强于 GPT-5.4**：实测中美摩擦、地缘、军工等叙事的抓取都更精准。
