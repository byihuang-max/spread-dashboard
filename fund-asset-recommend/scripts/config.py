#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - 配置文件
================================
统一管理：
  - 火富牛 API 密钥
  - 产品池（从 fund_asset_pool.json 动态读取，仅 approved 状态进入正式池）
  - 市场策略分类 ID
  - 策略分类 → 基准指数映射

产品池管理流程：
  团队提交(pending) → API验证(verified/failed) → 管理员审核(approved/rejected) → 正式池
  种子产品(seed=true) 始终保留，不可删除。

修改产品池后，重新运行 fetch_data.py + render_html.py 即可生效。
"""

import os, sys, json

# ========== 火富牛 API ==========
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

# ========== 路径 ==========
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(MODULE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
POOL_PATH = os.path.join(DATA_DIR, "fund_asset_pool.json")

# 火富牛 SDK（使用 GAMT 主看板已有的 SDK）
GAMT_ROOT = os.path.dirname(MODULE_DIR)
SDK_PATH = os.path.join(GAMT_ROOT, "mall_sdk")
if SDK_PATH not in sys.path:
    sys.path.insert(0, os.path.dirname(SDK_PATH))


# ========== 产品池读取 ==========

def _load_pool():
    """读取产品池 JSON"""
    if os.path.exists(POOL_PATH):
        with open(POOL_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"products": [], "combis": []}


def _save_pool(pool):
    """写入产品池 JSON"""
    os.makedirs(os.path.dirname(POOL_PATH), exist_ok=True)
    with open(POOL_PATH, 'w', encoding='utf-8') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)


def get_approved_products():
    """获取正式池产品（status=approved）"""
    pool = _load_pool()
    return [p for p in pool.get("products", []) if p.get("status") == "approved"]


def get_approved_combis():
    """获取正式池组合（status=approved）"""
    pool = _load_pool()
    return [c for c in pool.get("combis", []) if c.get("status") == "approved"]


def get_all_pool():
    """获取完整产品池（含所有状态，管理后台用）"""
    return _load_pool()


def add_to_pool(item, item_type="product"):
    """添加产品/组合到池子"""
    pool = _load_pool()
    key = "products" if item_type == "product" else "combis"
    code_field = "code" if item_type == "product" else "id"

    # 检查重复
    existing_codes = {p.get(code_field) for p in pool[key]}
    if item.get(code_field) in existing_codes:
        return False, f"产品 {item.get(code_field)} 已存在"

    pool[key].append(item)
    _save_pool(pool)
    return True, "添加成功"


def update_pool_item(code, updates, item_type="product"):
    """更新池子中某个产品的字段"""
    pool = _load_pool()
    key = "products" if item_type == "product" else "combis"
    code_field = "code" if item_type == "product" else "id"

    for item in pool[key]:
        if item.get(code_field) == code:
            item.update(updates)
            _save_pool(pool)
            return True, "更新成功"
    return False, f"未找到 {code}"


def remove_from_pool(code, item_type="product"):
    """从池子中移除产品（种子产品不可删除，只能标记 removed）"""
    pool = _load_pool()
    key = "products" if item_type == "product" else "combis"
    code_field = "code" if item_type == "product" else "id"

    for item in pool[key]:
        if item.get(code_field) == code:
            if item.get("seed"):
                return False, "种子产品不可删除"
            item["status"] = "removed"
            _save_pool(pool)
            return True, "已下架"
    return False, f"未找到 {code}"


# ========== 兼容层：PRODUCTS / COMBIS 变量 ==========
# fetch_data.py 和 render_html.py 通过 from config import PRODUCTS, COMBIS 使用
# 这里动态生成，只包含 approved 状态的产品

PRODUCTS = get_approved_products()
COMBIS = get_approved_combis()


# ========== 策略组配色（新增产品时自动匹配） ==========
GROUP_COLORS = {
    "量选类": "#2f5ea8",
    "风格多头": "#1f7a6b",
    "绝对收益": "#6a4c93",
    "商品类": "#a36a2b",
    "多策略": "#3c6e71",
    "FOF组合类": "#7b8794",
    "FOF组合": "#7b8794",
}


# ========== 市场策略基准 ==========
# 火富牛 /market/category 接口的策略分类 ID（1-16）
MARKET_IDS = "2,3,4,5,6,7,8,9,10,11,12,13,14,15,16"

# 需要走 platform 接口（FundPrice）而非 team 接口（FundCompanyPrice）的产品
# 这些产品在火富牛上没有团队净值，只有平台净值
PLATFORM_SOURCE_CODES = {"SZC020", "SSV122"}

# ========== 策略分类 → 基准指数 + 关联产品 ==========
STRATEGY_BENCHMARK = {
    # 风格多头组
    8:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SGN799"]},
    9:  {"benchmark": "000905", "benchmark_name": "中证500",  "products": ["SNY231"]},
    10: {"benchmark": "000852", "benchmark_name": "中证1000", "products": ["SAJJ91", "SZB966"]},
    7:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SATW62"]},
    6:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SACB34"]},
    16: {"benchmark": "000985", "benchmark_name": "中证全指", "products": ["SLQ349", "STE836"]},
    17: {"benchmark": "932000", "benchmark_name": "中证2000", "products": ["SBCA75"]},
    18: {"benchmark": "000922", "benchmark_name": "中证红利", "products": ["SSV122"]},
    # 对冲中性组
    5:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": []},
    4:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": []},
    11: {"benchmark": "000905", "benchmark_name": "中证500",  "products": []},
    12: {"benchmark": "000300", "benchmark_name": "沪深300",  "products": []},
    # 债券组
    15: {"benchmark": None,     "benchmark_name": None,       "products": []},
    # 另类策略组
    2:  {"benchmark": None,     "benchmark_name": None,       "products": ["SVZ009"]},
    3:  {"benchmark": None,     "benchmark_name": None,       "products": ["SXJ836", "SZM385", "SSR379"]},
    13: {"benchmark": None,     "benchmark_name": None,       "products": ["SVZ638", "SARZ77"]},
    14: {"benchmark": None,     "benchmark_name": None,       "products": ["SAST37"]},
}
