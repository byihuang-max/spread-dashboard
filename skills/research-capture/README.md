# research-capture

投研材料捕获器 · GAMT Skills

把我（Roni）看到的研报、券商观点、投研心得、长文、链接，一键入库到 Smart Notes 知识库，并做去重、迭代识别、投研式结构化拆解。

## 核心定位

- **不是** 可视化链接收藏夹
- **是** Smart Notes 上游的"信息摄取层"
- 入口成本极低：一句"这篇收一下"或"<链接> 收"

## 使用方法

### 1. 显式触发（最常用）

在飞书/对话中：

```text
https://xxx  收
```

或：

```text
这篇收一下：<链接>
```

或贴一大段文字 + `归档`。

### 2. CLI 直接跑

```bash
# URL 入库
python3 scripts/capture_research.py --url "https://xxx" --save

# 文本入库
echo "正文..." | python3 scripts/capture_research.py --text - --save

# 预览不落盘
python3 scripts/capture_research.py --url "https://xxx" --dry

# 指定来源元数据
python3 scripts/capture_research.py --url "https://xxx" --source "中信证券" --author "张三" --save
```

### 3. 半触发（分析但不存）

- `看一下` → 只做摘要拆解，不入库
- `暂存` → 进 archive，不升到 Smart Notes（MVP 暂未实现，走 `--dry` 替代）

## 工作流

```
输入（URL/文本/PDF）
    ↓
extract_content.py     抓正文 + 清洗
    ↓
distill.py             调 Claude 做投研拆解（标题/观点/证据/资产/风险）
    ↓
生成 Markdown 笔记
    ↓
save_note.py           接 Smart Notes 管线（分类 + 迭代 + 落盘）
    ↓
飞书回执
```

## 输出结构

每条笔记自动包含：

- 标题 / 来源 / 作者 / 日期 / 原文链接
- 一句话结论
- 3-5 条核心观点
- 关键证据 / 数据
- 影响资产 / 行业 / 策略
- 新信息密度（高/中/低）
- 可交易性（高/中/低）
- 风险 / 反方观点

最终按 Smart Notes 管线归到：

- `research/reports`（研报观点）
- `research/factors`（因子/策略研究）
- `research/strategy`（策略设计）
- `research/narrative`（宏观叙事）
- `conversations`（对话讨论）
- `concepts`（基础概念）

## 文件结构

```text
research-capture/
├── README.md
├── SKILL.md                   # AI 触发文档
├── scripts/
│   ├── capture_research.py    # 主入口
│   ├── extract_content.py     # URL → 正文抽取
│   └── distill.py             # 正文 → 投研结构化 Markdown
└── references/
    └── note_schema.md         # 字段定义
```

## 依赖

```bash
pip3 install --user --break-system-packages requests beautifulsoup4 certifi readability-lxml
```

已有：`requests` / `beautifulsoup4` / `certifi`  
推荐：`readability-lxml`（正文抽取显著更准）

## 与 Smart Notes 管线的关系

本 skill 只做"摄取+拆解"，**分类、迭代、落盘全部交给 Smart Notes 管线**：

```bash
~/Desktop/gamt-dashboard/smart-notes/intelligence/save_note.py
```

不要在本 skill 里重造分类轮子。

## 红线

- 不伪造抓不到的内容
- 不在主聊天默认自动入库
- 不把脚本放 workspace
- 写文件后立刻验证落盘

## 上线时间

2026-05-07 by 雷军
