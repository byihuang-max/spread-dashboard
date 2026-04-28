#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - 配置文件
================================
统一管理：
  - 火富牛 API 密钥
  - GAMT 核心产品列表（28只，分7个策略组）
  - FOF 组合列表（6只，含2只隐藏）
  - 市场策略分类 ID
  - 策略分类 → 基准指数映射

修改产品列表后，重新运行 fetch_data.py + render_html.py 即可生效。
"""

import os, sys

# ========== 火富牛 API ==========
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

# ========== 路径 ==========
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(MODULE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")

# 火富牛 SDK（使用 GAMT 主看板已有的 SDK）
GAMT_ROOT = os.path.dirname(MODULE_DIR)
SDK_PATH = os.path.join(GAMT_ROOT, "mall_sdk")
if SDK_PATH not in sys.path:
    sys.path.insert(0, os.path.dirname(SDK_PATH))

# ========== GAMT 核心产品列表 ==========
# 28只产品，分7个策略组
# code: 火富牛产品编码（reg_code）
# group: 策略分组（量选类/风格类/绝对收益/商品类/多策略/FOF组合类）
# detail: 策略细分标签（展示用）
# color: 策略组主题色（核心资产卡片用）
PRODUCTS = [
    # --- 量选类 ---
    {"name": "顽岩量化选股1号",       "code": "SATW62", "group": "量选类", "detail": "量化选股",     "color": "#2f5ea8"},
    {"name": "正仁股票择时一期",       "code": "SARD76", "group": "量选类", "detail": "股票择时",     "color": "#2f5ea8"},
    # --- 风格类 ---
    {"name": "正仁双创择时一号",       "code": "SXG834", "group": "风格类", "detail": "双创择时",     "color": "#1f7a6b"},
    {"name": "瀚鑫纸鸢量化优选",       "code": "SZC020", "group": "风格类", "detail": "微盘择时",     "color": "#1f7a6b"},
    {"name": "积沐领航者",             "code": "SAJJ91", "group": "风格类", "detail": "1000指增",     "color": "#1f7a6b"},
    {"name": "太衍光年中证2000指数增强2号", "code": "SBCA75", "group": "风格类", "detail": "2000指增T0", "color": "#1f7a6b"},
    {"name": "时间序列红利增强1号",     "code": "SSV122", "group": "风格类", "detail": "红利指增",     "color": "#1f7a6b"},
    {"name": "赢仕安盈二号",           "code": "SLQ349", "group": "风格类", "detail": "转债集中",     "color": "#1f7a6b"},
    {"name": "具力芒种1号",            "code": "STE836", "group": "风格类", "detail": "转债分散",     "color": "#1f7a6b"},
    {"name": "玉数纯阿尔法一号",       "code": "SGN799", "group": "风格类", "detail": "300指增T0",   "color": "#1f7a6b"},
    {"name": "玉数顺利一号",           "code": "SNY231", "group": "风格类", "detail": "500指增T0",   "color": "#1f7a6b"},
    {"name": "玉数涵瑞专享十七号",     "code": "SZB966", "group": "风格类", "detail": "1000指增T0",  "color": "#1f7a6b"},
    {"name": "龙旗科技创新精选1号",     "code": "SACB34", "group": "风格类", "detail": "双创指增",     "color": "#1f7a6b"},
    {"name": "正仁择时量选听涛二号",    "code": "SBHP32", "group": "风格类", "detail": "灵活方向择时", "color": "#1f7a6b"},
    # --- 绝对收益 ---
    {"name": "旌安思源1号B类",         "code": "AEU46B", "group": "绝对收益", "detail": "短线择时",   "color": "#6a4c93"},
    {"name": "创世纪顾锝灵活多策略1号", "code": "SBDC67", "group": "绝对收益", "detail": "趋势策略",   "color": "#6a4c93"},
    {"name": "立心-私募学院菁英353号",  "code": "SCJ476", "group": "绝对收益", "detail": "主线择时",   "color": "#6a4c93"},
    {"name": "翔云50二号A类",          "code": "VB166A", "group": "绝对收益", "detail": "大盘择时",   "color": "#6a4c93"},
    {"name": "特夫郁金香全量化",        "code": "SQX078", "group": "绝对收益", "detail": "量化打板",   "color": "#6a4c93"},
    {"name": "玉数涵瑞六号",           "code": "SJD168", "group": "绝对收益", "detail": "300中性T0",  "color": "#6a4c93"},
    # --- 商品类 ---
    {"name": "铭跃行远均衡一号",       "code": "SVZ009", "group": "商品类", "detail": "量化时序CTA",  "color": "#a36a2b"},
    {"name": "碳硅1号",               "code": "SXJ836", "group": "商品类", "detail": "化工主观",     "color": "#a36a2b"},
    {"name": "涌泉君安三号",           "code": "SZM385", "group": "商品类", "detail": "黑色主观",     "color": "#a36a2b"},
    {"name": "海鹏扬帆",              "code": "SSR379", "group": "商品类", "detail": "农产品主观",   "color": "#a36a2b"},
    # --- 多策略 ---
    {"name": "格林基金鲲鹏6号",        "code": "SVZ638", "group": "多策略", "detail": "黄金大类",     "color": "#3c6e71"},
    {"name": "波克宏观配置1号",        "code": "SARZ77", "group": "多策略", "detail": "宏观大类",     "color": "#3c6e71"},
    # --- FOF组合类 ---
    {"name": "国联证券陆联1号FOF",     "code": "SAST37", "group": "FOF组合类", "detail": "低波私募FOF", "color": "#7b8794"},
]

# ========== FOF 组合列表 ==========
# 使用火富牛 /combi/price 接口（非基金接口）
# id: 火富牛组合 ID
# hidden: True 表示数据照常采集但前端不展示
COMBIS = [
    {"id": "c59639ceac9aca1f", "name": "大方向之中波思源365",       "group": "FOF组合类", "detail": "中波公募FOF"},
    {"id": "f3a5298b3ec32ce7", "name": "飞虹路-鑫益大方向1号",      "group": "FOF组合",   "detail": "FOF组合"},
    {"id": "bb24bad1d31a4173", "name": "长盛71号",                  "group": "FOF组合",   "detail": "FOF组合"},
    {"id": "ea21daabf8d35fd6", "name": "飞虹路-长盛65号",           "group": "FOF组合",   "detail": "FOF组合"},
    {"id": "63983e4cd5cdda5f", "name": "君宜安鑫",                  "group": "FOF组合",   "detail": "FOF组合", "hidden": True},
    {"id": "52b8287b5c62e21b", "name": "宁涌富春分8号（凌总）组合",  "group": "FOF组合",   "detail": "FOF组合", "hidden": True},
]

# ========== 市场策略基准 ==========
# 火富牛 /market/category 接口的策略分类 ID（1-16）
MARKET_IDS = "2,3,4,5,6,7,8,9,10,11,12,13,14,15,16"

# 需要走 platform 接口（FundPrice）而非 team 接口（FundCompanyPrice）的产品
# 这些产品在火富牛上没有团队净值，只有平台净值
PLATFORM_SOURCE_CODES = {"SZC020", "SSV122"}

# ========== 策略分类 → 基准指数 + 关联产品 ==========
# 用于策略详情弹窗中展示产品 vs 基准的对比
# 注意：这个映射是给旧版弹窗用的（展示具体产品净值）
# 新版弹窗使用 fetch_strategy_curves.py 的策略分类平均收益曲线
# benchmark=None 表示该策略只展示绝对收益
STRATEGY_BENCHMARK = {
    # 权益多头组
    8:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SGN799"]},
    9:  {"benchmark": "000905", "benchmark_name": "中证500",  "products": ["SNY231"]},
    10: {"benchmark": "000852", "benchmark_name": "中证1000", "products": ["SAJJ91", "SZB966"]},
    7:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SARD76", "SATW62", "SBHP32"]},
    6:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SXG834", "SACB34"]},
    16: {"benchmark": "000985", "benchmark_name": "中证全指", "products": ["SLQ349", "STE836"]},
    # 对冲中性组
    5:  {"benchmark": "000300", "benchmark_name": "沪深300",  "products": ["SJD168"]},
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
