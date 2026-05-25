# CSS 兜底覆盖与 inline 颜色保留的可靠模式

**日期**: 2026-05-24
**标签**: #CSS specificity #!important #属性选择器 #dark mode override #Bloomberg #热力图

---

## 摘要

在 bloomberg-override.css 的 catch-all 场景中，经过三轮试错确认：属性选择器精确重声明配合高特异度是保留特定 inline 颜色最可靠的方案，revert 和 :not() 排除均不稳定。

## 正文

CSS catch-all 兜底覆盖 vs inline 颜色保留 - 可靠模式

场景：bloomberg-override.css 需要把所有白色 inline 背景一刀切成黑色，但部分元素（热力图、chip）必须保留自己的 inline 颜色。

试过的方案与可靠度（按从弱到强）：
1. background: revert !important - 不可靠（多 !important 同级时无法回到 inline 值）
2. :not(.X) 在 catch-all 上排除 - 偶尔可靠（依赖声明顺序）
3. 属性选择器精确重声明 - 最稳：
   .content .card .heatmap-cell[style*="rgba(220,38,38"] {
     background: rgba(220,38,38,0.85) !important;
     color: #fff !important;
   }

铁律：
- 在 catch-all 战场，"用更高特异度 + 精确重声明" 比 "靠 revert/排除" 稳得多
- 把所有可能颜色档位列出来，每档单独写一条 - 工作量大但零失败
- 这种位置必须给元素加专属 class（heatmap-cell / mega-chip）方便后续维护

5/24 晚间反复踩了 3 轮才领悟到这点，先后用 :not() 失败、revert 失败、属性选择器才成。
