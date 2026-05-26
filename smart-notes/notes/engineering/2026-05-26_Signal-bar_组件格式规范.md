# Signal-bar 组件格式规范

**日期**: 2026-05-26
**标签**: #signal-bar #Bloomberg主题 #CSS规范 #组件设计 #前端样式

---

## 摘要

定义了 Bloomberg 暗色主题下 signal-bar 模块的 HTML 结构、CSS 样式规则、tag 颜色语义及常见 CSS 覆盖问题的解决方案。

## 正文

Bloomberg 主题 signal-bar 标准格式规范

## 标准 HTML 结构

```html
<div class="signal-bar">
  <div class="signal-main">模块名称</div>
  <div class="signal-tags">
    <span class="signal-tag good">指标A 数值</span>
    <span class="signal-tag warn">指标B 数值</span>
    <span class="signal-tag risk">指标C 数值</span>
  </div>
  <div style="margin-left:auto;font-size:11px;color:#7c8598">更新: 时间</div>
</div>
```

## Bloomberg 暗色样式（由 bloomberg-override.css 全局处理）

- 背景：`#0f0f0f`
- 边框：`1px solid #2a2a2a`
- 左侧橙色竖杠：`border-left: 3px solid #ff8c00`
- 标题 `.signal-main`：`color: #ff8c00`
- 圆角：`0`（Bloomberg 风格无圆角）

## signal-tag 颜色 class

- `good` = 绿色背景（rgba(34,197,94,0.2)）+ 绿色文字（#4ade80）→ 正常/健康
- `warn` = 黄色背景（rgba(245,158,11,0.25)）+ 黄色文字（#fbbf24）→ 注意
- `risk` = 红色背景（rgba(239,68,68,0.2)）+ 红色文字（#f87171）→ 警告
- 无 class = 灰色（rgba(255,255,255,0.1)）+ 灰色文字（#b8bfce）→ 中性

## 避坑要点

1. 子页面 bb-override 里如果写了 `.signal-bar { border: 1px solid #2a2a2a!important }` 会覆盖全局的 border-left 橙色竖杠。必须显式加回 `border-left: 3px solid #ff8c00!important`
2. signal-tags 内容应为动态数据（从 JSON 渲染），不是静态描述文字
3. 更新时间放在 signal-bar 最右侧，用 `margin-left:auto` 推到右边

## 已应用的模块

- 全球利率与汇率（rates.html）
- 经济基本面（fundamentals.html）
- 反脆弱看板（antifragile.html / render_html.py）
- HALO 交易（halo_dashboard.html）
- 境内流动性（liquidity.html）
- 全球金融日历（calendar.html）
