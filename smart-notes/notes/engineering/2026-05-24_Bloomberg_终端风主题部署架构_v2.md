# GAMT 看板 Bloomberg 主题 CSS 架构

**日期**: 2026-05-30
**版本**: v2
**迭代自**: `notes/engineering/2026-05-24_Bloomberg_终端风主题部署架构.md`
**标签**: #Bloomberg主题 #CSS架构 #暗色模式 #iframe同步 #GAMT看板 #前端工程

---

## 摘要

描述 GAMT 看板的 Bloomberg 主题 CSS 加载流程，包括静态 shell、动态 dark override、localStorage 持久化、iframe 子页面同步及主题切换的完整架构设计。

## 相比上一版

- 从单一 URL 参数切换方案演进为 localStorage + shell/override 双层 CSS 架构，支持暗色/亮色模式切换
- 新增详细的页面加载流程与主题切换流程（bbToggleMode / applyMode）描述
- iframe 子页面同步机制从简单提及扩展为 parent.__bbMode 读取 + message 监听 + 延迟 reload 策略
- CSS 文件职责拆分更清晰（shell 始终生效 vs override 按模式启禁），废弃了旧的 bloomberg-light.css

## 正文

# GAMT 看板 Bloomberg 主题 CSS 架构流程图

## 页面加载流程

浏览器解析 index.html <head>:

1. **静态 <link href="bloomberg-shell.css">** — 始终加载，阻塞渲染
   - 覆盖 :root 变量（--accent:#ff8c00 等）
   - sidebar/header/Tab Bloomberg 风格

2. **<style> 原始 CSS** — 定义默认变量、布局、卡片
   - 被 shell 的 !important 覆盖

3. **Bootstrap <script>（同步执行）**
   - 读取 localStorage("bbMode")
   - window.__bbMode = "dark" 或 "light"
   - 动态创建 <link id="bb-dark-css" href="bloomberg-override.css">
   - light → darkLink.disabled = true（不加载）
   - dark → darkLink.disabled = false（加载）

→ 渲染首帧（无闪烁）

## 主题切换流程（用户点击按钮）

bbToggleMode() → applyMode(m):

1. window.__bbMode = m
2. localStorage.setItem("bbMode", m)
3. bb-dark-css.disabled = (m==="light")
   - dark: override.css 生效 → 全站暗色
   - light: override.css 禁用 → 内容区白色，框架仍由 shell 控制
4. body class 切换（bb-light / bb-light-shell）
5. Chart.js defaults 更新 + update()
6. 按钮文字更新

延迟 400ms 后处理 iframe:
- 可见 iframe → src 加 ?_t=时间戳 强制重新加载
- 隐藏 iframe → 标记 data-needs-reload，切 Tab 时再 reload

## iframe 子页面加载流程

子页面 bootstrap:
- 读取 parent.__bbMode 或 parent.localStorage("bbMode")
- light → return（不加载暗色 CSS，用原始白色样式）
- dark → 加载 bloomberg-override.css + 激活内联 <style id="bb-override">

注册 message 监听器（备用实时切换）

## CSS 文件职责

| 文件 | 职责 |
|------|------|
| bloomberg-shell.css | 始终生效。sidebar/header/user-bar Bloomberg 风格 + :root 变量覆盖 |
| bloomberg-override.css | dark 时生效。全站暗色覆盖。light 时 disabled |
| bloomberg-light.css | 已废弃，不再引用 |
| 原始 <style> | 基础布局+白色配色，被 shell/override 的 !important 覆盖 |

## 最终效果

- **暗色模式:** shell + override 同时生效 → 全站 Bloomberg 暗色终端风
- **亮色模式:** shell 生效，override disabled → 框架暗色 + 内容区白色
