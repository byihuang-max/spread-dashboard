# Smart Notes 智能分类系统流程图

**日期**: 2026-05-05
**类型**: 决策 / 架构
**标签**: #smart-notes #embedding #llm #架构图 #流程图

---

## 看板关联

- 关联模块：Smart Notes（`~/Desktop/gamt-dashboard/smart-notes/`）
- 实现位置：`smart-notes/intelligence/`
- 关联笔记：`2026-05-05_GAMT架构梳理与对客逻辑缺口诊断.md`

---

## 整体流程（主干）

```mermaid
flowchart TD
    A["🗣️ Roni 在飞书发<br/>【存笔记：xxx】"] --> B[save_note.py 入口]
    B --> C[note_pipeline.ingest]

    C --> D["🤖 Claude 生成元数据<br/>title / summary / tags / category_hint"]
    C --> E["🧮 Embedding 分类<br/>BGE-base-zh 算向量"]

    D --> F{归类决策}
    E --> F

    F -->|LLM + Embed 一致| G1[直接落位]
    F -->|Embedding ≥ 0.60| G2[auto 落位]
    F -->|Embedding 0.50~0.60| G3["⚠️ 灰区<br/>Claude 看全部 10 类仲裁"]
    F -->|都不确定| G4["❓ need_confirm<br/>回给 Roni 问"]

    G1 --> H[迭代检测]
    G2 --> H
    G3 --> H
    G4 --> STOP[等待人工确认]

    H --> H1{"向量相似度 TOP1"}
    H1 -->|≥ 0.82 + 标题重叠 ≥ 40%| I1["💪 strong<br/>直接 v+1"]
    H1 -->|≥ 0.72| I2["⚠️ weak<br/>Claude 二次确认"]
    H1 -->|&lt; 0.72| I3[独立新笔记]

    I2 -->|confidence=high/med| I1
    I2 -->|confidence=low| I3

    I1 --> J1["📝 组装文档<br/>标题 / 日期 / 版本 / 迭代自 / 摘要 / diff / 正文"]
    I3 --> J1

    J1 --> K["💾 写入对应目录<br/>按类别映射到 notes/* 或根目录"]
    K --> L["✅ 回消息给 Roni<br/>路径 / 类别 / 是否迭代 / 决策日志"]

    style A fill:#fff4e6
    style L fill:#e6f7ff
    style G3 fill:#fff0f0
    style I2 fill:#fff0f0
    style G4 fill:#ffe0e0
    style STOP fill:#ffe0e0
```

---

## 归类决策细节

```mermaid
flowchart TD
    Start[收到新内容] --> Parallel[并行两路判断]

    Parallel --> Path1[路径 1: LLM category_hint]
    Parallel --> Path2[路径 2: embedding 相似度]

    Path1 --> A1[Claude 读原文<br/>直接输出类别建议]
    Path2 --> A2[对 10 个类别中心算余弦]
    A2 --> A3["top_category_score"]

    A1 --> M{融合决策}
    A3 --> M

    M -->|LLM hint == embed rec| Green[✅ 一致 → auto]
    M -->|embed ≥ 0.60| Green2[✅ embed auto]
    M -->|embed 0.50~0.60| Yellow["⚠️ 灰区 → Claude 看全部 10 类仲裁"]
    M -->|LLM 给 __NEW__| Red1[❓ 新类建议 → 问 Roni]
    M -->|embed < 0.50 且 LLM 无建议| Red2[❓ 无把握 → 问 Roni]

    Yellow --> Y1{Claude 仲裁结果}
    Y1 -->|选了已有类别| Green3[✅ 落位 + reason]
    Y1 -->|返回 __NEW__| Red1

    style Green fill:#e6ffe6
    style Green2 fill:#e6ffe6
    style Green3 fill:#e6ffe6
    style Yellow fill:#fff4e6
    style Red1 fill:#ffe0e0
    style Red2 fill:#ffe0e0
```

---

## 迭代决策细节

```mermaid
flowchart TD
    Start[收到新内容向量] --> V[vs 每篇历史笔记算余弦]
    V --> TOP["取 top 3 + 计算标题 2-gram 重叠"]

    TOP --> D1{top1 判断}

    D1 -->|相似度 ≥ 0.82<br/>标题重叠 ≥ 0.40| Strong["💪 strong"]
    D1 -->|相似度 ≥ 0.72| Weak["⚠️ weak"]
    D1 -->|相似度 &lt; 0.72| None[独立新笔记]

    Strong --> SD[Claude 生成 diff 摘要]
    SD --> VP[文件自动升版<br/>探测现有版本号 → v+1]

    Weak --> WC[Claude 读原文二次判断]
    WC --> WR{confidence}
    WR -->|high / medium| SD
    WR -->|low / false| None

    VP --> Out1[写成 v2 文件<br/>含 extends + diff]
    None --> Out2[写成新日期文件]

    style Strong fill:#e6ffe6
    style Weak fill:#fff4e6
    style None fill:#f0f0f0
    style Out1 fill:#e6f7ff
    style Out2 fill:#e6f7ff
```

---

## 版本号探测逻辑

```mermaid
flowchart LR
    F["文件名示例<br/>029_强势股日报体系v1.5_2026-05-02.md"] --> R["正则匹配<br/>[_-]?v(\d+(\.\d+)?)"]
    R --> E["提取: base, ver"]
    E --> B1["base = 029_强势股日报体系_2026-05-02"]
    E --> B2["ver = 1.5"]
    B2 --> NV["下一版 = int(1.5) + 1 = 2"]
    B1 --> NN["new_name = base + _v2.md"]
    NV --> NN
    NN --> OUT["029_强势股日报体系_2026-05-02_v2.md"]

    style OUT fill:#e6f7ff
```

