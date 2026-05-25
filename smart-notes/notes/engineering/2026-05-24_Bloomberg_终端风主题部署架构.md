---
title: 2026-05-24 Bloomberg 终端风主题部署架构
date: 2026-05-24
tags:
  - Bloomberg
  - 主题切换
  - 部署架构
  - GAMT
  - URL参数
  - Chart.js
  - afterLayout
category: engineering
---

GAMT 看板支持双版本同站，靠 URL 参数切换风格。

## 双版本访问

| 访问方式 | 显示 | 用户 |
|---|---|---|
| `dashboard.gamtfof.com/` | 原白色版 | 客户/团队 |
| `dashboard.gamtfof.com/?theme=bloomberg` | 彭博黑橙风 | Roni 自用 |

## 技术实现

在 `index.html` `<head>` 注入一段 38 行 IIFE：

```js
(function(){
  if(!location.search.includes("theme=bloomberg"))return;  // 没参数直接退出
  // 1) 动态注入 override CSS
  var l=document.createElement("link");
  l.rel="stylesheet";l.href="bloomberg-override.css";
  document.head.appendChild(l);
  // 2) hook Chart.js
  function tryHook(){
    if(typeof Chart==="undefined")return false;
    Chart.defaults.color="#888";
    Chart.defaults.borderColor="#2a2a2a";
    Chart.register({
      id:'bbGridLate',
      afterLayout:function(chart){
        // 事后改写每个 scale.options.grid
      }
    });
    return true;
  }
  // ... retry 逻辑
})();
```

## 三条关键决策

**1. 用 afterLayout 不用 beforeUpdate**
beforeUpdate 会污染 time scale，导致 chartjs-adapter-date-fns 报 `t.startsWith is not a function`。

**2. 实例 scale.options 优先级 > Chart.defaults**
所以必须 afterLayout 事后改写 scale.options，不能只改 defaults。

**3. catch-all CSS 必须用属性选择器精确重声明做兜底**
`.content [style*="background"]` 这种 catch-all 会无差别覆盖所有 inline 背景。`revert !important` 在多 `!important` 战场不可靠，必须用 `.X[style*="rgba(...)"] { background: ...; }` 显式重声明。

## 子页面（iframe）

24+ 个独立 HTML 子页面（meso/macro/micro_flow/env_fit）各自带 bb-overrides.js + override CSS。

## 共用 vs 隔离

- 数据、HTML 结构、JS 逻辑：完全共用
- 主题：只是 CSS 叠层 + Chart.js 钩子
- 客户访问默认版与自用 Bloomberg 版互不影响

## 回滚方案

```bash
cd ~/Desktop/gamt-dashboard
git reset --hard pre-bloomberg-2026-05-24
git push --force gitee main
ssh ubuntu@111.229.129.146 'bash /home/ubuntu/deploy_sync.sh'
```

Tag `pre-bloomberg-2026-05-24` 在 Gitee 永久保留，5/24 上线前打的安全网。

## 上线时间线

- 16:00 开始部署，commit `5bd8319b`（34 文件 +17296/-8574）
- 16:30 rebase 冲突误用 ours 丢失 hook，commit `0213d05a` 修复
- 17:00 验证 dashboard.gamtfof.com/?theme=bloomberg 可达
- 19:00 三轮风格迭代，commit `6f6a0ede`
- 23:00-23:18 晚间补丁五连战（chip 拆分、产业链传导、热力图、图表网格全隐藏），最终 commit `738c71f1`
