# inject 脚本重复注入 bug 与 marker 防御原则

**日期**: 2026-05-24
**标签**: #inject #bug修复 #marker防御 #cron累积 #HTML注入 #工程规范

---

## 摘要

inject_quant_stock.py 因未完整删除旧注入内容导致累积 63 份重复脚本块，修复方案为用唯一 marker 包裹注入内容并在每次注入前清除旧内容。

## 正文

inject 脚本重复注入 bug - 防御原则

5/24 发现 inject_quant_stock.py 有个藏了几十天的重复注入 bug：
- 注入 chart_script 时只删了 <script src=".../chart.js"></script>（CDN 行）
- 但没删紧跟的内联 <script>...</script> 块
- 每次 cron 跑一次 → append 一份新的，从来没清掉
- 累积 63 份重复 / 8MB / 12500 行 / 3 个月历史

更糟的是：累积过程中某次 </script> 关闭标签错位，导致整个 strat-momentum-stock script 块语法错误，所有 chart 不渲染。

防御原则（写进 inject 脚本必备）：
1. 注入内容必须用唯一 marker 包裹：
   <!-- inject_quant_stock START -->
   ...内容...
   <!-- inject_quant_stock END -->
2. 每次 inject 先 re.sub 删除 START/END 之间所有内容，再重新注入
3. 不要靠"删 CDN 行"或"找 </body></html> 替换"这种半截匹配

修复手段：
- 给 inject 加 marker 包裹
- 一次性 sed 清理 index.html 中所有重复（节省 6.6MB / 8400 行）
- 重新跑 inject 注入干净的一份

教训：累积型 bug 一开始难发现，但浏览器没渲染 chart 时一定要先看 index.html 行数是不是异常膨胀。
