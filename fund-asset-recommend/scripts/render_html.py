#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - HTML 渲染器
================================
读取 fund_asset_latest.json + strategy_curves.json，
注入到 fund_asset_template.html 模板，生成最终的 fund_asset.html。

数据流：
  fetch_data.py → fund_asset_latest.json  ─┐
  fetch_strategy_curves.py → strategy_curves.json ─┤→ render_html.py → fund_asset.html
  fund_asset_template.html ─────────────────┘

模板占位符说明：
  /*__ROWS_DATA__*/[]          核心资产表格行数据
  /*__STRATEGY_SUMMARY__*/[]   策略分组摘要（核心资产卡片用）
  /*__MARKET_DATA__*/[]        市场策略基准年度数据（扁平化后）
  /*__MARKET_MONTHLY__*/[]     市场策略基准月度数据
  /*__MARKET_QUARTERLY__*/[]   市场策略基准季度数据
  /*__MARKET_META__*/{}        各周期的副标题/区间文案
  /*__FOF_COMBIS__*/[]         FOF 组合数据
  /*__NAV_HISTORY__*/{}        产品净值历史（code → [[date, nav], ...]）
  /*__BENCHMARK_NAVS__*/{}     基准指数净值
  /*__STRATEGY_BENCHMARK__*/{} 策略→基准映射（config.py 中定义）
  /*__STRATEGY_CHARTS__*/{}    策略环境代表产品净值曲线（fund_nav.json）
  /*__STRATEGY_CURVES__*/{}    策略分类月度累计收益曲线（自建）
  /*__UPDATE_DATE__*/          数据更新日期
  /*__MARKET_SUBTITLE__*/      市场策略看板副标题
  /*__CORE_SUBTITLE__*/        核心资产副标题
  /*__FOF_SUBTITLE__*/         FOF 组合副标题
  等日期注释占位符

使用方式：
  python3 render_html.py
