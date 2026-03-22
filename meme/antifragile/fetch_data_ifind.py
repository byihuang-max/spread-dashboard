#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - iFind 数据源（替代 yfinance）
适合腾讯云大陆服务器直连，不需要翻墙

API: iFind quant API v1
端点: date_sequence（历史日线）+ real_time_quotation（实时）
"""

import requests
import json
import os
from datetime import datetime, timedelta

# ═══ iFind 配置 ═══
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
# refresh_token 从 chain_data.py 统一管理
_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(os.path.dirname(_DIR))

def _load_refresh_token():
    """从 chain_data.py 读取 refresh_token（单一来源）"""
    import re
    chain_data = os.path.join(_PROJECT, 'meso/chain_prosperity/chain_data.py')
    with open(chain_data, 'r', encoding='utf-8') as f:
        m = re.search(r"IFIND_REFRESH = '([^']+)'", f.read())
    return m.group(1) if m else None


def get_token():
    """获取 access_token"""
    refresh = _load_refresh_token()
    if not refresh:
        print("❌ 未找到 iFind refresh_token")
        return None
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': refresh}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
        print(f"❌ iFind token 错误: {d.get('errmsg', '未知')}")
    except Exception as e:
        print(f"❌ iFind token 连接失败: {e}")
    return None


# ═══ iFind 品种映射 ═══
# iFind code → (显示名, 是否有成交量)
# 经云端验证 2026-03-11
IFIND_ASSETS = {
    # 海外指数 / 代理ETF
    'NDX.GI':       ('纳斯达克100', False),      # ✅ 纳斯达克100指数
    '513500.SH':    ('标普500', True),           # ✅ 标普500ETF，作为标普500代理
    'N225.GI':      ('日经225', False),           # ✅ 日经225
    'KS11.GI':      ('韩国KOSPI', False),         # ✅ 韩国KOSPI

    # 港股 ETF
    '03033.HK':     ('恒生科技ETF', True),        # ✅ 南方恒生科技ETF

    # A 股 ETF
    '588000.SH':    ('科创50ETF', True),          # ✅ 科创50ETF

    # 商品（用A股ETF替代，iFind期货代码不可用）
    '518880.SH':    ('COMEX黄金', True),          # ✅ 黄金ETF（替代 COMEX 黄金期货）
    '159985.SZ':    ('WTI原油', True),            # ✅ 原油基金LOF（替代 WTI 原油期货）

    # BTC（用 iShares Bitcoin ETF 替代）
    'IBIT.O':       ('BTC', True),                # ✅ iShares Bitcoin ETF

    # 汇率
    'USDJPY.FX':    ('美元兑日元', False),         # ✅ USD/JPY
}

# 纳斯达克ETF QQQ 作为纳指成交量代理
QQQ_CODE = 'QQQ.O'  # QQQ纳斯达克100ETF（美股）

# 计算 Meme 信号需要成交量的资产
VOL_WEIGHTS = {
    'BTC':              0.35,
    '纳斯达克ETF(QQQ)': 0.25,
    '恒生科技ETF':       0.20,
    '科创50ETF':        0.20,
}


def ifind_history(access_token, codes, indicators, start_date, end_date):
    """
    iFind 历史日线数据（cmd_history_quotation 端点）
    codes: 品种代码
    indicators: 逗号分隔的指标（如 close,volume）
    start_date / end_date: YYYY-MM-DD 格式
    """
    try:
        r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
            json={
                'codes': codes,
                'indicators': indicators,
                'startdate': start_date,
                'enddate': end_date,
            },
            headers={'Content-Type': 'application/json', 'access_token': access_token},
            timeout=30)
        d = r.json()
        if d.get('errorcode') == 0:
            return d.get('tables', [])
        else:
            print(f"  ⚠️ {codes}: {d.get('errmsg', '未知错误')}")
    except Exception as e:
        print(f"  ❌ {codes} 失败: {e}")
    return []


def ifind_realtime(access_token, codes, indicators='latest'):
    """iFind 实时行情"""
    try:
        r = requests.post(f'{IFIND_BASE}/real_time_quotation',
            json={'codes': codes, 'indicators': indicators},
            headers={'Content-Type': 'application/json', 'access_token': access_token},
            timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d.get('tables', [])
    except Exception as e:
        print(f"  ❌ realtime {codes} 失败: {e}")
    return []


def load_existing_data():
    """加载现有数据"""
    nav_path = os.path.join(_DIR, 'antifragile_nav.json')
    if os.path.exists(nav_path):
        with open(nav_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('nav_data', {}), data.get('vol_data', {})
    return {}, {}


def parse_date_sequence(tables, name, has_volume=False):
    """
    解析 date_sequence 返回的 tables
    返回: (close_dict, vol_dict)  {date_str: value}
    """
    close_dict = {}
    vol_dict = {}
    if not tables:
        return close_dict, vol_dict

    for tbl in tables:
        time_list = tbl.get('time', [])
        table_data = tbl.get('table', {})

        close_values = table_data.get('close', [])
        vol_values = table_data.get('volume', [])

        for i, t in enumerate(time_list):
            # 日期格式化为 YYYY-MM-DD
            if len(t) == 8:  # 20260311
                date_str = f"{t[:4]}-{t[4:6]}-{t[6:]}"
            elif 'T' in t:
                date_str = t.split('T')[0]
            else:
                date_str = t[:10]

            if i < len(close_values) and close_values[i] is not None:
                close_dict[date_str] = float(close_values[i])

            if has_volume and i < len(vol_values) and vol_values[i] is not None:
                v = float(vol_values[i])
                if v > 0:
                    vol_dict[date_str] = v

    return close_dict, vol_dict


def _fallback_yfinance():
    """iFind 不可用时 fallback 到 yfinance"""
    import subprocess, sys
    script = os.path.join(_DIR, 'fetch_data.py')
    if os.path.exists(script):
        print("  → 运行 fetch_data.py (yfinance)...")
        subprocess.run([sys.executable, script], cwd=_DIR)
    else:
        print("  ❌ fetch_data.py 不存在，无法 fallback")


def main():
    at = get_token()
    if not at:
        print("⚠️ iFind token 获取失败，fallback 到 yfinance...")
        _fallback_yfinance()
        return

    existing_nav, existing_vol = load_existing_data()
    merged_nav = {k: dict(v) for k, v in existing_nav.items()}
    merged_vol = {k: dict(v) for k, v in existing_vol.items()}

    end_date = datetime.now().strftime('%Y-%m-%d')

    # 确定起始日期（增量拉取）
    if existing_nav:
        # 找最新日期，往前回退3天（覆盖可能的修正）
        all_dates = []
        for asset_data in existing_nav.values():
            all_dates.extend(asset_data.keys())
        if all_dates:
            latest = max(all_dates)
            start_date = (datetime.strptime(latest, '%Y-%m-%d') - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    else:
        start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')

    print(f"📅 iFind 增量拉取: {start_date} → {end_date}")
    print(f"   品种数: {len(IFIND_ASSETS) + 1} (含QQQ)")

    # ── 逐个资产拉取历史日线 ──
    for code, (name, has_vol) in IFIND_ASSETS.items():
        indicators = 'close,volume' if has_vol else 'close'
        asset_start_date = start_date
        existing_asset = merged_nav.get(name, {})
        if not existing_asset or len(existing_asset) < 60:
            asset_start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
        print(f"  {name} ({code}): ", end='', flush=True)

        tables = ifind_history(at, code, indicators, asset_start_date, end_date)
        close_dict, vol_dict = parse_date_sequence(tables, name, has_vol)

        if close_dict:
            if name not in merged_nav:
                merged_nav[name] = {}
            merged_nav[name].update(close_dict)
            print(f"+{len(close_dict)} 条价格（共 {len(merged_nav[name])} 天）", end='')
        else:
            print("无新数据", end='')

        if vol_dict:
            if name not in merged_vol:
                merged_vol[name] = {}
            merged_vol[name].update(vol_dict)
            print(f", +{len(vol_dict)} 条成交量", end='')

        print()

    # ── QQQ（纳指成交量代理）──
    print(f"  纳斯达克ETF(QQQ) ({QQQ_CODE}): ", end='', flush=True)
    tables = ifind_history(at, QQQ_CODE, 'close,volume', start_date, end_date)
    close_dict, vol_dict = parse_date_sequence(tables, '纳斯达克ETF(QQQ)', True)
    if close_dict:
        merged_nav['纳斯达克ETF(QQQ)'] = merged_nav.get('纳斯达克ETF(QQQ)', {})
        merged_nav['纳斯达克ETF(QQQ)'].update(close_dict)
        print(f"+{len(close_dict)} 条价格", end='')
    if vol_dict:
        merged_vol['纳斯达克ETF(QQQ)'] = merged_vol.get('纳斯达克ETF(QQQ)', {})
        merged_vol['纳斯达克ETF(QQQ)'].update(vol_dict)
        print(f", +{len(vol_dict)} 条成交量", end='')
    print()

    # ── 保存 ──
    from datetime import datetime as _dt
    output = {
        'update_time': _dt.now().strftime('%Y-%m-%d %H:%M:%S'),
        'nav_data': merged_nav,
        'vol_data': merged_vol,
    }
    out_path = os.path.join(_DIR, 'antifragile_nav.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)

    print(f"\n✅ 保存完成")
    print(f"   价格数据：{len(merged_nav)} 个资产")
    print(f"   成交量数据：{len(merged_vol)} 个资产 → {list(merged_vol.keys())}")


if __name__ == '__main__':
    main()
