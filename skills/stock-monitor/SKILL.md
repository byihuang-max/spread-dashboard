---
name: stock-monitor
description: 个股监控每日推送。监控指定股票的公告、减持、舆情和筹码结构，盘后自动发飞书卡片。减持公告红色高亮。
trigger:
  - 个股监控
  - stock-monitor
  - 监控列表
---

# 个股监控 Skill

## 触发词

| 说法 | 动作 |
|------|------|
| 个股监控加票 昊志机电 | 添加到监控列表 |
| 个股监控删票 昊志机电 | 从列表移除 |
| 个股监控发一次 | 立刻手动触发发送 |
| 个股监控看列表 | 查看当前监控了哪些票 |
| stock-monitor 加票 XXX | 同上 |

关键前缀：**个股监控** 或 **stock-monitor**，避免跟其他"加票"混淆。

## 执行方式

```bash
# 手动触发
cd ~/Desktop/gamt-dashboard/skills/stock-monitor
python3 stock_monitor.py

# 预览不发送
python3 stock_monitor.py --dry
```

## 配置文件
`watchlist.json` — 股票列表 + 飞书群 ID + 参数

## 自动运行
腾讯云 crontab 工作日 18:30 自动跑。

## 注意事项
- iFinD MCP 需要有效 token
- Tushare 直连不用代理
- 飞书发送需要 bot 在目标群里
- 加票时需要提供股票名称，我会自动查 ts_code