"""

import json, os, re
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(MODULE_DIR, 'fund_asset_template.html')
DATA_PATH = os.path.join(MODULE_DIR, 'data', 'fund_asset_latest.json')
OUTPUT_PATH = os.path.join(MODULE_DIR, 'fund_asset.html')


# 火富牛策略分类 id → v3 HTML 的策略分组名
# 用于 flatten_market_data 中给每条记录打 group 标签
GROUP_MAP = {5: '股票策略', 10: '股票策略', 9: '股票策略', 8: '股票策略', 7: '股票策略',
             4: '股票策略', 6: '股票策略', 2: '期货策略', 3: '期货策略',
             11: '其他策略', 12: '其他策略', 13: '其他策略', 15: '其他策略', 14: '其他策略', 16: '其他策略'}


def flatten_market_data(raw_list, monthly_list=None, quarterly_list=None):
    """
    把火富牛 API 返回的嵌套结构转成 v3 HTML 需要的扁平结构。
    API 返回: {return: {mean, median, ten, ...}, sp_return_data: {...}, ...}
    v3 需要: {ret_mean, ret_median, ret_10, sp_mean, sp_median, ...}
    同时合并月度/季度收益到 month_mean / quarter_mean 字段。
    """
    # 建立月度/季度索引
    monthly_map = {}
    for item in (monthly_list or []):
        ret = item.get('return', {})
        monthly_map[item.get('id')] = {'month_mean': ret.get('mean', 0), 'month_profit': ret.get('profit_rate', 0)}
    quarterly_map = {}
    for item in (quarterly_list or []):
        ret = item.get('return', {})
        quarterly_map[item.get('id')] = {'quarter_mean': ret.get('mean', 0), 'quarter_profit': ret.get('profit_rate', 0)}

    result = []
    for item in raw_list:
        # 如果已经是扁平结构（旧缓存），直接用
        if 'ret_mean' in item:
            result.append(item)
            continue

        flat = {
            'id': item.get('id'),
            'name': item.get('name', ''),
            'group': GROUP_MAP.get(item.get('id'), '其他策略'),
        }
        ret = item.get('return', {})
        flat['count'] = ret.get('count', 0)
        flat['ret_mean'] = ret.get('mean', 0)
        flat['ret_median'] = ret.get('median', 0)
        flat['ret_10'] = ret.get('ten', 0)
        flat['ret_25'] = ret.get('tf', 0)
        flat['ret_75'] = ret.get('sf', 0)
        flat['ret_90'] = ret.get('ninety', 0)
        flat['profit_rate'] = ret.get('profit_rate', 0)
        sp = item.get('sp_return_data', {})
        flat['sp_mean'] = sp.get('mean', 0)
        flat['sp_median'] = sp.get('median', 0)
        flat['sp_10'] = sp.get('ten', 0)
        flat['sp_90'] = sp.get('ninety', 0)
        md = item.get('md_return_data', {})
        flat['md_mean'] = md.get('mean', 0)
        flat['md_median'] = md.get('median', 0)
        flat['md_10'] = md.get('ten', 0)
        flat['md_90'] = md.get('ninety', 0)
        vol = item.get('vol_return_data', {})
        flat['vol_mean'] = vol.get('mean', 0)
        flat['vol_median'] = vol.get('median', 0)
        flat['vol_10'] = vol.get('ten', 0)
        flat['vol_90'] = vol.get('ninety', 0)
        cal = item.get('calmar_return_data', {})
        flat['cal_mean'] = cal.get('mean', 0)
        flat['cal_median'] = cal.get('median', 0)
        flat['cal_10'] = cal.get('ten', 0)
        flat['cal_90'] = cal.get('ninety', 0)
        # 月度/季度从对应数据合并
        mid = item.get('id')
        m = monthly_map.get(mid, {})
        flat['month_mean'] = m.get('month_mean', 0)
        flat['month_profit'] = m.get('month_profit', 0)
        q = quarterly_map.get(mid, {})
        flat['quarter_mean'] = q.get('quarter_mean', 0)
        flat['quarter_profit'] = q.get('quarter_profit', 0)

        result.append(flat)
    return result


def build_nav_history(strategy_summary):
    """从 strategy_summary 中提取各产品的净值历史（code → [[date, nav], ...]）"""
    nav_history = {}
    for group in strategy_summary:
        for item in group.get('items', []):
            code = item.get('code', '')
            raw_navs = item.get('_raw_navs', [])
            if code and raw_navs:
                # 按日期正序
                sorted_navs = sorted(raw_navs, key=lambda x: x[0])
                nav_history[code] = [[d, v] for d, v in sorted_navs]
    return nav_history


def build_rows(strategy_summary):
    """从 strategy_summary 扁平化生成 rows（核心资产表格用）"""
    rows = []
    for group in strategy_summary:
        for item in group.get('items', []):
            # 判断状态标签
            stat_end = item.get('stat_end_used_date') or item.get('stat_end_date') or item.get('latest_date', '')
            status_label = '正常'
            if item.get('data_source') == 'fallback':
                status_label = '缓存 / 滞后'
            elif stat_end:
                # 简单判断：如果数据日期比最新日期早2天以上，标为滞后
                pass  # 保持 API 返回的 status

            # 简化名称（去掉编号后缀）
            name = item.get('name', '')
            short_names = {
                '顽岩量化选股1号': '顽岩量化选股',
                '正仁股票择时一期': '正仁股票择时',
                '正仁双创择时一号': '正仁双创择时',
                '瀚鑫纸鸢量化优选': '瀚鑫纸鸢',
                '太衍光年中证2000指数增强2号': '太衍光年2000增强',
                '时间序列红利增强1号': '时间序列红利增强',
                '旌安思源1号B类': '旌安思源1号B',
                '创世纪顾锝灵活多策略1号': '创世纪顾锝',
                '立心-私募学院菁英353号': '立心菁英353号',
                '翔云50二号A类': '翔云50二号A',
                '特夫郁金香全量化': '特夫郁金香',
                '铭跃行远均衡一号': '铭跃行远',
                '格林基金鲲鹏6号': '格林鲲鹏6号',
                '波克宏观配置1号': '波克宏观配置',
                '正仁择时量选听涛二号': '正仁择时量选听涛二号',
                '国联证券陆联1号FOF': '国联证券陆联1号FOF',
                '大方向之中波思源365': '大方向之中波思源365',
            }
            display_name = short_names.get(name, name)

            rows.append({
                'name': display_name,
                'code': item.get('code', ''),
                'strategy': item.get('strategy', group.get('strategy', '')),
                'strategy_detail': item.get('strategy_detail', ''),
                'latest_date': item.get('latest_date', ''),
                'week_return': item.get('week_return'),
                'month_return': item.get('month_return'),
                'ytd_return': item.get('ytd_return'),
                'status_label': status_label if item.get('data_source') == 'fallback' else ('滞后' if item.get('status') == '滞后' else '正常'),
                'data_source': item.get('data_source', 'api'),
                'stat_end_used_date': stat_end,
            })
    return rows


def render():
    # 读模板
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()

    # 读数据
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    update_time = data.get('update_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    update_date = update_time[:10]
    strategy_summary = data.get('strategy_summary', [])
    market_data = data.get('market_data', {})

    # 市场基准：合并年度数据（v3 用的是 annual）
    # API 返回嵌套结构，v3 HTML 需要扁平结构
    market_annual_raw = market_data.get('annual', [])
    market_monthly_raw = market_data.get('monthly', [])
    market_quarterly_raw = market_data.get('quarterly', [])
    market_annual = flatten_market_data(market_annual_raw, market_monthly_raw, market_quarterly_raw)

    # Flatten monthly and quarterly for period switching
    market_monthly = flatten_market_data(market_monthly_raw)
    market_quarterly = flatten_market_data(market_quarterly_raw)

    # 生成 rows
    rows = build_rows(strategy_summary)

    # FOF 组合数据
    fof_combis = data.get('fof_combis', [])

    # JSON 序列化
    js_market = json.dumps(market_annual, ensure_ascii=False)
    js_market_monthly = json.dumps(market_monthly, ensure_ascii=False)
    js_market_quarterly = json.dumps(market_quarterly, ensure_ascii=False)
    js_rows = json.dumps(rows, ensure_ascii=False)
    js_strategy = json.dumps(strategy_summary, ensure_ascii=False)
    js_fof = json.dumps(fof_combis, ensure_ascii=False)

    # 注入数据
    html = template
    html = html.replace('/*__MARKET_DATA__*/[]', js_market)
    html = html.replace('/*__MARKET_MONTHLY__*/[]', js_market_monthly)
    html = html.replace('/*__MARKET_QUARTERLY__*/[]', js_market_quarterly)
    html = html.replace('/*__ROWS_DATA__*/[]', js_rows)
    html = html.replace('/*__STRATEGY_SUMMARY__*/[]', js_strategy)
    html = html.replace('/*__FOF_COMBIS__*/[]', js_fof)
    html = html.replace('/*__UPDATE_DATE__*/', update_date)

    # navHistory: 从 JSON 中读取
    nav_history = data.get('nav_history', {})
    html = html.replace('/*__NAV_HISTORY__*/{}', json.dumps(nav_history, ensure_ascii=False))

    # 基准指数净值 + 策略→基准映射
    benchmark_navs = data.get('benchmark_navs', {})
    strategy_benchmark = data.get('strategy_benchmark', {})
    html = html.replace('/*__BENCHMARK_NAVS__*/{}', json.dumps(benchmark_navs, ensure_ascii=False))
    html = html.replace('/*__STRATEGY_BENCHMARK__*/{}', json.dumps(strategy_benchmark, ensure_ascii=False))

    # 策略指数净值曲线（来自 size_spread/fund_nav/fund_nav.json）
    fund_nav_path = os.path.join(MODULE_DIR, '..', 'size_spread', 'fund_nav', 'fund_nav.json')
    strategy_charts = {}
    if os.path.exists(fund_nav_path):
        with open(fund_nav_path, 'r', encoding='utf-8') as f:
            fnav = json.load(f)
        for item in fnav.get('funds', []):
            tab = item.get('tab', '')
            strategy_charts[tab] = {
                'name': item.get('name', ''),
                'benchmark_name': item.get('benchmark_name', ''),
                'date_range': item.get('date_range', ''),
                'total_return': item.get('total_return'),
                'index_return': item.get('index_return'),
                'excess_return': item.get('excess_return'),
                'chart': item.get('chart', {}),
            }
    html = html.replace('/*__STRATEGY_CHARTS__*/{}', json.dumps(strategy_charts, ensure_ascii=False))

    # 策略分类月度累计收益曲线（自建）
    curves_path = os.path.join(MODULE_DIR, 'data', 'strategy_curves.json')
    strategy_curves = {}
    if os.path.exists(curves_path):
        with open(curves_path, 'r', encoding='utf-8') as f:
            sc = json.load(f)
        strategy_curves = sc.get('curves', {})
    html = html.replace('/*__STRATEGY_CURVES__*/{}', json.dumps(strategy_curves, ensure_ascii=False))

    # 日期注释 — 从 API 实际数据取截止日
    from dateutil.relativedelta import relativedelta

    # 市场策略基准的实际截止日
    annual_raw = market_data.get('annual', [])
    monthly_raw = market_data.get('monthly', [])
    quarterly_raw = market_data.get('quarterly', [])
    annual_end = annual_raw[0]['return']['trade_date'] if annual_raw else update_date
    monthly_end = monthly_raw[0]['return']['trade_date'] if monthly_raw else update_date
    quarterly_end = quarterly_raw[0]['return']['trade_date'] if quarterly_raw else update_date
    annual_cycle = annual_raw[0]['return'].get('cycle', '') if annual_raw else ''
    monthly_cycle = monthly_raw[0]['return'].get('cycle', '') if monthly_raw else ''
    quarterly_cycle = quarterly_raw[0]['return'].get('cycle', '') if quarterly_raw else ''

    # 核心资产/FOF 的日期区间用 update_date（产品净值是日频的）
    end_dt = datetime.strptime(update_date, '%Y-%m-%d')
    y1_start = (end_dt - relativedelta(years=1)).strftime('%Y-%m-%d')
    m1_start = (end_dt - relativedelta(months=1)).strftime('%Y-%m-%d')
    q1_start = (end_dt - relativedelta(months=3)).strftime('%Y-%m-%d')
    w1_start = (end_dt - timedelta(days=7)).strftime('%Y-%m-%d')

    # 市场策略基准的年度区间用实际截止日
    annual_end_dt = datetime.strptime(annual_end, '%Y-%m-%d')
    annual_start = (annual_end_dt - relativedelta(years=1)).strftime('%Y-%m-%d')

    html = html.replace('/*__ANNUAL_RANGE__*/',
        f'（年度滚动 {annual_start} ~ {annual_end}）')

    # Market meta for JS period switching
    market_meta = {
        'annual_range': f'（年度滚动 {annual_start} ~ {annual_end}）',
        'monthly_range': f'（月度 {monthly_end}，{monthly_cycle}）',
        'quarterly_range': f'（季度 {quarterly_end}，{quarterly_cycle}）',
    }
    html = html.replace('/*__MARKET_META__*/{}', json.dumps(market_meta, ensure_ascii=False))
    html = html.replace('/*__MARKET_SUBTITLE__*/',
        f'数据来源：火富牛策略观察 API<br/>年度指标截至 {annual_end}（{annual_cycle}） ｜ 月度收益截至 {monthly_end}（{monthly_cycle}） ｜ 季度收益截至 {quarterly_end}（{quarterly_cycle}）')
    html = html.replace('/*__MARKET_NOTE__*/',
        f'说明：年度指标统计截至 {annual_end}（{annual_cycle}），月度收益截至 {monthly_end}（{monthly_cycle}），季度收益截至 {quarterly_end}（{quarterly_cycle}）。<br/>分位数为各策略样本内的分布，10% 表示前10%分位（最优），90% 表示后10%分位（最差）。数据来源：火富牛策略观察 /market/category API。')
    html = html.replace('/*__CORE_SUBTITLE__*/',
        f'生成时间 {update_time} ｜ 各产品净值日期见表格"净值日期"列<br/>近一周/近一月/今年以来 均以各产品最新净值日为基准计算')
    html = html.replace('/*__CORE_NOTE__*/',
        f'各产品净值更新频率不同（日度/周度），具体见"净值日期"列')
    html = html.replace('/*__FOF_SUBTITLE__*/',
        f'生成时间 {update_time} ｜ 各组合净值日期见表格 ｜ 点击组合卡片查看详细分析报告')
    html = html.replace('/*__FOF_NOTE__*/',
        f'说明：数据来源火富牛模拟组合 /combi/price API。各组合净值更新日期见表格"净值日期"列。夏普无风险利率取2%，年化波动率=日波动率×√252。')

    # 写输出
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 生成: {OUTPUT_PATH}")
    print(f"   数据日期: {update_date}")
    print(f"   产品数: {len(rows)}")
    print(f"   策略组: {len(strategy_summary)}")
    print(f"   市场基准: {len(market_annual)}")
    print(f"   FOF组合: {len(fof_combis)}")
    print(f"   文件大小: {os.path.getsize(OUTPUT_PATH):,} bytes")


if __name__ == '__main__':
    render()
