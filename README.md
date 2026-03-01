# GAMT 投研看板

FOF 多策略投研仪表盘，覆盖宏观→中观→微观→策略环境的全链路监控。前端为静态 HTML（Cloudflare Pages 部署），后端为 Python 数据管道 + Cloudflare Tunnel 刷新服务。

## 项目结构

```
gamt-dashboard/
├── index.html              # 主看板入口
├── admin.html              # 用户管理后台
├── auth.py                 # 用户认证模块（SQLite + session）
├── update_all.py           # 一键更新全部模块
├── refresh_server.py       # 刷新 API 服务（端口 9876）
├── start_refresh.py        # 启动刷新服务 + Cloudflare Tunnel
├── overview_calc.py        # 概览页汇总各模块信号 → overview.json
│
├── macro/                  # 宏观层
│   ├── liquidity/          #   境内流动性（Shibor/DR007/M1M2）
│   ├── rates/              #   全球利率汇率（中美10Y/USDCNY）
│   └── fundamentals/       #   经济基本面（PMI/CPI/PPI/美林时钟）
│
├── macro_score/            # 宏观综合打分 + 策略适配度
│
├── meso/                   # 中观层
│   └── chain_prosperity/   #   产业链景气度（科技/创新药/周期/消费）
│
├── micro_flow/             # 微观资金流
│   ├── crowding/           #   拥挤度监控（北向/ETF/两融/行业热力图）
│   ├── option_sentiment/   #   期权情绪（IV/PCR/OI异常检测）
│   └── patient_capital/    #   耐心资本持筹（ETF 15min大单追踪）
│
├── env_fit/                # 策略环境适配度
│   ├── quant_stock/        #   宽基量化股票（因子表现/基差/波动率）
│   ├── momentum_stock/     #   强势股情绪（赚钱效应/连板/北向）
│   ├── commodity_cta/      #   商品CTA（趋势扫描/宏观比价/CTA环境）
│   ├── cb_env/             #   转债指增（活跃度/估值/DELTA/债底）
│   └── arbitrage/          #   套利（股指基差/商品比价/期权波动率）
│
├── size_spread/            # 风格轧差
│   └── fund_nav/           #   基金净值跟踪（各策略代表产品超额）
│
├── alerts/                 # 红灯预警（5维风险综合评分）
├── daily_report/           # 每日投研简报
└── smart-notes/            # 智能笔记
```

## 数据源

| 来源 | 用途 |
|------|------|
| Tushare Pro | A股/期货/期权/宏观/ETF 日线及分钟线 |
| iFind (同花顺) | 汇率实时行情、产业链高频数据 |
| 火富牛 (fof99) | 私募基金净值 |

## 更新流程

```bash
cd ~/Desktop/gamt-dashboard
python3 update_all.py          # 全量更新
python3 update_all.py --module quant_stock  # 单模块更新
python3 start_refresh.py       # 启动在线刷新服务
```

## 技术栈

- **前端**: 原生 HTML/JS + Chart.js，Cloudflare Pages 托管
- **后端**: Python 3 数据管道，SQLite 认证，Cloudflare Tunnel 暴露 API
- **数据存储**: CSV（真相源）+ JSON（中间产物）+ HTML（渲染产物）
