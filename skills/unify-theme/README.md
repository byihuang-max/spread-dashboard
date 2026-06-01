# unify-theme

GAMT 看板子页面主题统一工具。

## 背景
GAMT 看板有 16+ 个子页面，原来用"白色硬编码 + bb-override 暴力覆盖"实现明暗切换，切换时有跳变/reload。

## 新架构
- 一套 CSS 变量（`:root` 白色，`html.bb-dark` 暗色）
- 所有元素用 `var(--xxx)` 引用颜色
- 切换 = add/remove `bb-dark` class，0 reload，0.35s 过渡
- 页面自包含，不依赖外部 override 文件

## 使用
跟雷军说：
- "把 xxx.html 统一主题"
- "批量统一所有子页面主题"
- "新写的页面套上日夜模式"

## 标准参考
已完成的页面可作为模板：
- `macro/rates/rates.html` — Chart.js 页面标准
- `macro/global_calendar/calendar.html` — 纯表格/卡片页面标准
- `macro/halo_trade/halo_dashboard.html` — ECharts 页面标准
