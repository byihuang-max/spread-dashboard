# 个股监控 Skill (stock-monitor)

每日盘后自动推送飞书卡片，监控指定股票的公告、舆情、减持动态和筹码结构。

## 功能

- **全量公告**：通过 iFinD MCP 拉取当日所有公告
- **减持高亮**：减持相关公告红色加粗，卡片标题变红
- **减持明细**：Tushare `stk_holdertrade` 获取股东减持数量/均价/比例
- **舆情动态**：iFinD 新闻语义检索
- **筹码结构**：复用 chip_query 模块，展示获利比例/主力资金流

## 文件结构

```
skills/stock-monitor/
├── watchlist.json      # 监控股票列表 + 配置
├── stock_monitor.py    # 主脚本
├── README.md           # 本文件
└── SKILL.md            # AI 触发文件
```

## 使用

```bash
# 预览（不发送）
cd ~/Desktop/gamt-dashboard/skills/stock-monitor
python3 stock_monitor.py --dry

# 正式发送
python3 stock_monitor.py
```

## 配置

编辑 `watchlist.json`：

```json
{
  "stocks": [
    {"ts_code": "300503.SZ", "name": "昊志机电", "focus": ["减持"]},
    {"ts_code": "605555.SH", "name": "德昌股份", "focus": ["减持"]}
  ],
  "settings": {
    "send_time": "18:30",
    "feishu_chat_id": "oc_63ee7ddec4971b0c6064d378effd08ec",
    "lookback_days": 60,
    "news_days": 1
  }
}
```

- `focus`：重点关注的关键词，匹配到的公告会红色高亮
- `news_days`：拉取最近 N 天的公告/舆情
- `lookback_days`：筹码计算回看天数

## 数据源

| 数据 | 来源 | 接口 |
|------|------|------|
| 减持明细 | Tushare | `stk_holdertrade` |
| 公告 | iFinD MCP | `search_notice` |
| 舆情 | iFinD MCP | `search_news` |
| 筹码/资金流 | Tushare | `daily` + `moneyflow` |

## 部署

腾讯云 crontab 添加（工作日 18:30）：
```
30 18 * * 1-5 cd /home/ubuntu/gamt-dashboard/skills/stock-monitor && /usr/bin/python3 stock_monitor.py >> /tmp/stock_monitor.log 2>&1
```
