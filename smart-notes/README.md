# Smart Notes

GAMT 投研看板的知识沉淀系统。把研究对话、设计决策、工程经验、外部研报统一归档，并与看板模块建立关联。

## 目录结构

```
smart-notes/
├── index.html              # 前端页面（Cloudflare Pages 托管）
├── notes_api.py            # 后端 API（/api/notes，动态扫描）
├── update_builtin.py       # 重建 index.html 内嵌的 BUILTIN_NOTES
├── sync.sh                 # 一键检查笔记数量是否对齐
├── audit_notes.py          # 完整性审计脚本（见下方）
├── AUDIT.md                # 审计报告输出（自动生成，勿手动编辑）
└── notes/
    ├── research/
    │   ├── factors/        # 因子与择时
    │   ├── strategy/       # 策略与框架
    │   └── narrative/      # 叙事与宏观
    ├── engineering/        # 工程实现
    ├── reports/            # 外部研报
    └── emerging_markets/   # 新兴市场思考
```

## 笔记规范

每篇笔记建议包含以下元数据（写在前 10 行内）：

```markdown
# 标题

**日期**: 2026-XX-XX
**类型**: 对话 / 决策 / 概念 / 研报
**标签**: #关键词1 #关键词2

---

## 看板关联

- 关联模块：强势股情绪 / 资金流拥挤度 / ...
- idea 建议：...
```

审计脚本会检查这些字段是否存在。

## 审计脚本

`audit_notes.py` 自动检查 Smart Notes 的完整性，覆盖 5 个维度：

| 维度 | 说明 |
|------|------|
| 模块覆盖 | 看板有模块但 Smart Notes 无对应笔记 |
| 元数据完整性 | 笔记缺日期、标签、看板关联 |
| 陈旧检测 | 超过 60 天未更新的笔记 |
| 空目录 | 分类目录下无任何笔记 |
| 对话沉淀 | memory/ 日记中的决策未在 Smart Notes 出现 |

### 用法

```bash
# 跑审计，输出 AUDIT.md
python3 smart-notes/audit_notes.py

# 只打印到终端，不写文件
python3 smart-notes/audit_notes.py --stdout

# 列出缺元数据的笔记路径（方便批量补）
python3 smart-notes/audit_notes.py --fix-meta
```

### 自动化

审计脚本可接入 cron 定期执行（如每周日 20:00），结果写入 `AUDIT.md`。打开看板 Smart Notes 页面即可看到待补清单。

```cron
# 每周日 20:00 跑审计
0 20 * * 0 cd ~/Desktop/gamt-dashboard && /opt/homebrew/bin/python3 smart-notes/audit_notes.py
```

## 日常维护

- 重要对话结束后，沉淀一篇笔记到对应分类
- 每篇笔记写明看板关联和 idea 建议
- 定期跑 `audit_notes.py` 检查遗漏
- 新模块上线时，同步写一篇设计笔记
