# Smart Notes 完整落地链路全景

**日期**: 2026-05-05
**版本**: v2
**迭代自**: `notes/engineering/Smart_Notes架构改造_动态加载方案.md`
**标签**: #smart-notes #工作流 #架构 #分类管线 #post-commit #embedding

---

## 摘要

梳理从 Roni 触发存笔记、经智能分类管线写入 Markdown、commit 同步腾讯云、到前端 rglob 扫盘显示的完整链路与关键设计决策。

## 相比上一版

- 范围从单点API改造扩展为存笔记→分类→同步→前端显示的完整链路
- 新增L2 Claude标题/标签生成 + L1 BGE embedding融合分类机制
- 新增note_vectors.json向量库与迭代检测
- 新增post-commit hook自动rsync部署到远程服务器

## 正文

# Smart Notes 完整落地链路（存笔记→归类→同步→前端显示）

本笔记完整梳理"Roni 说存笔记"之后从触发到前端可见的全链路机制，作为长期参考。

## 一、触发入口（等价触发词）

以下说法 **完全等价**，都会触发同一条管线：

- 存笔记：xxx
- 存到 smart notes：xxx
- 保存到 Smart Notes
- 归档到 smart notes
- 记一下（上下文是完整段落时）

加 "**预览一下**" 或 "**dry run**" → 走 `--dry` 模式，只输出分类结果，不落地。

## 二、核心执行链路

```
Roni 说"存笔记：xxx"
      │
      ▼
Kiro 调 save_note.py（智能分类管线）
      │
      ├─ 【L2 Claude】生成标题 / 摘要 / 标签 / category_hint
      ├─ 【L1 本地 BGE】算 768 维 embedding，对 10 个类别中心算余弦
      ├─ 【融合决策】Claude hint + embedding 相似度，决定归哪一类
      ├─ 【迭代检测】和 note_vectors.json 里 100 篇历史笔记比，判断是否 v+1
      │
      ▼
写 .md 到对应目录
  concepts/ | conversations/ | decisions/ | sessions/
  notes/research/factors | notes/research/strategy | notes/research/narrative
  notes/engineering/ | notes/reports/ | notes/emerging_markets/
      │
      ▼
更新 note_vectors.json（增量加向量）
      │
      ▼
git add（但不自动 commit，留给人工选时机）
      │
      ▼
===（以下是 commit 时才触发）===
      │
      ▼
post-commit hook（.git/hooks/post-commit）
      │
      ├─ rsync → ubuntu@111.229.129.146:/home/ubuntu/gamt-dashboard/
      ├─ 排除 .git / __pycache__ / venv / _cache
      └─ sudo systemctl restart gamt（后端服务重启）
      │
      ▼
用户打开 dashboard.gamtfof.com/smart-notes/
      │
      ▼
前端 fetch('/api/notes')
      │
      ▼
refresh_server.py 的 _serve_notes_list()
  rglob 扫 smart-notes/ 整个目录
  排除 intelligence/ / README.md / AUDIT.md
  返回 97+ 篇笔记 JSON
      │
      ▼
前端渲染分类树 + 笔记内容
```

## 三、三档决策规则

### 归类档位
| embedding 相似度 | 决策 | 行为 |
|---|---|---|
| ≥ 0.60 | auto | 直接落位到 top 类 |
| 0.50-0.60 | confirm | Claude 读原文看全部 10 类仲裁 |
| < 0.50 | need_confirm | 返回灰区，我问 Roni 要不要新建类 |

**防分类膨胀：** 系统不会自动建新类，LLM 返回 `__NEW__:xxx` 时必须人工确认。

### 迭代档位
| 相似度 | 标题 2-gram 重叠 | 决策 |
|---|---|---|
| ≥ 0.82 | ≥ 0.40 | strong：直接 v+1 |
| ≥ 0.72 | 任意 | weak：Claude 二次确认，high/medium 信心才升版 |
| < 0.72 | — | 独立新笔记 |

## 四、关键时序

| 阶段 | 耗时 | 备注 |
|---|---|---|
| Claude 元数据生成 | 2-4s | 一次 Opus 4.7 调用 |
| 本地 embedding | <0.3s | BGE-base-zh 算 768 维 |
| 灰区仲裁（可选） | 2-3s | 另一次 Claude 调用 |
| 迭代 diff（可选） | 2-4s | 又一次 Claude 调用 |
| 写文件 + git add | <0.5s | 本地 IO |
| commit + rsync + 后端重启 | 2-3s | post-commit hook |
| **Commit 到前端可见总耗时** | **10-15s** | 一般场景 |

成本：约 ¥0.02-0.05/篇（最多 3 次 Claude 调用）

## 五、关键设计决策（沉淀经验）

### 1. 本地 BGE + 云端 Claude 混合
- Claude 没 embedding 能力，相似度匹配用本地模型
- 生成类任务（标题/摘要/diff）交给 Claude
- 分工后：快 + 聪明 + 便宜

### 2. Commit 是"上线"的动作，不是 save_note
- save_note 只写文件 + git add，不自动 commit
- 让 Roni 控制什么时候"上线"，避免碎片化 commit
- commit 后 post-commit hook 自动同步腾讯云，dashboard 立刻生效

### 3. 前端无缓存，pull-on-demand
- 不是定时任务，不是 push 架构
- 用户每次打开页面都实时 rglob 扫磁盘
- .md 文件一旦到位，刷新就能看到

### 4. 只推 Gitee 作为主链，GitHub 降级为月度备份
- 日常 commit 后 post-commit 同步腾讯云（dashboard 立刻生效）
- Gitee 用作中心仓库，不需要梯子
- GitHub 每月 1 号 09:00 腾讯云 cron 推飞书提醒，手动跑 `push_github.sh`

### 5. 前端 API 扫描范围是整个 smart-notes/
- 2026-05-05 修复：原来只扫 notes/ 子目录，漏掉 43 篇
- 现在扫全目录，排除 intelligence/（算法代码）+ README.md + AUDIT.md
- 分类按顶层目录名决定（notes/xxx 这类深层保留二级）

## 六、核心文件清单

```
smart-notes/
├── intelligence/            # 算法层（不作为笔记暴露给前端）
│   ├── save_note.py         # 入口脚本
│   ├── note_pipeline.py     # ingest() 核心编排
│   ├── llm_client.py        # Claude API 封装
│   ├── notes_intel.py       # BGE embedding + 相似度
│   ├── note_vectors.json    # 向量库
│   └── category_centers.json  # 10 个类别中心
├── concepts/
├── conversations/
├── decisions/
├── sessions/
└── notes/
    ├── engineering/
    ├── research/{factors,strategy,narrative}/
    ├── reports/
    └── emerging_markets/
```

后端：`server/refresh_server.py` 的 `_serve_notes_list()`（commit `bfc875b1` 后扫全目录）

前端：`smart-notes/index.html`，加载后 `fetch('/api/notes')` 拿全量

## 七、一句话总结

> Roni 说"存笔记"，10-15 秒后 dashboard 上可见。
> 中间是：Claude 加工元数据 → BGE 决定归类 → 写 .md → git add → (commit) → rsync 腾讯云 → 后端重启 → 前端实时扫磁盘返回。
