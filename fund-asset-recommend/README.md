# 团队基金优选模块

GAMT 看板子模块，展示团队跟踪的私募产品、FOF 组合和市场策略基准。

## 架构

```
fund-asset-recommend/
├── fund_asset.html              # 最终页面（自动生成，勿手动编辑）
├── fund_asset_template.html     # HTML 模板（含占位符）
├── scripts/
│   ├── config.py                # 产品列表 + API 密钥
│   ├── fetch_data.py            # 数据采集（火富牛 API → JSON）
│   └── render_html.py           # 渲染（JSON + 模板 → HTML）
├── data/
│   ├── fund_asset_latest.json   # 最新数据（fetch_data.py 输出）
│   └── raw/                     # 历史快照（按日期归档）
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

## 数据源

- **API**: 火富牛 `mallapi.huofuniu.com`（直连，不走代理）
- **密钥**: 见 `config.py`（APP_ID / APP_KEY）