---

## 10 个类别归属示例

```mermaid
flowchart LR
    subgraph 输入侧
        I1["'巴西央行加息结束'"]
        I2["'三端对齐新流程'"]
        I3["'强势股日报 v1.6'"]
        I4["'某个策略概念定义'"]
        I5["'外部研报摘录'"]
    end

    subgraph 类别目录
        C1[notes/emerging_markets]
        C2[notes/engineering]
        C3[conversations]
        C4[concepts]
        C5[notes/reports]
        C6[decisions]
        C7[sessions]
        C8[notes/research/factors]
        C9[notes/research/strategy]
        C10[notes/research/narrative]
    end

    I1 -.灰区仲裁.-> C1
    I2 -.auto + strong迭代.-> C2
    I3 -.weak→确认 strong.-> C3
    I4 -.LLM hint.-> C4
    I5 -.LLM hint.-> C5

    style I1 fill:#fff4e6
    style I2 fill:#e6ffe6
    style I3 fill:#e6ffe6
```

---

## 模型分工

| 层 | 模型 | 位置 | 作用 | 成本 |
|----|------|------|------|------|
| L1 向量化 | BGE-base-zh-v1.5 | 本地（ModelScope 下载） | 文本 → 768 维向量 | 零 |
| L1 相似度 | numpy 余弦 | 本地 | 归类 + 迭代候选 | 零 |
| L2 生成 | Claude Opus 4.7 | aicanapi-47 中转 | 标题 / 摘要 / 标签 | ~¥0.01/次 |
| L2 仲裁 | Claude Opus 4.7 | 同上 | 灰区归类兜底 | ~¥0.01/次 |
| L2 diff | Claude Opus 4.7 | 同上 | v1 vs v2 变化摘要 | ~¥0.02/次 |

**单篇笔记总成本：** 约 ¥0.02~0.05（最多 3 次 Claude 调用）

---

## 文件结构

```
smart-notes/intelligence/
├── notes_intel.py          # L1 层：扫描 / 向量化 / embedding 分类
├── llm_client.py           # L2 层：Claude API 封装
├── note_pipeline.py        # 核心 ingest() 编排
├── save_note.py            # CLI + 飞书入口
├── note_vectors.json       # 向量库（86 篇，~2MB）
├── category_centers.json   # 9 个类别中心（~200KB）
└── README.md
```

---

## 防分类膨胀机制

```mermaid
flowchart TD
    Try[新内容进入] --> Q{有现有类别可归?}
    Q -->|是| Normal[正常归类]
    Q -->|否| NC[LLM 建议 __NEW__]

    NC --> R1["pipeline 不自动创建新目录"]
    R1 --> R2["返回 need_confirm"]
    R2 --> R3["Kiro 问 Roni 要不要建新类"]
    R3 --> D{Roni 决定}
    D -->|建| CreateNew[人工 mkdir + 重建索引]
    D -->|归入现有最接近的| Reroute[手动指定 --category]

    style NC fill:#ffe0e0
    style R1 fill:#fff4e6
    style R2 fill:#fff4e6
```

---

## 未来扩展（阶段 3 - 未启动）

```mermaid
flowchart LR
    subgraph "阶段 3 · 定期审计"
        A1[每周跑 audit_intel.py]
        A2[检测迭代候选清单]
        A3[检测孤儿类别]
        A4[检测类别相似度预警]
    end

    A1 --> A2
    A1 --> A3
    A1 --> A4
    A2 --> OUT[AUDIT.md 报告]
    A3 --> OUT
    A4 --> OUT
    OUT --> Roni[Roni 决策]

    subgraph "阶段 4 · 前端集成（可选）"
        F1[smart-notes/index.html]
        F2[笔记详情页加相关推荐栏]
        F3[打开笔记时显示 top 5 语义相关]
    end
```

---

## 关键设计决策（和记忆）

1. **本地 BGE + 云端 Claude 混合**：Claude 没 embedding 能力，相似度匹配不需要 LLM，两者配合成本/效果最优

2. **ModelScope 下载模型**：Hugging Face 直连不稳，代理也挂了，国内走 ModelScope 镜像站 1 分钟到手

3. **Homebrew Python 装依赖的正解**：`pip3 install --user --break-system-packages`（--user 隔离到 `~/Library/Python/3.14/`，不污染系统）

4. **防分类膨胀的三重保险**：
   - 不自动创建新目录
   - 灰区 prompt 强调"优先现有类别（含空类）"
   - 版本探测支持 `v1.5` 这种非整数版本号

5. **触发方式：Roni 说「存笔记：...」→ 我调 save_note.py**
   - 已写入 MEMORY.md 作为长期识别规则
   - 加「预览一下 / dry run」走 `--dry` 不落地

---

## 对话溯源

本次系统设计源于 Roni 的三个连环问题：

1. **"关键字没命中但有关联怎么办？"** → embedding 余弦相似度
2. **"怎么识别版本迭代？"** → embedding + 标题重叠 + Claude diff 三重判断
3. **"整个 Smart Notes 能不能更聪明？"** → L1 检索层 + L2 生成层的分层架构

Roni 原本以为本地模型"没有泛化能力"，澄清后确认：
- embedding 不需要 LLM 的推理能力，需要的是**语义相似度判断**
- 真正需要泛化的部分（摘要/仲裁/diff）交给 Claude
- 两者组合 = 快 + 聪明 + 便宜
