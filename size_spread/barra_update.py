#!/usr/bin/env python3
"""
Barra CNE6 风格因子日更脚本
- 从 DataYes API 拉增量因子收益率
- 追加到本地 pkl
- 输出前端 JSON（20个因子净值序列）

数据源: DataYes Barra CNE6 SW21
更新频率: 每日盘后（18:00 late-only 批次）
"""

import os
import sys
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

# === 配置 ===
DATAYES_TOKEN = '6b1c26f10036171bf12fa225d2bb98046db6a88b5999b0110c7fcfe574e810ce'
API_URL = 'https://api.datayes.com/data/v1/api/equity/getDy1dFactorRetCNE6SW21.json'

# 路径自适应（Mac / 腾讯云）
def _first_existing(*paths):
    for p in paths:
        expanded = os.path.expanduser(p)
        if os.path.exists(os.path.dirname(expanded)):
            return expanded
    return os.path.expanduser(paths[-1])

PKL_PATH = _first_existing(
    '/Users/apple/Desktop/quant-backtest/timing_model/data/barra_datayes/factor_return/factor_return.pkl',
    '/home/ubuntu/quant-backtest/timing_model/data/barra_datayes/factor_return/factor_return.pkl',
)

# 输出 JSON 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'data', 'barra_style_nav.json')

# 20 个风格因子
ALL_FACTORS = [
    'DIVYILD', 'RESVOL', 'MOMENTUM', 'BTOP', 'PROFIT', 'LTREVRSL',
    'STREVRSL', 'EARNYILD', 'EARNQLTY', 'INVSQLTY', 'SIZE', 'GROWTH',
    'BETA', 'LIQUIDTY', 'MIDCAP', 'LEVERAGE', 'EARNVAR',
    'ANALSENTI', 'INDMOM', 'SEASON'
]

FACTOR_NAMES = {
    'DIVYILD': '红利', 'RESVOL': '低波动', 'MOMENTUM': '动量',
    'BTOP': '价值(BP)', 'PROFIT': '质量(盈利)', 'LTREVRSL': '长期反转',
    'STREVRSL': '短期反转', 'EARNYILD': '盈利收益率', 'EARNQLTY': '盈利质量',
    'INVSQLTY': '投资质量', 'SIZE': '规模(小盘)', 'GROWTH': '成长',
    'BETA': '贝塔', 'LIQUIDTY': '流动性', 'MIDCAP': '中盘',
    'LEVERAGE': '杠杆', 'EARNVAR': '盈余稳定',
    'ANALSENTI': '分析师情绪', 'INDMOM': '行业动量', 'SEASON': '季节性'
}

FACTOR_GROUPS = {
    '核心六因子': ['DIVYILD', 'RESVOL', 'MOMENTUM', 'BTOP', 'PROFIT', 'LTREVRSL'],
    '估值与成长': ['EARNYILD', 'GROWTH'],
    '质量补充': ['EARNQLTY', 'INVSQLTY', 'EARNVAR'],
    '动量与反转': ['STREVRSL', 'INDMOM'],
    '风险与流动性': ['BETA', 'LIQUIDTY', 'SIZE', 'MIDCAP'],
    '其他': ['LEVERAGE', 'ANALSENTI', 'SEASON'],
}

# 因子状态含义（正收益时的解读）
FACTOR_MEANING = {
    'DIVYILD': '高股息跑赢，市场偏好确定性现金流',
    'RESVOL': '低波动跑赢，防御风格占优',
    'MOMENTUM': '中期动量有效，趋势延续',
    'BTOP': '低估值跑赢高估值，价值回归',
    'PROFIT': '高盈利质量跑赢，基本面定价有效',
    'LTREVRSL': '长期反转有效，过去3-4年输家反弹',
    'STREVRSL': '短期反转有效，近期超跌反弹',
    'EARNYILD': '高EP跑赢低EP，盈利收益率定价',
    'EARNQLTY': '高利润含金量跑赢，现金流质量受追捧',
    'INVSQLTY': '低资本开支跑赢，轻资产模式占优',
    'EARNVAR': '盈余稳定跑赢，市场厌恶不确定性',
    'SIZE': '大盘跑赢小盘',
    'GROWTH': '高成长跑赢低成长，成长风格占优',
    'BETA': '高贝塔跑赢低贝塔，风险偏好上升',
    'LIQUIDTY': '高换手跑赢低换手，交易活跃度溢价',
    'MIDCAP': '中盘跑赢大小盘两端',
    'LEVERAGE': '高杠杆跑赢低杠杆，加杠杆环境',
    'ANALSENTI': '被上调个股跑赢被下调，分析师情绪有效',
    'INDMOM': '热门行业继续跑赢，行业动量延续',
    'SEASON': '历史同期强势股跑赢，季节性规律有效',
}

# 多时间窗口定义
RETURN_WINDOWS = {
    'recent_5': 5,
    'recent_20': 20,
    'recent_60': 60,
    'recent_120': 120,
    'recent_250': 250,
}


