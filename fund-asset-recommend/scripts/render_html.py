#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - HTML 渲染（v3 模板注入版）
读取 fund_asset_latest.json，注入到 v3 模板生成 fund_asset.html
"""

import json, os, re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(SCRIPT_DIR)
TEMPLATE_PATH = os.path.join(MODULE_DIR, 'fund_asset_template.html')
DATA_PATH = os.path.join(MODULE_DIR, 'data', 'fund_asset_latest.json')
OUTPUT_PATH = os.path.join(MODULE_DIR, 'fund_asset.html')


GROUP_MAP = {5: '股票策略', 10: '股票策略', 9: '股票策略', 8: '股票策略', 7: '股票策略',
             4: '股票策略', 6: '股票策略', 2: '期货策略', 3: '期货策略', 1: '期货策略',
             11: '其他策略', 12: '其他策略', 13: '其他策略', 15: '其他策略', 14: '其他策略', 16: '其他策略'}


def flatten_market_data(raw_list, monthly_list=None, quarterly_list=None):
    """把 API 嵌套结构转成 v3 HTML 需要的扁平结构"""
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
                'strategy': item.get('strategy', group.get('strategy', '')),
                'strategy_detail': item.get('strategy_detail', ''),
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

    # 生成 rows
    rows = build_rows(strategy_summary)

    # FOF 组合数据
    fof_combis = data.get('fof_combis', [])

    # JSON 序列化
    js_market = json.dumps(market_annual, ensure_ascii=False)
    js_rows = json.dumps(rows, ensure_ascii=False)
    js_strategy = json.dumps(strategy_summary, ensure_ascii=False)
    js_fof = json.dumps(fof_combis, ensure_ascii=False)

    # 注入数据
    html = template
    html = html.replace('/*__MARKET_DATA__*/[]', js_market)
    html = html.replace('/*__ROWS_DATA__*/[]', js_rows)
    html = html.replace('/*__STRATEGY_SUMMARY__*/[]', js_strategy)
    html = html.replace('/*__FOF_COMBIS__*/[]', js_fof)
    html = html.replace('/*__UPDATE_DATE__*/', update_date)

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
