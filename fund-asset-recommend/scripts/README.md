# scripts/ — 数据管道

## config.py — 配置中心

定义所有常量，其他脚本只从这里读配置。

| 配置项 | 说明 |
|--------|------|
| `APP_ID` / `APP_KEY` | 火富牛 API 密钥 |
| `BASE_URL` | API 地址 `mallapi.huofuniu.com` |
| `PRODUCTS` | 27 只跟踪产品列表（code / name / group / detail / color） |
| `COMBIS` | 6 个 FOF 模拟组合（id / name / group） |
| `MARKET_IDS` | 16 个市场策略基准 ID |
| `PLATFORM_SOURCE_CODES` | 平台源产品代码（SZC020, SSV122），用不同 API 路径拉取 |

新增/删除产品只需改这个文件。

---

## fetch_data.py — 数据采集

从火富牛 API 拉取全部数据，计算收益指标，输出 JSON。

### 主要函数

| 函数 | 作用 |
|------|------|
| `api_sign()` | HMAC-MD5 签名 |
| `api_get()` | 通用 API 请求（签名 + 重试） |
| `fetch_fund_nav_history()` | 拉单只产品净值历史 |
| `fetch_all_products()` | 批量拉 27 只产品 |
| `fetch_combi_nav()` | 拉单个组合净值 |
| `fetch_all_combis()` | 批量拉 6 个组合 |
| `fetch_market_data()` | 拉 16 个策略基准（年/月/季） |
| `compute_fund_metrics()` | 从净值序列计算周/月/YTD 收益、夏普、最大回撤等 |
| `build_strategy_summary()` | 按策略组聚合产品，生成前端需要的 `strategySummary` 结构 |
| `build_fof_combis()` | 构建 FOF 组合详情（含净值曲线、月度收益、回撤等） |
| `save_data()` | 输出 `fund_asset_latest.json` + 按日期归档 |

### 输出 JSON 结构

```json
{
  "update_time": "2026-04-28 12:15:34",
  "strategy_summary": [...],   // 7 个策略组，每组含 items
  "market_data": {
    "annual": [...],           // 16 个策略基准（年度）
    "monthly": [...],          // 月度
    "quarterly": [...]         // 季度
  },
  "fof_combis": [...],        // 5 个 FOF 组合详情
  "nav_history": {             // code → [[date, nav], ...]
    "SAST37": [["2024-01-05", 1.0], ...],
    ...
  }
}
```

---

## render_html.py — HTML 渲染

读取 JSON 数据 + HTML 模板，注入数据生成最终页面。

### 主要函数

| 函数 | 作用 |
|------|------|
| `flatten_market_data()` | API 嵌套结构 → v3 扁平结构（`return.mean` → `ret_mean`），合并月度/季度 |
| `build_rows()` | 从 `strategy_summary` 构建产品表格行数据 |
| `render()` | 主函数：读模板 → 注入 11 个占位符 → 写 HTML |

### 模板占位符

| 占位符 | 注入内容 |
|--------|----------|
| `/*__ROWS_DATA__*/` | 产品表格数据 |
| `/*__STRATEGY_SUMMARY__*/` | 策略组摘要 |
| `/*__MARKET_DATA__*/` | 市场策略基准（扁平化后） |
| `/*__FOF_COMBIS__*/` | FOF 组合详情 |
| `/*__NAV_HISTORY__*/` | 净值曲线历史 |
| `/*__UPDATE_DATE__*/` | 数据日期 |
| `/*__MARKET_SUBTITLE__*/` | 市场策略副标题 |
| `/*__MARKET_NOTE__*/` | 市场策略说明 |
| `/*__CORE_SUBTITLE__*/` | 核心资产副标题 |
| `/*__FOF_SUBTITLE__*/` | FOF 副标题 |
| `/*__FOF_NOTE__*/` | FOF 说明 |
| `/*__ANNUAL_RANGE__*/` | 年度滚动区间 |

### 依赖

- `python-dateutil`（`relativedelta` 计算日期区间）
