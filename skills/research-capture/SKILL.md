---
name: research-capture
description: 投研材料捕获器。把链接/PDF/长文/心得等投研材料抽取正文、做投研式拆解、去重、落入 Smart Notes 知识库。触发词：收、收一下、存研报、存笔记、归档、归档这篇、保存到 Smart Notes、研报归档、research inbox。当 Roni 在飞书/对话里发送一个 URL/长文并显式表达这几个意图之一时使用；在专用 research inbox 入口中，对投研类链接/文件/长文默认使用。不用于：普通聊天、日常备忘录、非投研内容归档。
---

# research-capture

投研材料捕获器。定位不是可视化收藏夹，而是 Smart Notes 上游的"信息摄取层"。

## 触发

**显式触发（主聊天默认）**：

- `收` / `收一下` / `这篇收一下`
- `存研报` / `存笔记` / `归档` / `归档这篇`
- `保存到 Smart Notes` / `research inbox`

**隐式触发（仅在专用 research inbox 入口）**：

- 收到研报类 URL、PDF、长文本（>300 字且含投研关键词）

**半触发**：

- `看一下` / `只摘要` → 分析，不入库
- `暂存` → 进 inbox，不升级到 Smart Notes

## 工作流

### Step 1 · 识别输入类型

| 类型 | 识别信号 | 处理脚本 |
|------|---------|---------|
| URL | http(s):// 开头 | `scripts/capture_research.py --url <url>` |
| 飞书文档 | feishu.cn/docx 或 wiki 链接 | 优先调 feishu-doc / feishu-wiki skill |
| 长文本 | stdin 或消息体 >200 字 | `scripts/capture_research.py --text -` |
| PDF | 本地路径或附件 | 先用 pdfplumber 抽文，再走 `--text` 分支 |
| 截图/图片 | 需要 OCR | 不在 MVP 范围，要求 Roni 贴正文 |
| 混合消息 | URL + 用户附言 | 抓 URL + 把附言作为"用户注解"加进元数据 |

### Step 2 · 抽取正文

`scripts/capture_research.py` 默认用 requests + BeautifulSoup + readability 抽取主正文。

失败兜底：
- 状态码非 200 / 超时 / 反爬 → 返回 `extract_error`，不伪造内容
- 抽不到或抽出<200 字 → 请求 Roni 贴正文

### Step 3 · 投研式拆解（LLM 结构化）

调 `call_claude` 生成结构化 markdown，字段见 `references/note_schema.md`。

核心字段：

- `title` / `source` / `author` / `date` / `url`
- `one_line`（一句话结论）
- `core_views`（3-5 条）
- `key_evidence`（数据/图表/案例）
- `affected`（影响资产/行业/策略）
- `theme`（research/narrative、research/factors 等分类提示）
- `novelty`（高/中/低）
- `tradability`（高/中/低）
- `risks`
- `raw_url` / `raw_path`

### Step 4 · 调 Smart Notes 管线

不要自己写分类逻辑，一律走现成的：

```bash
cat <生成的 markdown> | python3 ~/Desktop/gamt-dashboard/smart-notes/intelligence/save_note.py
```

管线会自动做：embedding 分类、灰区仲裁、迭代识别、落文件、更新 BUILTIN_NOTES。

### Step 5 · 回执

飞书回复格式：

```text
● 已收录
标题：<title>
类型：<研报/文章/心得/数据/观点>
分类：<smart-notes 类别>
新信息密度：<高/中/低>
可交易性：<高/中/低>
路径：<smart-notes 落盘路径>
备注：<如果是迭代，写 "v2 迭代原笔记 xxx">
```

抽取失败：

```text
○ 未入库
原因：<原文无法抓取 / 正文<200字 / 反爬>
建议：把原文贴到对话里，我再入库
```

内容不值得入库：

```text
○ 建议暂存
原因：<信息密度低 / 与已有笔记高度重复>
是否强制收录？(回复"强制收录"会覆盖判断)
```

## 使用方式

### 主入口（Roni 在飞书/对话中）

单条命令：

```bash
# URL
python3 ~/Desktop/gamt-dashboard/skills/research-capture/scripts/capture_research.py --url "https://xxx" --save

# 纯文本（stdin）
echo "正文..." | python3 ~/Desktop/gamt-dashboard/skills/research-capture/scripts/capture_research.py --text - --save

# 预览不落盘
python3 ~/Desktop/gamt-dashboard/skills/research-capture/scripts/capture_research.py --url "https://xxx" --dry
```

`--save` 会调 Smart Notes 管线；不加 `--save` 只做抽取+拆解。

### 约束（必读）

- 主聊天里没显式触发词，不要自动调用
- 抽取失败不编造内容
- 所有新 `.py` 只能放在 `~/Desktop/gamt-dashboard/skills/` 下，**不要**写进 workspace
- 写完文件立刻 `ls -la` + `git status` 验证落盘

## 文件结构

```text
~/Desktop/gamt-dashboard/skills/research-capture/
├── README.md                  # 人看的使用文档
├── SKILL.md                   # 本文件（AI 触发文档）
├── scripts/
│   ├── capture_research.py    # 主入口
│   ├── extract_content.py     # URL/HTML 抽正文
│   └── distill.py             # 调 Claude 做投研拆解
└── references/
    └── note_schema.md         # 笔记字段 schema
```

## 依赖

已有：`requests`, `certifi`, `beautifulsoup4`  
建议装：`readability-lxml`（正文抽取更准）

## 红线

- ⛔ 不在 workspace 里建 `.py`
- ⛔ 不伪造抓不到的研报内容
- ⛔ 不在主聊天默认自动入库
- ⛔ 不跳过 Smart Notes 管线自己写分类