def fetch_incremental(last_date_str, end_date_str):
    """从 DataYes 拉增量数据"""
    headers = {
        'Authorization': f'Bearer {DATAYES_TOKEN}',
        'Accept-Encoding': 'gzip, deflate'
    }
    # 从 last_date 的下一天开始
    begin = (datetime.strptime(last_date_str, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')
    
    if begin > end_date_str:
        print(f'[barra_update] 已是最新，无需更新 (last={last_date_str}, end={end_date_str})')
        return None
    
    resp = requests.get(API_URL, params={
        'field': '',
        'tradeDate': '',
        'beginDate': begin,
        'endDate': end_date_str,
    }, headers=headers, timeout=30)
    
    data = resp.json()
    if data.get('retCode') != 1:
        print(f'[barra_update] API 错误: {data.get("retMsg")}')
        return None
    
    rows = data.get('data', [])
    if not rows:
        print(f'[barra_update] 无新数据 ({begin} ~ {end_date_str})')
        return None
    
    df_new = pd.DataFrame(rows)
    # 转换数值列
    for col in df_new.columns:
        if col != 'tradeDate':
            df_new[col] = pd.to_numeric(df_new[col], errors='coerce')
    
    print(f'[barra_update] 拉取 {len(df_new)} 天增量 ({begin} ~ {end_date_str})')
    return df_new


def update_pkl(df_new):
    """追加到本地 pkl"""
    if not os.path.exists(PKL_PATH):
        print(f'[barra_update] pkl 不存在: {PKL_PATH}')
        return None
    
    df = pd.read_pickle(PKL_PATH)
    df['tradeDate'] = df['tradeDate'].astype(str).str.replace('-', '')
    
    # 去重追加
    existing_dates = set(df['tradeDate'].tolist())
    df_new_filtered = df_new[~df_new['tradeDate'].isin(existing_dates)]
    
    if len(df_new_filtered) == 0:
        print('[barra_update] 无新增数据（全部已存在）')
        return df
    
    df = pd.concat([df, df_new_filtered], ignore_index=True)
    df = df.sort_values('tradeDate').reset_index(drop=True)
    df.to_pickle(PKL_PATH)
    print(f'[barra_update] pkl 更新完成，共 {len(df)} 天')
    return df


def generate_json(df):
    """生成前端 JSON"""
    df = df.copy()
    df['tradeDate'] = df['tradeDate'].astype(str)
    df = df.sort_values('tradeDate').reset_index(drop=True)
    
    n = len(df)
    # 降采样：每5个点取1个 + 最近60天全量
    keep_recent = min(60, n)
    indices = list(range(0, n - keep_recent, 5)) + list(range(n - keep_recent, n))
    indices = sorted(set(indices))
    
    dates_sampled = [df['tradeDate'].iloc[i][:4] + '/' + df['tradeDate'].iloc[i][4:6] + '/' + df['tradeDate'].iloc[i][6:8] for i in indices]
    
    navs_sampled = {}
    total_return = {}
    window_returns = {wname: {} for wname in RETURN_WINDOWS}
    
    # 全量日期（用于前端时间筛选）
    all_dates = [df['tradeDate'].iloc[i][:4] + '/' + df['tradeDate'].iloc[i][4:6] + '/' + df['tradeDate'].iloc[i][6:8] for i in range(n)]
    all_navs = {}
    
    for code in ALL_FACTORS:
        if code not in df.columns:
            continue
        returns = df[code].fillna(0).tolist()
        nav = 1.0
        nav_list = []
        for r in returns:
            nav *= (1 + r)
            nav_list.append(nav)
        
        navs_sampled[code] = [round(nav_list[i], 6) for i in indices]
        all_navs[code] = [round(v, 6) for v in nav_list]
        total_return[code] = round((nav_list[-1] - 1) * 100, 2)
        
        # 多时间窗口收益
        for wname, wdays in RETURN_WINDOWS.items():
            window = returns[-wdays:] if len(returns) >= wdays else returns
            cum = 1.0
            for r in window:
                cum *= (1 + r)
            window_returns[wname][code] = round((cum - 1) * 100, 2)
    
    last_date = df['tradeDate'].iloc[-1]
    update_date = f'{last_date[:4]}-{last_date[4:6]}-{last_date[6:8]}'
    
    output = {
        'dates': dates_sampled,
        'all_dates': all_dates,
        'navs': navs_sampled,
        'all_navs': all_navs,
        'names': FACTOR_NAMES,
        'groups': FACTOR_GROUPS,
        'meanings': FACTOR_MEANING,
        'recent_5': window_returns['recent_5'],
        'recent_20': window_returns['recent_20'],
        'recent_60': window_returns['recent_60'],
        'recent_120': window_returns['recent_120'],
        'recent_250': window_returns['recent_250'],
        'total_return': total_return,
        'update_date': update_date,
        'total_days': n,
    }
    
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)
    
    print(f'[barra_update] JSON 输出: {OUTPUT_JSON} ({os.path.getsize(OUTPUT_JSON)/1024:.1f} KB)')
    return output


def main():
    print(f'[barra_update] 开始更新 Barra CNE6 风格因子...')
    
    # 读取现有数据
    if not os.path.exists(PKL_PATH):
        print(f'[barra_update] 错误: pkl 文件不存在 {PKL_PATH}')
        sys.exit(1)
    
    df = pd.read_pickle(PKL_PATH)
    df['tradeDate'] = df['tradeDate'].astype(str).str.replace('-', '')
    last_date = df['tradeDate'].max()
    
    # 拉增量
    today = datetime.now().strftime('%Y%m%d')
    df_new = fetch_incremental(last_date, today)
    
    if df_new is not None:
        df = update_pkl(df_new)
    
    if df is None:
        df = pd.read_pickle(PKL_PATH)
        df['tradeDate'] = df['tradeDate'].astype(str).str.replace('-', '')
    
    # 生成前端 JSON
    generate_json(df)
    print('[barra_update] 完成')


if __name__ == '__main__':
    main()
