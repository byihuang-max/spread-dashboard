# 研报因子蒸馏（Factor Forge）实现与接入

> 把研报蒸馏成可观测因子的独立模块，已接入 GAMT 主看板工具栏（admin-only）。

---

## 核心理念

研报里的"观点"≠"因子"。
- "我们看好半导体复苏" = 观点（不可观测，没用）
- 真因子 = 把观点翻译成可跟踪的信号 + 成立条件 + 证伪条件

每条因子必须能回答：每天/每周看哪个数据，看到什么说明观点在兑现/证伪？

---

## 双 LLM 分工（刻意分开）

| 角色 | 职责 | 看到的上下文 |
|------|------|--------------|
| 蒸馏器 distiller | 忠于原文，把观点翻译成可观测信号 | 只有研报正文 |
| 看板顾问 advisor | 判断因子对 GAMT 系统有什么用 | GAMT 模块清单 + 因子 |

分开的原因：蒸馏要忠于原文、顾问要结合看板，混在一起会互相污染。
**看板顾问是正反馈闭环的来源**——它读完因子后告诉你该挂哪个模块、建议加什么观测项、跟现有因子是印证还是矛盾。

---

## 因子数据模型

```
factor_id, source, layer(macro/industry/stock),
factor_name, direction(看多/看空/中性),
logic_chain, observable(最关键), trigger, invalidation,
horizon(短/中/长), confidence(人工1-5星),
linked_industry, linked_tickers(行业→个股索引),
dashboard_hook(顾问产出), status(候选/已采纳/已证伪/观察中)
```

行业→个股索引靠 linked_industry + linked_tickers 两字段，攒到基数后按行业聚合。

---

## 文件结构

```
factor-forge/
├── extract_pdf.py  PDF抽取（pdfplumber→pymupdf→pdfminer 三引擎兜底）
├── forge.py        蒸馏器+看板顾问（复用 smart-notes llm_client.call_claude）
├── store.py        因子库（data/factors.json，行业索引）
├── ingest.py       端到端CLI（PDF→蒸馏→入库）
├── server.py       独立API（备用，已合并进主服务）
└── index.html      前端（研报摄入/因子库/行业索引 三栏）
```

---

## 接入 GAMT 主看板的标准流程（复用经验）

**关键架构决策**：动态模块（依赖后端 API）不能像静态页那样直接 iframe 嵌入。
若前端写死 `localhost:7788`，手机通过 tunnel 访问时 localhost 指向手机自己，连不到 Mac，功能全废。
**正解：API 合并进主服务 9876，前端用相对路径（API=''），同源 + tunnel 自动透传。**

### 后端：在 server/refresh_server.py 加路由
- do_GET 加 `/api/factors`（catchall 之前）
- do_POST 加 `/api/forge` + `/api/factors`（catchall else 之前）
- 新增 do_PATCH / do_DELETE 方法
- handler 方法用 `_ff_` 前缀，懒加载 factor-forge 目录到 sys.path

### 前端：index.html 4 处改动（与景气度股票池完全一致）
1. nav-item：`id="navFactorForge" data-module="factor_forge" style="display:none"`
2. module-page：`id="page-factor_forge"` 内嵌 iframe
3. titles 映射 + MODULE_PAGE_MAP 各加一条
4. showApp() 里加 admin-only 显示逻辑

### 收尾
- bump SW 缓存版本（static/sw.js: gamt-vN）
- factor-forge/data/ 加 .gitignore（本地产物不入库）
- git push，webhook 自动重启后端

---

## 踩坑记录

- **Python 3.14 移除了 cgi 模块**：multipart 解析改用标准库 email 模块，或手工 split boundary
- **patch 大块插入易吞掉相邻方法**：插入后必须 py_compile 验证，这次 log_message 被误吞过
- **homebrew python 是 externally-managed**：pip 装包要加 `--break-system-packages`
- **LSP import 报错是误报**：运行时 sys.path 注入了真实路径

---

## 待办

- llm_client.py 第257行 Kimi API key 硬编码，建议挪到环境变量
- PDF 扫描件（无文字层）三引擎都抽不出，会提示粘贴正文——正常兜底非bug

---

*Created: 2026-06-07*
