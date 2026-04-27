# 团队基金优选模块

GAMT 看板子模块，跟踪团队核心私募产品业绩。

## 目录结构

```
fund-asset-recommend/
├── scripts/
│   ├── config.py          # 统一配置（API密钥、产品列表、路径）
│   └── fetch_data.py      # 数据采集主脚本（一个文件搞定）
├── data/
│   ├── fund_asset_latest.json   # 最新数据（每次覆盖）
│   ├── raw/                     # 带日期的历史快照
│   └── archive/                 # 原始文件归档（勿动）
│       ├── original_scripts/    # 原始70个py脚本
│       ├── html_versions/       # 原始23个HTML版本
│       └── *.csv/*.xlsx/*.json  # 原始数据文件
└── sdk/
    └── huofuniu-sdk-original/   # 原始SDK备份（与主看板SDK一致）
```

## 使用

```bash
cd ~/Desktop/gamt-dashboard/fund-asset-recommend/scripts
python3 fetch_data.py
```

一个脚本完成：产品净值采集 → 组合净值采集 → 市场基准采集 → 收益计算 → JSON输出。

## 数据覆盖

- 27只基金产品（7个策略组）
- 6个FOF组合
- 16个市场策略基准

## 数据源

火富牛 API（mallapi.huofuniu.com），使用主看板已有的 fof99 SDK。

## 后续

- [ ] 生成 HTML 页面，接入 GAMT 主看板
- [ ] 接入 update_all.py 日更链路
