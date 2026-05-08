# Smart Notes 前端自动同步机制设计

**日期**: 2026-05-07
**版本**: v2
**迭代自**: `notes/engineering/Smart_Notes架构改造_动态加载方案.md`
**标签**: #Smart Notes #前端同步 #自动化管线 #容错设计 #模块隔离 #BUILTIN_NOTES

---

## 摘要

为 Smart Notes 管线新增 Step 8，通过独立模块 update_builtin_notes.py 在笔记写入后自动同步前端 BUILTIN_NOTES 数组，采用容错不阻塞、幂等去重、模块隔离的设计原则。

## 相比上一版

- 旧版提出从硬编码改为动态API加载的方案；新版放弃API方案，改为在pipeline写入md后直接修改index.html中的BUILTIN_NOTES数组实现同步
- 新版新增独立模块 update_builtin_notes.py，并将其集成到 note_pipeline.ingest() 作为 Step 8
- 新版强调容错不阻塞、幂等、模块隔离等设计原则
- 新版补充了完整的端到端判断流程图（从用户触发到分类决策）

## 正文

# Smart Notes 前端自动同步机制（2026-05-07）

## 背景

之前 Smart Notes 管线有个断点：`save_note.py` 写完 `.md` 文件后不会自动更新前端 `index.html` 里的 `BUILTIN_NOTES` 数组。结果每次存笔记，前端都看不到新内容，必须手动编辑 HTML 塞一条进去。

这次把这一步也自动化了。

## 架构改动

### 新增 `smart-notes/intelligence/update_builtin_notes.py`

独立模块，职责单一：
- 读 `.md` 文件 → 提取标题/内容
- 解析 `index.html` 的 `BUILTIN_NOTES` 数组
- 按 path 去重：已存在则更新，否则追加
- 写回 `index.html`

可以独立调用：`python3 update_builtin_notes.py <path> <category>`

### 修改 `note_pipeline.py` 的 `ingest()` 函数

在 Step 7（写入 md）之后新增 Step 8（同步前端）：

```python
# Step 8: 同步前端 BUILTIN_NOTES（容错，不影响主流程）
try:
    from update_builtin_notes import update_builtin_notes
    if update_builtin_notes(str(target_file.relative_to(ROOT)), final_category):
        decisions.append("✓ 已同步到前端 BUILTIN_NOTES")
    else:
        decisions.append("⚠️  前端 BUILTIN_NOTES 同步失败（不影响笔记本身）")
except Exception as e:
    decisions.append(f"⚠️  前端同步异常：{type(e).__name__}: {e}")
```

## 设计原则

1. **容错不阻塞**：同步失败只记日志，不影响笔记本身的写入
2. **幂等**：按 path 去重，重复调用不会产生重复记录
3. **模块隔离**：独立文件，方便独立测试和替换
4. **决策日志可见**：成功/失败都记录在 `decisions` 里，调用方能看到

## 判断流程

```
用户触发（飞书"收" / CLI --save）
    ↓
capture_research.py（skill 入口）
    ↓
extract_content.py 抓正文
    ↓
distill.py 投研式拆解
    ↓
save_note.py / note_pipeline.ingest()
    ├─ Step 1: Claude 生成元数据（标题/摘要/标签/category_hint）
    ├─ Step 2: embedding 分类（recommended_category）
    ├─ Step 3: 归类决策
    │   ├─ LLM + embedding 一致 → 用它
    │   ├─ 灰区（0.50~0.60）→ Claude 仲裁
    │   └─ < 0.50 或 __NEW__ → 返回 need_confirm
    ├─ Step 4: 迭代决策
    │   ├─ 相似度 ≥ 0.82 + 标题 2-gram 重叠 ≥ 40% → strong，v+1
    │   ├─ ≥ 0.72 → weak，Claude 二次判断
    │   └─ < 0.72 → 新笔记
    ├─ Step 5: 决定文件路径（分类目录 + 迭代版本号）
    ├─ Step 6: 组装 Markdown
    ├─ Step 7: 写入 .md
    └─ Step 8: 同步前端 BUILTIN_NOTES（新增）
         ↓
前端刷新即可见
```

## 适用场景

所有走 Smart Notes 管线的入口都自动享受这个改动：
- research-capture skill（链接/文本投研材料）
- 主聊天"存笔记"指令
- CLI `save_note.py` 直接调用
- 未来任何接入 `note_pipeline.ingest()` 的新 skill

## 解决了什么痛点

| 环节 | 改动前 | 改动后 |
|------|--------|--------|
| 存笔记 | `save_note.py` 落盘 | 同上 |
| 前端显示 | 手动编辑 `index.html` 塞 BUILTIN_NOTES | 自动 patch |
| 失败处理 | 笔记和前端脱节，无感知 | 日志告警，笔记不受影响 |

## 方法论沉淀

**低耦合 + 高内聚**：前端同步是独立模块，不塞进 `save_note.py` 主干；`ingest()` 只做一个 import + try/except 调用。这样以后要改前端格式（动态 API 加载 / 新的数据结构）只动 `update_builtin_notes.py`，不动分类管线。

**容错设计**：主流程不能因为辅助步骤失败而中断。笔记落盘比前端显示更重要——.md 文件是真实数据，前端只是展示层。
