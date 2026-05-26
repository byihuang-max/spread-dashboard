# Bloomberg主题CSS三层架构复盘与重构方案

**日期**: 2026-05-25
**版本**: v2
**迭代自**: `notes/engineering/2026-04-25_GAMT主页Bloomberg风格改造与sed教训.md`
**标签**: #CSS架构 #主题切换 #Bloomberg终端 #CSS变量 #技术债务 #前端工程

---

## 摘要

复盘Bloomberg暗色/亮色主题切换落地中暴露的CSS架构问题：catch-all与精确重声明的特异度冲突、iframe规则不统一、布局与配色未分离，提出拆为layout/color-dark/color-light三文件并用CSS变量驱动的重构路径。

## 相比上一版

- 旧笔记记录 Bloomberg 风格改造的决策（去 emoji）和 sed 批量替换的教训；新笔记深入到改造落地后 CSS 架构的具体技术债务复盘
- 新笔记新增了三层 CSS 架构（base / dark override / light overlay）的详细拆解
- 新笔记聚焦特异度冲突、iframe 规则不统一、inline style 缺少 light 反转等工程问题
- 时间线从 4/25 推进到 5/25，是同一 Bloomberg 主题改造项目的后续迭代

## 正文

# Bloomberg 主题 CSS 三层架构问题与拆解（2026-05-25 复盘）

## 背景

5/24 上线 Bloomberg 暗色主题，5/25 加日夜切换。落地过程中发现 CSS 结构混乱，多个层次互相覆盖，新增亮色叠加层时大量盲点漏过去。

## 现有三层 CSS 架构

### 层 1：原版 GAMT 浅色（base）
- `index.html` 内 `<style>` 块 + 各 iframe 子页面自己的 `<style>` 块
- 大量 inline `style="background:#fff"` / `style="color:#1e293b"` 写死在 HTML
- 来源：3 月份初版手写

### 层 2：bloomberg-override.css（dark 暗色覆盖）
- 250 行 + 末尾 250 行 inline catch-all
- 用 `.content [style*="..."]` catch-all 拦截 inline 浅色背景，统一翻成 #0a0a0a
- 用 `.X[style*="rgba(...)"]` 属性选择器精确重声明（热力图、chip 等需保留功能色的元素）
- iframe 子页面：自己有内联 `<style id="bb-override" media="not all">` + JS 检测 parent URL 切 `media="screen"`

### 层 3：bloomberg-light.css（light 亮色叠加）
- 5/25 新增，依赖层 2 已加载
- 用 `body.bb-light-shell .content` 反向覆盖层 2 的暗色到浅色
- iframe 用 `body.bb-light:not(.bb-light-shell)` 整页翻白

## 核心问题

### 问题 1：catch-all vs 精确重声明的特异度战场
层 2 用 `.content [style*="background"]` 一刀切（特异度 0,0,1,1）
层 3 想反向用 `body.bb-light-shell .content [style*="background"]:not(...)` 还原（特异度 0,0,2,2）

理论上 light 应该赢，但 `revert` 在多 `!important` 战场不可靠（5/24 已经踩过）。
正确做法是属性选择器**精确重声明每一个色档**，工程量随 inline style 数量线性增长。

### 问题 2：iframe 子页面规则不统一
15 个 iframe 子页面里：
- 有的有 `<style id="bb-override" media="not all">` 内联块
- 有的没有，只靠主页面 link 注入的 bloomberg-override.css
- 有的内联块用 catch-all（`p,span,div{color:#ccc}`），有的用属性选择器精确匹配
- 反脆弱（antifragile）甚至有完整的内联 `<script>` 自己生成 `<style>` 注入

light 模式想覆盖时，每种模式要写不同的反向规则，盲点很难穷尽。

### 问题 3：暗色规则注入 inline style 没有 light 反转
有些子页面（比如 5/24 给反脆弱加暗色时）写了 `[style*="background:#fff"] { background:#0a0a0a }`，但没写"light 模式下反转回去"的规则。light 模式去看时还是浅色 → 因为 inline style 在暗色叠加被翻黑、又被 light 翻回浅色，但中间路径不稳。

## 根因

**从来没有清晰的"布局层 vs 配色层"分离。**

bloomberg-override.css 同时承担：
- 布局（紧凑卡片、字体、间距）
- 暗色配色（色值）
- inline style 兜底覆盖（catch-all）

三件事混在一个文件，光看名字"override"就不知道哪些规则是布局哪些是配色。

## 拆解目标（待重构）

```
bloomberg-layout.css   (布局：紧凑卡片/JetBrains Mono 字体/卡片边框宽度/padding)
bloomberg-color-dark.css   (配色：黑底/橙强调/暗灰文字)
bloomberg-color-light.css  (配色：白底/橙强调/深蓝灰文字)
```

切换逻辑：
- `?theme=bloomberg` → 永远加载 layout
- `mode=dark` → 加载 color-dark
- `mode=light` → 加载 color-light

不再有"反向覆盖"，每个配色文件独立完整。

## inline style 处理新规则

不靠 catch-all 翻 inline style，而是**预处理 HTML**：
- 在 inject_*.py / render_html.py 生成 HTML 时不写 `style="background:#fff"`，而是写 `class="bb-card"`
- CSS 里 `.bb-card { background: var(--card-bg) }`，dark/light 各自定义 `--card-bg`

这是真正的 CSS 变量驱动，不再依赖 inline style 战场。

## 短期 vs 长期

**短期（1-2 天）：** 在现有 CSS 上修 light 模式可见盲点（Roni 反馈具体哪里有问题就改哪里）
**长期（3-5 天）：** 抽出 layout/color 三层 CSS + CSS 变量化，把 inline style 逐步改成 class

## 教训

- 写 CSS 主题切换前，**先想清楚布局层和配色层的边界**，不要混在一个 override 文件里
- 用 catch-all + 属性选择器是"暗色覆盖浅色"场景的妥协，不是"主题切换"的工程方法
- iframe 子页面的内联 `<style>` 是隐性大坑，多套规则散落在 15 个文件里很难维护，应该统一走外部 CSS
- CSS 变量（`--bg` / `--text` / `--card-bg`）是主题切换的正解，比规则覆盖战场可靠 100 倍
