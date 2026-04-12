# 经济基本面新增图表 — iFind 字段映射草案 V1

目标：把“经济基本面”新增 4 张主图，从抽象指标层推进到**可编码的数据字段层**。  
说明：以下先用**标准化字段名 + iFind 检索方向/口径说明**来定结构；等实际调用 iFind 时，再把对应 EDB 代码/接口字段补齐固化。

---

## 一、总原则

### 1. 数据源优先级
- **主源：iFind**
- **兜底：Tushare / 现有缓存**
- 页面最终不要绑定源字段名，只绑定统一后的内部字段名。

### 2. 输出目标
最终 `fundamentals.json` 中新增四个区块：
- `growth_breakdown`
- `credit_structure`
- `property_recovery`
- `inventory_cycle`

每个区块都至少包含：
- `status`
- `summary`
- `series`
- `latest`

### 3. 频率原则
- 主框架优先用**月度数据**，保证与当前“月度结论卡”一致
- 高频数据只做验证层，不抢主叙事

---

# 二、图1：增长总量拆解图

## 图的目标
回答：**当前增长修复，是全面扩散，还是单链条修复？**

## 统一内部字段

| 内部字段名 | 中文名 | 推荐频率 | iFind 检索方向 | 备注 |
|---|---|---:|---|---|
| industrial_production_yoy | 工业增加值同比 | 月度 | 宏观月度-工业增加值-当月同比 | 制造/生产总量修复 |
| retail_sales_yoy | 社零同比 | 月度 | 宏观月度-社会消费品零售总额-当月同比 | 消费需求修复 |
| exports_yoy | 出口同比 | 月度 | 海关进出口-出口金额-同比 | 外需支撑 |
| fai_ytd_yoy | 固定资产投资累计同比 | 月度 | 固定资产投资完成额-累计同比 | 总投资强弱 |
| manufacturing_investment_ytd_yoy | 制造业投资累计同比 | 月度 | 制造业固定资产投资-累计同比 | 企业扩产意愿 |
| infrastructure_investment_ytd_yoy | 基建投资累计同比 | 月度 | 基础设施建设投资-累计同比 | 政策投资托底 |
| real_estate_investment_ytd_yoy | 地产投资累计同比 | 月度 | 房地产开发投资完成额-累计同比 | 地产拖累/修复 |

## iFind 检索口径建议
优先找以下口径：
- **同比 / 累计同比** 优先
- 若同一指标有“当月同比”和“累计同比”，优先：
  - 工增、社零、出口 → 当月同比
  - 固投及拆分 → 累计同比

## JSON 草案
```json
{
  "growth_breakdown": {
    "status": "结构修复",
    "summary": "工业与出口改善，但消费与投资跟进仍有限。",
    "latest": {
      "industrial_production_yoy": 5.4,
      "retail_sales_yoy": 3.1,
      "exports_yoy": 7.8,
      "fai_ytd_yoy": 4.0
    },
    "series": [
      {
        "date": "2026-03",
        "industrial_production_yoy": 5.4,
        "retail_sales_yoy": 3.1,
        "exports_yoy": 7.8,
        "fai_ytd_yoy": 4.0
      }
    ]
  }
}
```

## 状态判断建议
- **全面修复**：工增、社零、固投至少三项同步改善，出口不拖累
- **结构修复**：工业/出口好于消费/投资，或消费改善但地产投资明显拖累
- **偏弱**：工增、社零、固投多数仍偏弱

---

# 三、图2：信用结构拆解图

## 图的目标
回答：**这轮信用扩张，有没有真正进入实体和内生需求？**

## 统一内部字段

| 内部字段名 | 中文名 | 推荐频率 | iFind 检索方向 | 备注 |
|---|---|---:|---|---|
| tsf_stock_yoy | 社融存量同比 | 月度 | 社会融资规模存量-同比 | 宽信用总方向 |
| tsf_flow | 新增社融 | 月度 | 社会融资规模增量-当月值 | 当期信用投放强度 |
| gov_bond_financing | 政府债融资 | 月度 | 社融分项-政府债券融资 | 政策托底强度 |
| corp_medium_long_loan | 企业中长期贷款 | 月度 | 金融机构人民币贷款-企业中长期贷款新增 | 企业融资扩张 |
| household_medium_long_loan | 居民中长期贷款 | 月度 | 金融机构人民币贷款-居民中长期贷款新增 | 居民长期信用意愿 |
| bill_financing | 票据融资 | 月度 | 金融机构人民币贷款-票据融资新增 | 冲量/空转识别 |
| m1_yoy | M1同比 | 月度 | 货币供应量M1-同比 | 企业活化程度 |
| m2_yoy | M2同比 | 月度 | 货币供应量M2-同比 | 总货币宽松程度 |
| m1_m2_scissors | M1-M2剪刀差 | 月度 | 计算字段 | 信用活化程度 |

## iFind 检索口径建议
- 社融尽量统一使用**央行官方月度口径**
- 企业/居民中长期贷款优先用**当月新增**，更能看边际变化
- 票据融资若波动太大，可附带 3M MA 用于展示平滑

## JSON 草案
```json
{
  "credit_structure": {
    "status": "托底扩张",
    "summary": "社融改善主要由政府债驱动，居民与企业中长期融资仍待确认。",
    "latest": {
      "tsf_stock_yoy": 8.7,
      "tsf_flow": 48000,
      "gov_bond_financing": 12000,
      "corp_medium_long_loan": 15000,
      "household_medium_long_loan": 1800,
      "bill_financing": 9000,
      "m1_yoy": 1.2,
      "m2_yoy": 6.8,
      "m1_m2_scissors": -5.6
    },
    "series_main": [],
    "series_breakdown": []
  }
}
```

