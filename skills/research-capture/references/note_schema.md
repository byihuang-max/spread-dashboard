# 投研笔记字段 Schema

capture_research 生成的 Markdown 笔记统一结构，便于 Smart Notes 管线识别、去重、迭代。

## 标准 Frontmatter

```yaml
---
source: 中信证券 / 天风 / 微信公众号 / WSJ / 雪球 / 路透
author: 张三
date: 2026-05-07
url: https://xxx
captured_at: 2026-05-07 19:30
novelty: 高
tradability: 中
theme: research/narrative
---
```

## 正文结构

```markdown
# <标题>

**一句话结论：** <一行 50 字内>

## 核心观点

- 观点 1
- 观点 2
- 观点 3

## 关键证据 / 数据

- 数据点 1（带来源）
- 数据点 2
- 关键图表描述

## 影响资产 / 策略

- **A 股：** 受益板块 / 回避板块
- **债市：** 利率方向
- **商品：** 具体品种
- **FOF 策略含义：** 对量化股票/强势股/CTA/转债指增/套利各自的含义

## 风险 / 反方观点

- 风险 1
- 反方观点 1

## 原文参考

- 链接：<url>
- 本地存档：<archive_path>（如有）
```

## 字段含义

| 字段 | 含义 | 取值 |
|------|------|------|
| `source` | 发布机构/媒体 | 自由文本 |
| `author` | 作者/分析师 | 自由文本 |
| `date` | 原文发布日期 | YYYY-MM-DD |
| `url` | 原文链接 | http(s):// |
| `captured_at` | 入库时间 | YYYY-MM-DD HH:MM |
| `novelty` | 新信息密度 | 高 / 中 / 低 |
| `tradability` | 可交易性 | 高 / 中 / 低 |
| `theme` | Smart Notes 分类提示 | research/reports / research/factors / research/strategy / research/narrative / conversations / concepts |

## 分类提示词

- `research/reports` — 券商研报、机构观点
- `research/factors` — 因子/量化方法
- `research/strategy` — 策略设计/回测
- `research/narrative` — 宏观叙事、主题交易
- `conversations` — 讨论、对话沉淀
- `concepts` — 基础概念、框架、术语
