# 公告扫描 Skill

每日自动扫描全市场上市公司公告，按关键词分类推送飞书。

## 快速开始

```bash
cd ~/Desktop/gamt-dashboard/skills/announcement-scanner

# 扫描今天的公告并发送飞书
python3 market_scanner.py --send

# 扫描指定日期
python3 market_scanner.py --date 2026-05-12 --send
```

## 功能特性

- ✅ 自动扫描全市场公告（数据源：iFinD MCP）
- ✅ 6 大类关键词分类：并购重组、处罚、增持、减持、定增、ST风险
- ✅ 按股票聚合展示（同一股票的多条公告合并）
- ✅ 飞书卡片推送（可折叠面板）
- ✅ 前端页面查看（挂在个股监控 Tab 4）
- ✅ JSON 数据存档

## 扫描结果示例

**2026-05-12 扫描结果：**
- 并购重组：14 只股票，23 条公告
- 处罚：34 只股票，40 条公告
- 增持：11 只股票，16 条公告
- 减持：20 只股票，23 条公告
- 定增：20 只股票，21 条公告
- ST风险：13 只股票，18 条公告
- **总计：112 只股票，141 条公告**

## 前端查看

访问 https://dashboard.gamtfof.com/skills/stock-monitor/stock_monitor.html

切到 Tab 4 "全市场公告"，选择日期加载。

## 定时任务

腾讯云 crontab：

```bash
# 每工作日 21:00 自动扫描
0 21 * * 1-5 cd /home/ubuntu/gamt-dashboard/skills/announcement-scanner && python3 market_scanner.py --send
```

## 关键词配置

在 `market_scanner.py` 中修改 `KEYWORDS` 字典：

```python
KEYWORDS = {
    "并购重组": ["并购", "重组", "收购", "资产注入", "吸收合并", "要约收购"],
    "处罚": ["处罚", "立案", "调查", "违规", "警示函", "监管函"],
    "增持": ["增持", "买入", "购买股份"],
    "减持": ["减持", "出售股份", "股份转让"],
    "定增": ["定向增发", "非公开发行", "增发", "配股"],
    "ST风险": ["ST", "*ST", "退市风险", "暂停上市", "终止上市"]
}
```

## 推送目标

默认推送到 RONIHUANG BOT 群（`oc_1e941df394190b21d4c4edd83deae4f3`）。

修改推送目标：

```bash
python3 market_scanner.py --send --chat-id <your_chat_id>
```

## 数据存档

每日扫描结果自动保存到 `detail/YYYY-MM-DD.json`，供前端页面读取。

## 依赖

- iFinD MCP（`~/.openclaw/extensions/ifind-finance-data/`）
- 飞书 App（App ID: `cli_a91c36caf5785cb2`）
- Python 3.x + requests

## 注意事项

- iFinD MCP 直连不需要代理，开代理反而可能超时
- 每个关键词最多返回 100 条公告（`size: 100`）
- 同一公告可能匹配多个关键词，已做去重
- 同一股票的多条公告会聚合在一起展示

## 技术架构

```
market_scanner.py
  ├─ scan_market_announcements()  # 扫描 + 聚合
  ├─ build_feishu_card()          # 构建飞书卡片
  ├─ send_feishu_msg()            # 发送飞书
  └─ main()                       # CLI 入口

detail/
  └─ YYYY-MM-DD.json              # 每日数据存档

前端（stock_monitor.html Tab 4）
  └─ renderScannerData()          # 渲染公告列表
```

## 开发者

- 作者：雷军（AI 量化策略研发搭档）
- 项目：GAMT 投研看板
- 日期：2026-05-12
