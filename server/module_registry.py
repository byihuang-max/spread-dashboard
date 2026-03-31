#!/usr/bin/env python3
"""
GAMT 模块注册表

单一事实来源（single source of truth）：
- update_all.py 用它生成 data_scripts / inject_script / post_inject
- refresh_server.py 用它生成 scripts 和 TAB 映射

约定：
- scripts: 按执行顺序列出所有脚本（含注入脚本）
- inject_script: scripts 中最后一个注入脚本（可选）
- post_inject: update_all.py 专用的后置注入（可选）
- aliases: refresh_server.py 的 tab/url 别名（可选）
- include_in_update_all / include_in_refresh_server: 控制是否出现在对应入口
"""

from __future__ import annotations

import os
from copy import deepcopy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODULE_REGISTRY = {
    'fund_nav': {
        'name': '产品净值',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
        ],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'style_spread': {
        'name': '风格轧差',
        'scripts': [
            ('size_spread', 'fetch_incremental.py'),
            ('size_spread', 'compute_spreads.py'),
            ('size_spread', 'render_html.py'),
        ],
        'aliases': ['style-spread'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'quant_stock': {
        'name': '宽基量化股票',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
            ('env_fit/quant_stock', 'quant_stock_data.py'),
            ('env_fit/quant_stock', 'excess_attribution.py'),
            ('env_fit/quant_stock', 'inject_quant_stock.py'),
        ],
        'inject_script': ('env_fit/quant_stock', 'inject_quant_stock.py'),
        'aliases': ['quant-stock'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'momentum_stock': {
        'name': '强势股情绪',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
            ('env_fit/momentum_stock', 'momentum_data.py'),
            ('env_fit/momentum_stock/limit_index', 'limit_index_data.py'),
            ('env_fit/momentum_stock/limit_index/seal_spread', 'seal_spread_data.py'),
            ('env_fit/momentum_stock', 'momentum_sector.py'),
            ('env_fit/momentum_stock', 'momentum_warning.py'),
            ('env_fit/momentum_stock', 'momentum_return_decomp.py'),
            ('env_fit/momentum_stock', 'inject_momentum.py'),
        ],
        'inject_script': ('env_fit/momentum_stock', 'inject_momentum.py'),
        'post_inject': [
            ('timing-research', 'generate_leader_pool.py'),
            ('timing-research', 'export_leader_pool_history.py'),
            ('timing-research', 'generate_replay_page.py'),
            ('timing-research', 'push_limit_replay_feishu.py'),
        ],
        'aliases': ['momentum-stock'],
        'late_data': True,  # 涨跌停数据约17:30-18:00才出全
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'commodity_cta': {
        'name': '商品CTA',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
            ('env_fit/commodity_cta', 'commodity_data.py'),
            ('env_fit/commodity_cta', 'mod1_cta_env.py'),
            ('env_fit/commodity_cta', 'mod1b_pca_engine.py'),
            ('env_fit/commodity_cta', 'mod1c_market_vol.py'),
            ('env_fit/commodity_cta', 'mod2_trend_scan.py'),
            ('env_fit/commodity_cta', 'mod3_macro_ratio.py'),
            ('env_fit/commodity_cta', 'commodity_cta_main.py'),
            ('env_fit/commodity_cta', 'inject_commodity_cta.py'),
        ],
        'inject_script': ('env_fit/commodity_cta', 'inject_commodity_cta.py'),
        'aliases': ['cta'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'cb_env': {
        'name': '转债指增',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
            ('env_fit/cb_env', 'cb_data.py'),
            ('env_fit/cb_env', 'cb_calc.py'),
            ('env_fit/cb_env', 'inject_cb_env.py'),
            ('env_fit/cb_env', 'inject_cb_nav.py'),
        ],
        'inject_script': ('env_fit/cb_env', 'inject_cb_env.py'),
        'post_inject': [('env_fit/cb_env', 'inject_cb_nav.py')],
        'aliases': ['convertible'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'alerts': {
        'name': '红灯预警（A股）',
        'scripts': [
            ('alerts', 'alerts_data.py'),
            ('alerts', 'alerts_calc.py'),
        ],
        'aliases': ['alerts'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'us_alerts': {
        'name': '美股风险监控',
        'scripts': [
            ('alerts', 'us_alerts_data.py'),
            ('alerts', 'us_alerts_calc.py'),
        ],
        'aliases': ['us-alerts'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'crowding': {
        'name': '资金流拥挤度',
        'scripts': [
            ('micro_flow/crowding', 'crowding_data.py'),
            ('micro_flow/crowding', 'crowding_calc.py'),
        ],
        'aliases': ['crowding'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'option_sentiment': {
        'name': '期权情绪',
        'scripts': [
            ('micro_flow/option_sentiment', 'option_data.py'),
            ('micro_flow/option_sentiment', 'option_calc.py'),
        ],
        'aliases': ['option-sentiment'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'patient_capital': {
        'name': '耐心资本',
        'scripts': [
            ('micro_flow/patient_capital', 'patient_data.py'),
            ('micro_flow/patient_capital', 'patient_calc.py'),
        ],
        'aliases': ['patient-capital'],
        'late_data': True,  # 15min成交明细晚到，T+1才出全
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'macro_liquidity': {
        'name': '宏观流动性',
        'scripts': [
            ('macro/liquidity', 'liquidity_data.py'),
            ('macro/liquidity', 'liquidity_calc.py'),
        ],
        'aliases': ['liquidity'],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'macro_rates': {
        'name': '利率数据',
        'scripts': [
            ('macro/rates', 'rates_data.py'),
            ('macro/rates', 'rates_calc.py'),
        ],
        'aliases': ['rates'],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'macro_fundamentals': {
        'name': '基本面数据',
        'scripts': [
            ('macro/fundamentals', 'fundamentals_data.py'),
            ('macro/fundamentals', 'fundamentals_calc.py'),
        ],
        'aliases': ['fundamentals'],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'antifragile': {
        'name': '反脆弱看板',
        'scripts': [
            ('meme/antifragile', 'fetch_data_ifind.py'),
            ('meme/antifragile', 'calc_corr.py'),
            ('meme/antifragile', 'calc_meme.py'),
            ('meme/antifragile', 'render_html.py'),
        ],
        'aliases': ['antifragile'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'narrative_monitor': {
        'name': '叙事监控',
        'scripts': [
            ('daily_report/meme交易', 'narrative_monitor.py'),
        ],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'narrative_lifecycle': {
        'name': '叙事生命周期',
        'scripts': [
            ('meme', 'macro_lifecycle.py'),
        ],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'chain_prosperity': {
        'name': '中观景气度',
        'scripts': [
            ('meso/chain_prosperity', 'chain_data.py'),
            ('meso/chain_prosperity', 'chain_calc.py'),
        ],
        'aliases': ['chain-prosperity'],
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'macro_score': {
        'name': '宏观打分+策略适配',
        'scripts': [
            ('macro/score', 'macro_score.py'),
        ],
        'aliases': ['macro-score'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'timing_factors': {
        'name': '择时因子系统',
        'scripts': [],
        'external_script': os.path.expanduser('~/Desktop/quant-backtest/timing_model/factor_system/daily_update.py'),
        'include_in_update_all': True,
        'include_in_refresh_server': False,
    },
    'arbitrage': {
        'name': '套利',
        'scripts': [
            ('size_spread/fund_nav', 'fund_nav_data.py'),
            ('env_fit/arbitrage', 'fetch_incremental.py'),
            ('env_fit/arbitrage', 'mod1_index_arb.py'),
            ('env_fit/arbitrage', 'mod2_commodity_arb.py'),
            ('env_fit/arbitrage', 'mod3_option_arb.py'),
        ],
        'aliases': ['arbitrage'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'halo_trade': {
        'name': 'HALO交易',
        'scripts': [
            ('halo_trade', 'halo_data_ifind_full.py'),
            ('halo_trade', 'halo_financials_tushare.py'),
            ('halo_trade', 'halo_pe_scissors_tushare.py'),
            ('halo_trade', 'halo_calc.py'),
            ('halo_trade', 'china_halo.py'),
        ],
        'aliases': ['halo'],
        'include_in_update_all': True,
        'include_in_refresh_server': True,
    },
    'rates': {
        'name': '全球利率与汇率',
        'scripts': [
            ('macro/rates', 'rates_data.py'),
            ('macro/rates', 'rates_calc.py'),
        ],
        'aliases': ['rates'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
    'fundamentals': {
        'name': '经济基本面',
        'scripts': [
            ('macro/fundamentals', 'fundamentals_data.py'),
            ('macro/fundamentals', 'fundamentals_calc.py'),
            ('macro/fundamentals/profit_cycle', 'profit_cycle_data.py'),
        ],
        'aliases': ['fundamentals'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
    'liquidity': {
        'name': '境内流动性',
        'scripts': [
            ('macro/liquidity', 'liquidity_data.py'),
            ('macro/liquidity', 'liquidity_calc.py'),
        ],
        'aliases': ['liquidity'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
    'chain-prosperity': {
        'name': '产业链景气',
        'scripts': [
            ('meso/chain_prosperity', 'chain_data.py'),
            ('meso/chain_prosperity', 'chain_calc.py'),
        ],
        'aliases': ['chain-prosperity'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
    'macro_meme': {
        'name': '宏观Meme叙事',
        'scripts': [
            ('daily_report/meme交易', 'narrative_monitor.py'),
            ('meme', 'macro_lifecycle.py'),
        ],
        'aliases': ['macro-meme'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
    'overview': {
        'name': '仪表盘汇总',
        'scripts': [
            ('server', 'overview_calc.py'),
        ],
        'aliases': ['overview'],
        'include_in_update_all': False,
        'include_in_refresh_server': True,
    },
}


def build_update_all_modules():
    modules = {}
    for key, conf in MODULE_REGISTRY.items():
        if not conf.get('include_in_update_all'):
            continue
        item = {
            'name': conf['name'],
            'data_scripts': deepcopy(conf.get('scripts', [])),
            'inject_script': conf.get('inject_script'),
        }
        if item['inject_script'] and item['inject_script'] in item['data_scripts']:
            item['data_scripts'].remove(item['inject_script'])
        if conf.get('post_inject'):
            item['post_inject'] = deepcopy(conf['post_inject'])
            for post in conf['post_inject']:
                if post in item['data_scripts']:
                    item['data_scripts'].remove(post)
        if conf.get('external_script'):
            item['external_script'] = conf['external_script']
        modules[key] = item
    return modules


def build_refresh_modules():
    modules = {}
    for key, conf in MODULE_REGISTRY.items():
        if not conf.get('include_in_refresh_server'):
            continue
        modules[key] = {
            'name': conf['name'],
            'scripts': deepcopy(conf.get('scripts', [])),
        }
    return modules


def build_tab_map():
    tab_map = {}
    for key, conf in MODULE_REGISTRY.items():
        if not conf.get('include_in_refresh_server'):
            continue
        for alias in conf.get('aliases', []):
            tab_map[alias] = key
    return tab_map
