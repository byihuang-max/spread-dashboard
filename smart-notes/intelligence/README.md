# Smart Notes 智能分类系统

本地 embedding + Claude LLM + 规则决策，实现笔记自动归类 + 版本迭代识别。

## 架构

```
intelligence/
├── notes_intel.py          # 【L1】扫描 / 建索引 / embedding 分类 / 迭代检测
├── llm_client.py           # 【L2】Claude API 封装（标题/摘要/标签/仲裁/diff）
├── note_pipeline.py        # 【核心】ingest() 串起所有步骤
├── save_note.py            # 【入口】CLI + 飞书命令入口
├── note_vectors.json       # 笔记向量库（86 篇）
├── category_centers.json   # 9 个类别中心向量
└── README.md               # 本文件
```

## 模型分工

| 阶段 | 工具 | 作用 |
|------|------|------|
| 向量化 | 本地 BGE-base-zh-v1.5 | 笔记 → 768 维向量 |
| 相似度匹配 | numpy 余弦 | 归类 + 迭代候选 |
| 标题/摘要/标签 | Claude Opus 4.7 | 原始文本 → 结构化元数据 |
| 灰区仲裁 | Claude Opus 4.7 | embedding 信心不足时接管 |
| 迭代 diff | Claude Opus 4.7 | v1 vs v2 变化总结 |

## 用法

### 存一篇笔记

```bash
cd ~/Desktop/gamt-dashboard/smart-notes/intelligence

# 从 stdin 读
echo "你的笔记内容..." | python3 save_note.py

# 或直接传参
python3 save_note.py "你的笔记内容..."

# 预览不写入
python3 save_note.py --dry "..."

# 只要 JSON 输出（给程序调用）
python3 save_note.py --json "..."
```

### 飞书/对话入口（我的识别触发词）

Roni 说「**存笔记：**xxx」或「**存到 smart notes：**xxx」→ 我会自动跑 save_note.py。

加「**预览一下**」或「**dry run**」→ 走 `--dry` 模式。

### 重建索引

笔记批量变动后跑：
```bash
python3 notes_intel.py build           # 增量（复用 content_hash 命中的）
python3 notes_intel.py build --force   # 全量重算
```

## 决策规则

### 归类（3 档）

| embedding 相似度 | 决策 | 行为 |
|------|------|------|
| ≥ 0.60 | `auto` | 自动落位到 top 类 |
| 0.50~0.60 | `confirm` | Claude 读原文仲裁（结合全部 10 个类别，不只 top3） |
| < 0.50 | → LLM 兜底 | LLM hint 可用则用；否则返回 need_confirm |

### 迭代（3 档）

| 相似度 | 标题 2-gram 重叠 | 决策 |
|--------|----------|------|
| ≥ 0.82 | ≥ 0.40 | `strong`：Claude 生成 diff，文件自动升 v+1 |
| ≥ 0.72 | 任意 | `weak`：Claude 二次确认，confidence=high/medium 才升版 |
| 其他 | — | `none`：当独立新笔记 |

### 防分类膨胀

- **不会自动创建新类别**：LLM 返回 `__NEW__:xxx` 时 pipeline 返回 `need_confirm`，我会问 Roni
- 灰区仲裁 prompt 强调"优先从现有类别选，包括空类（如 emerging_markets）"

## 10 个类别

| 目录 | 定位 |
|------|------|
| `concepts/` | 概念定义 |
| `conversations/` | 研究对话过程 |
| `decisions/` | 最终决策 |
| `sessions/` | 阶段共识/工作流 |
| `notes/research/factors/` | 因子研究 |
| `notes/research/strategy/` | 策略研究 |
| `notes/research/narrative/` | 叙事/主题研究 |
| `notes/engineering/` | 工程/架构/部署 |
| `notes/reports/` | 外部研报 |
| `notes/emerging_markets/` | 新兴市场 |

## 输出笔记格式

```markdown
# 标题（Claude 生成）

**日期**: 2026-05-05
**版本**: v2（仅迭代时）
**迭代自**: `path/to/v1.md`（仅迭代时）
**标签**: #tag1 #tag2 #tag3

---

## 摘要
（Claude 一句话）

## 相比上一版（仅迭代时）
- bullet 1
- bullet 2

## 正文
（原始输入）
```

## 测试样本

| 场景 | 结果 |
|------|------|
| 巴西金融市场 | ✅ Claude 仲裁落进空目录 `emerging_markets`（embedding 灰区 0.56） |
| 三端对齐新流程 | ✅ auto `engineering` + strong 迭代 v2 |
| 强势股日报 v1.6 | ✅ auto `conversations` + weak→Claude 高信心确认 v2（diff 自动生成） |

## 成本

- Embedding：本地 BGE，零成本
- Claude 调用：约 3 次/笔记（元数据 + 可能的灰区仲裁 + 可能的迭代 diff），中转 API 大概 ¥0.02~0.05/篇

## 依赖安装

```bash
pip3 install --user --break-system-packages \
  sentence-transformers modelscope numpy requests certifi
```

Homebrew Python 需要 `--user --break-system-packages`（不污染系统，装到 `~/Library/Python/3.14/`）。

首次用 ModelScope 下载 BGE 模型（~390MB，国内 1-2 分钟）：
```bash
python3 -c "from modelscope import snapshot_download; snapshot_download('AI-ModelScope/bge-base-zh-v1.5')"
```
