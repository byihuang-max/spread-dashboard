# 团队基金优选模块

GAMT 看板子模块，展示团队跟踪的私募产品、FOF 组合和市场策略基准。

## 架构

```
fund-asset-recommend/
├── fund_asset.html              # 最终页面（自动生成，勿手动编辑）
├── fund_asset_template.html     # HTML 模板（含占位符）
├── scripts/
│   ├── config.py                # 产品列表 + API 密钥
│   ├── fetch_data.py            # 数据采集（火富牛 API → JSON + CSV）
│   ├── render_html.py           # 渲染（JSON + 模板 → HTML）
│   └── README.md                # 脚本详细说明
├── data/
│   ├── fund_asset_latest.json   # 最新全量数据（渲染用，每次覆盖）
│   ├── fund_asset_history.jsonl # JSON Lines 增量（每天追加一行）
│   ├── products_history.csv     # 产品净值快照 CSV（每天追加，UTF-8 BOM）
│   ├── fof_history.csv          # FOF 组合快照 CSV（每天追加，UTF-8 BOM）
│   └── raw/                     # JSON 日快照（按日期归档）
└── README.md
```

## 数据流

```
火富牛 API ──→ fetch_data.py ──→ fund_asset_latest.json ──→ render_html.py ──→ fund_asset.html
```

## 运行

```bash
cd ~/Desktop/gamt-dashboard/fund-asset-recommend/scripts
/opt/homebrew/bin/python3 fetch_data.py    # 拉取最新数据
/opt/homebrew/bin/python3 render_html.py   # 生成 HTML
```

已注册到 `module_registry.py`，`update_all.py` 日更时自动执行。

## 覆盖范围

- **27 只私募产品**：量选 / 风格 / 绝对收益 / 商品 / 多策略 / FOF组合类（7 个策略组）
- **6 个 FOF 模拟组合**：含净值曲线、回撤、夏普等完整指标
- **16 个市场策略基准**：年度 / 月度 / 季度收益分位

## 数据存储策略

| 文件 | 模式 | 用途 |
|------|------|------|
| `fund_asset_latest.json` | 覆盖 | 渲染 HTML 用，始终是最新一次 |
| `raw/fund_asset_YYYYMMDD.json` | 快照 | 每天一个完整 JSON，可回溯任意一天 |
| `fund_asset_history.jsonl` | 追加 | 每天一行 JSON，程序读取历史方便 |
| `products_history.csv` | 追加 | 产品净值快照，Excel/飞书可直接打开 |
| `fof_history.csv` | 追加 | FOF 组合快照，Excel/飞书可直接打开 |

CSV 使用 UTF-8 with BOM 编码，Excel 打开不会中文乱码。

## 数据源

- **API**: 火富牛 `mallapi.huofuniu.com`（直连，不走代理）
- **密钥**: 见 `config.py`（APP_ID / APP_KEY）
