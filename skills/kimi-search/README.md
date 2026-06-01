# kimi-search — Kimi 联网搜索工具

## 概述

基于 Moonshot Kimi API 的联网搜索封装。Kimi 的核心优势是能联网搜索并整合最新信息，适合验证数据口径、政策变化、市场事件等场景。

## 文件结构

```
skills/kimi-search/
├── SKILL.md           # AI 触发说明
├── README.md          # 本文件
├── kimi_search.py     # 核心搜索模块（可 import / 可命令行）
└── config/
    └── api_keys.json  # API 密钥
```

## API

### `search(query, model, temperature, timeout, max_retries) -> str`

单条联网搜索。Kimi 会自动判断是否需要搜索互联网。

### `search_batch(queries, interval, verbose) -> list`

批量搜索，自动间隔 1.5s 避免频率限制。

## 技术实现

Kimi 联网搜索的机制是 OpenAI 兼容的 tool_calls：
1. 请求带 `$web_search` 工具声明
2. Kimi 判断需要搜索时返回 `tool_calls` + 搜索摘要
3. 第二轮请求把搜索结果喂回去，得到最终整合回答

## 被引用

- `skills/stock-monitor/generate_merger_report.py`（并购线索验证）
- `micro_flow/crowding/`（拥挤度数据口径验证）

## 密钥

`config/api_keys.json` 里的 `kimi_api_key`，来自 Moonshot 开放平台。