## 状态判断建议
- **有效扩张**：社融改善 + 企业中长贷改善 + 居民中长贷改善，票据非主导
- **托底扩张**：政府债主导，企业/居民跟进不足
- **空转扩张**：票据融资占比偏高，M1-M2无明显改善
- **信用偏弱**：社融和结构项普遍弱

---

# 四、图3：地产修复验证图

## 图的目标
回答：**地产是政策托底，还是已经开始真实止血？**

## 统一内部字段

| 内部字段名 | 中文名 | 推荐频率 | iFind 检索方向 | 备注 |
|---|---|---:|---|---|
| property_sales_area_yoy | 商品房销售面积同比 | 月度 | 商品房销售面积-累计同比/当月同比 | 地产需求修复 |
| real_estate_investment_yoy | 房地产开发投资同比 | 月度 | 房地产开发投资完成额-累计同比 | 地产投资端 |
| household_medium_long_loan | 居民中长期贷款 | 月度 | 金融机构人民币贷款-居民中长期贷款新增 | 居民购房信用意愿 |
| housing_starts_yoy | 房屋新开工面积同比 | 月度 | 房屋新开工面积-累计同比 | 开发商信心 |
| housing_completion_yoy | 房屋竣工面积同比 | 月度 | 房屋竣工面积-累计同比 | 保交楼/后周期 |
| city30_property_sales_yoy | 30大中城市商品房成交面积同比 | 周/日 | 高频地产成交 | 高频验证层 |

## iFind 检索口径建议
- 主图优先用月度口径，减少高频噪声
- 销售面积可以优先考虑**累计同比**，若希望更敏感可同时缓存当月同比
- 高频 30 城成交仅作为增强，不应替代月度主判断

## JSON 草案
```json
{
  "property_recovery": {
    "status": "政策托底",
    "summary": "销售阶段性改善，但投资和居民中长期贷款尚未同步转强。",
    "latest": {
      "property_sales_area_yoy": -8.2,
      "real_estate_investment_yoy": -10.6,
      "household_medium_long_loan": 1800,
      "housing_starts_yoy": -22.5,
      "housing_completion_yoy": 14.2
    },
    "series": []
  }
}
```

## 状态判断建议
- **弱修复**：销售改善 + 居民中长贷回暖 + 投资跌幅收窄
- **低位企稳**：销售不再恶化，投资仍弱但边际趋稳
- **政策托底**：销售/高频成交短反弹，但居民中长贷和投资未同步改善
- **继续探底**：销售、投资、居民中长贷均弱

---

# 五、图4：库存周期验证图

## 图的目标
回答：**价格修复有没有传导到企业经营和景气？**

## 统一内部字段

| 内部字段名 | 中文名 | 推荐频率 | iFind 检索方向 | 备注 |
|---|---|---:|---|---|
| ppi_yoy | PPI同比 | 月度 | 工业生产者出厂价格指数-同比 | 价格修复方向 |
| finished_goods_inventory_yoy | 产成品库存同比 | 月度 | 工业企业产成品存货-同比 | 企业库存行为 |
| industrial_profit_ytd_yoy | 工业企业利润累计同比 | 月度 | 规模以上工业企业利润总额-累计同比 | 盈利传导 |
| pmi_finished_goods_inventory | PMI产成品库存 | 月度 | 制造业PMI-产成品库存分项 | 企业库存预期 |
| pmi_raw_material_inventory | PMI原材料库存 | 月度 | 制造业PMI-原材料库存分项 | 备货意愿 |

## iFind 检索口径建议
- 利润数据如果发布滞后明显，前端应允许与 PPI/库存数据存在一个月错位
- 若产成品库存同比难稳定获取，可先以工业企业存货相关口径替代，但字段名保持不变

## JSON 草案
```json
{
  "inventory_cycle": {
    "status": "被动去库",
    "summary": "PPI边际改善，但库存与盈利传导仍不充分，景气修复尚未全面展开。",
    "latest": {
      "ppi_yoy": -0.9,
      "finished_goods_inventory_yoy": 4.8,
      "industrial_profit_ytd_yoy": -1.5,
      "pmi_finished_goods_inventory": 47.2,
      "pmi_raw_material_inventory": 48.1
    },
    "series": []
  }
}
```

## 状态判断建议
- **主动补库**：PPI改善 + 库存回升 + 利润改善
- **被动补库**：价格改善、库存回升，但利润传导有限
- **被动去库**：价格仍弱、库存回落或高位消化、盈利承压
- **主动去库**：企业主动压库存，景气预期偏弱

---

# 六、前端落地建议

## 页面位置
- 第一屏：保留现有美林时钟 + 月度结论卡
- 第二屏：
  - 左：增长总量拆解图
  - 右：信用结构拆解图
- 第三屏：
  - 左：地产修复验证图
  - 右：库存周期验证图
- 第四屏后：保留现有 PMI / CPI-PPI / 利润周期 / 内需接棒

## 前端字段消费建议
每张图统一读取：
- `status`
- `summary`
- `latest`
- `series`

这样前端只负责展示，不负责业务判断。

---

# 七、下一步建议

## Step 1
先去 iFind 确认上述字段对应的**真实可用指标代码/字段名**。

## Step 2
写一个新的数据层脚本，优先产出：
- `growth_breakdown`
- `credit_structure`
- `property_recovery`
- `inventory_cycle`

## Step 3
在 `fundamentals_calc.py` 中把这些区块合并进 `fundamentals.json`。

## Step 4
最后再改 `fundamentals.html`，把新增图表前置展示。

---

# 八、结论

到这一步，经济基本面模块的新增图表已经从“想法层”推进到“可编码字段层”。  
剩下的核心工作，不再是讨论框架，而是：

1. 对接 iFind 实际字段
2. 产出结构化 JSON
3. 前端接图
