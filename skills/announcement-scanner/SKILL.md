---
name: announcement-scanner
description: |
  公告扫描 Skill。每日自动扫描全市场上市公司公告，按关键词（并购/重组、处罚、增持、减持、定增、ST风险）分类汇总，推送飞书卡片。
  触发词：公告扫描、扫描公告、全市场公告、公告skill
---

# 全市场公告扫描器

每日盘后自动扫描全市场上市公司公告，按关键词分类推送飞书卡片。

## 功能

- **数据源**: iFinD MCP `search_notice`
- **关键词分类**: 并购重组、处罚、增持、减持、定增、ST风险
- **输出**: 飞书卡片（可折叠，按股票聚合）+ JSON 存档
- **前端**: 挂在个股监控页面 Tab 4

## 使用方式

### 手动执行

```bash
cd ~/Desktop/gamt-dashboard/skills/announcement-scanner

# 扫描今天的公告并发送飞书
python3 announcement_scanner.py --send

# 扫描指定日期
python3 announcement_scanner.py --date 2026-05-12 --send

# 只保存 JSON 不发飞书
python3 announcement_scanner.py --date 2026-05-12
```

### 定时任务（腾讯云）

```bash
# 每工作日 21:00 自动扫描
0 21 * * 1-5 cd /home/ubuntu/gamt-dashboard/skills/announcement-scanner && python3 announcement_scanner.py --send
```

### 前端查看

访问 `https://dashboard.gamtfof.com/skills/stock-monitor/stock_monitor.html`，切到 Tab 4 "全市场公告"，选择日期加载。

## 数据结构

### 输出 JSON

```json
{
  "date": "2026-05-12",
  "scan_time": "2026-05-12T21:00:00",
  "results": {
    "并购重组": {
      "中芯国际": [
        {
          "stock_name": "中芯国际",
          "title": "关于发行股份购买资产...",
          "raw_title": "中芯国际：中芯国际关于...",
          "pub_date": "2026-05-12",
          "snippet": "A股代码：688981...",
          "keyword": "并购"
        }
      ]
    },
    "处罚": {...},
    "增持": {...},
    "减持": {...},
    "定增": {...},
    "ST风险": {...}
  }
}
```

### 飞书卡片

- 可折叠面板，按类别展开
- 每个类别下按股票分组
- 显示"X 只股票，Y 条公告"

## 关键词配置

在 `announcement_scanner.py` 中修改 `KEYWORDS` 字典：

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
python3 announcement_scanner.py --send --chat-id <your_chat_id>
```

## 文件结构

```
skills/announcement-scanner/
├── announcement_scanner.py       # 主脚本
├── detail/                 # 每日数据存档（供前端读取）
│   └── 2026-05-12.json
├── SKILL.md               # 本文档
└── README.md              # 用户文档
```

## 依赖

- iFinD MCP（`~/.openclaw/extensions/ifind-finance-data/`）
- 飞书 App（App ID: `cli_a91c36caf5785cb2`）
- Python 3.x + requests

## 注意事项

- iFinD MCP 直连不需要代理，开代理反而可能超时
- 每个关键词最多返回 100 条公告（`size: 100`）
- 同一公告可能匹配多个关键词，已做去重
- 前端页面需要 Nginx/Cloudflare Tunnel 提供 HTTPS 访问
