# GAMT看板与Bloomberg主题协作工作流

**日期**: 2026-05-26
**版本**: v2
**迭代自**: `notes/engineering/2026-05-24_Bloomberg_终端风主题部署架构.md`
**标签**: #GAMT看板 #Bloomberg主题 #前端架构 #CSS皮肤 #cron自动化 #团队口径

---

## 摘要

讲解GAMT Dashboard三层架构（代码仓库、云端cron数据更新、浏览器端主题加载）的协作机制，说明数据更新与Bloomberg暗色皮肤互不干扰的设计原理及当前inline样式盲点的成因与解法。

## 相比上一版

- 从技术实现记录升级为面向团队/客户的「傻瓜版讲解」口径文档，增加大白话解释
- 新增「三层架构心智模型」框架（代码仓库 → cron 数据更新 → 浏览器端主题切换），比旧版结构更完整
- 补充了 cron 每日更新流程细节（Tushare/iFind → inject → render → git push）以及与主题文件互不干扰的关系
- 扩展了浏览器端主题切换的四步机制（iframe media 属性切换、light 模式叠加层），比旧版更详尽

## 正文

# GAMT 看板 + Bloomberg 主题完整工作流（傻瓜版讲解）

Roni 2026-05-25 深夜问：云端每天更新代码和 Bloomberg 主题之间到底怎么协作。沉淀这套讲解口径供后续给团队/客户解释用。

## 三层架构心智模型

### 第一层：代码仓库（一份源码）

```
gamt-dashboard/
├── index.html              ← 主页面（含登录、左侧导航）
├── bloomberg-override.css  ← 暗色皮肤（静态文件）
├── bloomberg-light.css     ← 亮色皮肤叠加层
├── data/*.py               ← 抓数据脚本
├── inject_*.py             ← 把数据塞进 HTML 的脚本
├── render_html.py          ← 生成子页面的脚本
└── env_fit/, macro/, ...   ← 15 个 iframe 子页面 HTML
```

**大白话：** 就一个文件夹，所有代码都在这。Bloomberg 不是"另一个项目"，就是这文件夹里多了两个 .css 文件而已。

### 第二层：腾讯云每天 cron（只更新数据，不碰 CSS）

每天定时任务（早盘前 / 盘后 / 晚 21:00）：

1. `data/*.py` → 去 Tushare/iFind 拉今天的行情数据 → 存 JSON
2. `inject_*.py` → 把 JSON 数据塞进 index.html 占位符
3. `render_html.py` → 生成 antifragile.html / liquidity.html 等子页面
4. git commit + push → Gitee → 腾讯云 pull → Nginx 上线

**关键：第④步只动 *.html 和 *.json，从来不动 bloomberg-override.css**

**大白话：** cron 就像每天上班的小机器人，它的工作只是"把今天的股价数字写到网页上"。它不知道也不关心 Bloomberg 主题。

### 第三层：用户打开浏览器（这里才决定穿哪件衣服）

**场景 A：客户打开 dashboard.gamtfof.com**
- 浏览器加载 index.html
- `<head>` 里 JS 检测 URL 没有 ?theme=bloomberg → 啥也不做 → 白底默认版
- 客户看到原版网页，跟以前一样

**场景 B：自己打开 dashboard.gamtfof.com/?theme=bloomberg**
- JS 检测到参数后忙活四件事：
  1. 动态加载 bloomberg-override.css（披上黑色外套）
  2. 唤醒 iframe 子页面里的暗色样式（把 `<style media="not all">` 改成 `media="screen"`，让 iframe 里的小网页也穿上黑外套）
  3. 注册 Chart.js `afterLayout` 钩子（每次画图前强制改网格线颜色，覆盖 inject 脚本里硬编码的颜色）
  4. 如果还带 ?mode=light → 再叠 bloomberg-light.css（黑外套外面再罩白马甲，做日夜模式）

## 最终效果对照

| 维度 | 白底版（客户用）| Bloomberg 版（自己用）|
|------|---------------|---------------------|
| 数据 | 今天的 | 今天的（一样）|
| HTML | 今天的 | 今天的（一样）|
| CSS | 默认浅色 | override 暗色 |
| 图表 | 彩色 | 橙绿红 + 暗灰 |

**数据和 HTML 一模一样，只有 CSS 和图表样式不同。**

## 三句话总结

1. 云端 cron 每天只更新"数据"和"HTML 内容"，不动皮肤
2. Bloomberg 皮肤是"用户打开网页时浏览器自己加载的"，不是云端处理的
3. URL 参数 ?theme=bloomberg 是开关，决定要不要穿这件外套

## 为啥这阵子反复修盲点

问题出在 inject 脚本里硬编码了 inline 样式，比如：
```html
<div style="background:#fff; color:#1e293b">
```

inline 样式优先级最高，CSS 外套盖不住它。所以要在 bloomberg-override.css 里写"专门针对 #fff 的属性选择器"硬刚。一旦 inject 脚本里冒出新颜色，CSS 就漏一个盲点。

**彻底解法：** 把 inject 脚本改成 class-based（不写颜色，只写 class 名），让 CSS 完全掌控皮肤。工程量大，目前先打补丁。

## 一句话核心

**数据是天天换的，皮肤是用户进门时自己挑的，两边互不干扰。**
