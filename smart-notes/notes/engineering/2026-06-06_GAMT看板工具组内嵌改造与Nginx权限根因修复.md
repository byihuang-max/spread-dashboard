# GAMT看板工具组内嵌改造与Nginx权限根因修复

**日期**: 2026-06-06
**标签**: #Nginx权限 #iframe内嵌 #chmod #安全加固 #GAMT看板 #部署工程化

---

## 摘要

将GAMT看板工具组由window.open外链改为iframe内嵌，并排查修复了因目录权限700导致的404问题及users.db等敏感文件公网可访问的安全漏洞。通过新建fix-perms.sh幂等脚本实现权限永久根治。

## 正文

GAMT看板「工具组外链改内嵌 + 权限根因排查」完整记录（2026-06-06）

## 背景目标
用户(Roni)发现工具组(择时研究/并购舆情监控/财报预期风险/团队基金优选/公募基金研究/Smart Notes)全是 window.open 外链：①跳新标签破坏看板统一观感 ②裸URL绕过登录遮罩(安全)。目标：除Smart Notes外全部改成跟主面板一样的右侧iframe内嵌渲染。

## 内嵌改造(纯前端，index.html)
主面板早已用 <iframe class="embed-frame"> 内嵌十几个模块(宏观/微观/套利/期权)，工具组没跟上。改造三步：
1. 导航项去掉 onclick="window.open(...)"，保留/补 data-module（navFundResearch原缺，补 data-module="fund_research"）
2. 在 page-alerts 前加5个 <div class="module-page" id="page-XXX"> 容器，内嵌对应iframe
3. MODULE_PAGE_MAP + titles 两个映射补上5个新模块
Smart Notes 和「邮件订阅管理」保留 window.open（独立应用，不在范围）。

## 真正的坑：数据加载404/空白 = 文件系统权限，不是代码/路径
内嵌后页面能打开但数据加载失败。根因排查链(关键方法论)：
- curl -H 'Host: xxx' http://127.0.0.1/path 实测HTTP码定位
- 看 /var/log/nginx/error.log → "stat() ... failed (13: Permission denied)"
- namei -l <文件路径> 逐层看权限链，定位卡在哪一级目录
根因：这些子目录是 700(drwx------)，nginx 的 www-data 进程无权进入 → 文件存在/路径对却返回404/403。
大白话比喻：服务器=楼，文件夹=房间，nginx=前台接待，访客=网页客户。房间锁死(700)前台没钥匙进不去，只能跟客户说"找不到"(404)。
涉及目录：timing-research/、skills/stock-monitor/(及其backtest_output/)、financial_risk/、fund-asset-recommend/、fund_analysis/、data/(及data/financial_risk_factor.json文件本身是600连组都读不了)。
修复：前端资产目录 chmod o+x(可进入)，html/json/js/css等文件 chmod o+r(可读)，显式排除 server/ venv/ zsxq/ .git/。

## 顺手发现并修复的安全漏洞（既有问题，非本次引入）
排查时实测发现 /server/users.db(用户账号数据库!)、/server/auth.py、/server/users.db.bak.*、/zsxq/config.json 全部 HTTP 200 可被公网直接下载。
修复：chmod o-rwx server zsxq，改成750(drwxr-x---)，www-data进不去→公网访问全部404。后端API是ubuntu用户跑的(端口9876)不受影响。
注意：原 sync-to-cloud.sh 第42/55行的 chmod -R o+rX 全放开正是这漏洞的元凶——它对云端已存在文件改权限，把users.db也放开了(虽然rsync exclude了不同步，但chmod照样放开)。

## 关键结构性根因：git reset --hard 会重置目录权限
git reset --hard / 目录重建 会把权限退回默认(常700) → 下次部署页面又404。这解释了"权限问题时有时无"：走 sync-to-cloud.sh(自带chmod)就正常，走 git push+git reset --hard(漏chmod)就404。

## 永久根治方案
新建 scripts/fix-perms.sh(幂等可反复跑)：①前端资产目录o+x+文件o+r(排除敏感目录)②server/、zsxq/ 强制 o-rwx 锁死。
改 sync-to-cloud.sh 第42/55行：把危险的 chmod -R o+rX 换成 bash ~/gamt-dashboard/scripts/fix-perms.sh。
效果：用户只需说"三端对齐"，无论底层走rsync脚本还是git reset，权限永远自动修对+敏感目录永远锁死。

## 协作语义澄清
用户说"三端对齐"=他的手动触发指令；助手执行(git push gitee + ssh腾讯云 git reset --hard)=自动。在助手语境里：用户下指令=手动，助手跑命令=自动。

## 验证结果(全部符合预期)
5个工具页200 / 数据文件200 / 敏感文件(users.db/auth.py/zsxq/config.json)404。

## 同期附带小改动
- 基金优选手机版：stat卡片6列竖排1列+6条蓝线刷屏 → 改 ≤1200px 3列、≤640px 2列+隐藏 .stat::before 蓝线+收紧padding/字号(commit 50492b57)
- 日报固定7模块(前一轮)：二百亿涨停/三异常信号无数据也出占位
- 内嵌后删掉各工具页左上角"返回看板"链接(4个文件有：timing-research/index.html、financial_risk/financial_risk_factor.html、fund_analysis/fund_research.html、skills/stock-monitor/stock_monitor.html)

## 可复用排查方法论(沉淀)
前端页面"文件在、路径对、却404/空白"时，第一怀疑文件系统权限而非代码：
1. curl -o /dev/null -w '%{http_code}' -H 'Host: 域名' http://127.0.0.1/路径  逐个测
2. sudo tail /var/log/nginx/error.log 看 Permission denied / stat() failed
3. namei -l 文件全路径  逐层看权限，找700/600卡点
4. nginx worker 用户：ps aux | grep 'nginx: worker'（通常www-data）
5. 修复排除敏感目录(server/含db和源码、zsxq/含config)，并主动 o-rwx 锁死它们
