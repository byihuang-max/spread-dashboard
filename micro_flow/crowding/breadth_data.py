#!/usr/bin/env python3
"""
行业市场宽度（breadth）+ 横截面占比历史 — 数据抓取层（增量）

新增三类数据，配合现有 crowding_data.py 的纵向量比一起用：

1. 个股日涨跌 → 按申万一级/二级聚合涨跌家数（breadth）
2. 涨跌停数量 → 按行业聚合（情绪温度）
3. 申万行业历史成交额 → 算横截面占比 + 占比历史分位（铺底 2 年）

增量逻辑与 crowding_data.py 一致：
- 明细表存全量，增量只补最近 LOOKBACK_DAYS 起的交易日
- merge_dedup 按主键去重，keep='last'
- 行业成份映射（individual→申万）变化极慢，单独缓存，过期才刷新
"""
import datetime as dt
import os
import time

import pandas as pd
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# breadth / 涨跌停从近一年起即可（不需要太长）
BREADTH_START = '20240101'
# 占比分位需要长历史铺底（拉到2021，和xls起始一致）
SHARE_HIST_START = '20210101'
END_DATE = dt.date.today().strftime('%Y%m%d')
LOOKBACK_DAYS = 10
# 行业成份映射缓存有效期（天），超过才重新逐行业拉
MEMBER_MAP_TTL_DAYS = 30

# ── 缓存文件 ──
MEMBER_MAP_CSV = os.path.join(CACHE_DIR, 'sw_member_map.csv')        # 个股→申万一二级 映射
BREADTH_L1_CSV = os.path.join(CACHE_DIR, 'breadth_l1.csv')          # 一级行业每日涨跌家数
BREADTH_L2_CSV = os.path.join(CACHE_DIR, 'breadth_l2.csv')          # 二级行业每日涨跌家数
SHARE_HIST_CSV = os.path.join(CACHE_DIR, 'sw_share_hist.csv')       # 一级行业每日成交额占比历史
LIMIT_DETAIL_CSV = os.path.join(CACHE_DIR, 'limit_detail.csv')      # 涨跌停个股明细（连板数+成交额，龙头案例用）


def ts_api(api_name, fields='', **kwargs):
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=60, proxies={'http': None, 'https': None})
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed for {api_name}: {e}")
            time.sleep(2)
    return pd.DataFrame()


def norm_date(s):
    return pd.to_datetime(str(s).strip()).strftime('%Y%m%d')


def read_csv(path, date_col='trade_date'):
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={'con_code': str, 'ts_code': str})
    if date_col in df.columns:
        df[date_col] = df[date_col].astype(str).str.strip().map(norm_date)
    return df


def incremental_start(df, col='trade_date', fallback=BREADTH_START, lookback_days=LOOKBACK_DAYS):
    if df.empty or col not in df.columns or df[col].dropna().empty:
        return fallback
    last = pd.to_datetime(df[col].astype(str).max()) - pd.Timedelta(days=lookback_days)
    return max(fallback, last.strftime('%Y%m%d'))


def merge_dedup(old, new, keys):
    if old.empty:
        return new.copy()
    if new.empty:
        return old.copy()
    return pd.concat([old, new], ignore_index=True).drop_duplicates(keys, keep='last')


def get_trade_dates(start, end):
    """交易日历，只返回开市日"""
    cal = ts_api('trade_cal', fields='cal_date,is_open', exchange='SSE', start_date=start, end_date=end)
    if cal.empty:
        return []
    cal = cal[cal['is_open'].astype(str) == '1']
    return sorted(cal['cal_date'].map(norm_date).tolist())


# ════════════════════════════════════════════════════════
#  1. 个股 → 申万一二级 行业映射（缓存，变化慢）
# ════════════════════════════════════════════════════════
def build_member_map(force=False):
    """
    逐申万一级行业拉成份（index_member），同时记录二级归属。
    映射变化极慢，缓存 MEMBER_MAP_TTL_DAYS 天，过期才重拉。
    输出列：ts_code, l1_code, l1_name, l2_code, l2_name
    """
    if not force and os.path.exists(MEMBER_MAP_CSV):
        age_days = (time.time() - os.path.getmtime(MEMBER_MAP_CSV)) / 86400
        if age_days < MEMBER_MAP_TTL_DAYS:
            df = read_csv(MEMBER_MAP_CSV)
            if not df.empty:
                print(f'  行业映射缓存有效（{age_days:.0f}天前），{len(df)}只个股')
                return df

    print('  重建个股→申万行业映射（逐行业拉成份）...')
    # 申万二级分类（带 parent 一级）
    # 关键：L2.parent_code 对应的是 L1.industry_code（如 110000），不是 L1.index_code（801010.SI）
    cls2 = ts_api('index_classify', fields='index_code,industry_name,parent_code', level='L2', src='SW2021')
    cls1 = ts_api('index_classify', fields='index_code,industry_name,industry_code', level='L1', src='SW2021')
    if cls2.empty or cls1.empty:
        print('  分类拉取失败，沿用旧缓存')
        return read_csv(MEMBER_MAP_CSV)
    l1_name_map = dict(zip(cls1['industry_code'].astype(str), cls1['industry_name']))

    rows = []
    for _, r in cls2.iterrows():
        l2_code, l2_name, l1_code = r['index_code'], r['industry_name'], str(r['parent_code'])
        l1_name = l1_name_map.get(l1_code, '')
        mem = ts_api('index_member', fields='con_code,is_new', index_code=l2_code)
        if mem.empty:
            time.sleep(0.15)
            continue
        mem = mem[mem['is_new'].astype(str) == 'Y']  # 仅当前有效成份
        for con in mem['con_code']:
            rows.append({
                'ts_code': con, 'l1_code': l1_code, 'l1_name': l1_name,
                'l2_code': l2_code, 'l2_name': l2_name,
            })
        time.sleep(0.15)

    df = pd.DataFrame(rows).drop_duplicates('ts_code', keep='last')
    if df.empty:
        print('  映射为空，沿用旧缓存')
        return read_csv(MEMBER_MAP_CSV)
    df.to_csv(MEMBER_MAP_CSV, index=False)
    print(f'  行业映射重建完成：{len(df)}只个股，一级{df.l1_name.nunique()}个 / 二级{df.l2_name.nunique()}个')
    return df


# ════════════════════════════════════════════════════════
#  2. 个股日涨跌 + 涨跌停 → 行业 breadth（增量，逐交易日）
# ════════════════════════════════════════════════════════
def fetch_breadth():
    print('增量拉取行业 breadth（涨跌家数 + 涨跌停）...')
    member = build_member_map()
    if member.empty:
        print('  无行业映射，跳过')
        return
    code2l2 = dict(zip(member['ts_code'], member['l2_name']))
    # 二级→一级 名称映射（一级 breadth 由二级聚合得到，保证口径一致）
    l2_to_l1 = dict(zip(member['l2_name'], member['l1_name']))

    old_l1 = read_csv(BREADTH_L1_CSV)
    old_l2 = read_csv(BREADTH_L2_CSV)
    old_detail = read_csv(LIMIT_DETAIL_CSV)
    # 增量基于二级（一级派生），二级 name 不会出现空值污染
    start = incremental_start(old_l2)
    trade_dates = get_trade_dates(start, END_DATE)
    if not trade_dates:
        print('  无交易日')
        return

    have = set(old_l2['trade_date'].unique()) if not old_l2.empty else set()
    todo = [d for d in trade_dates if d not in have or d >= incremental_start(old_l2, lookback_days=LOOKBACK_DAYS)]
    todo = sorted(set(todo))
    print(f'  待拉交易日 {len(todo)} 天（{todo[0] if todo else "-"} ~ {todo[-1] if todo else "-"}）')

    new_l2 = []
    new_detail = []
    for d in todo:
        daily = ts_api('daily', fields='ts_code,pct_chg', trade_date=d)
        # 涨跌停明细：多取 name/limit_times/amount，用于龙头案例（连板最高+成交额最大）
        limit = ts_api('limit_list_d', fields='ts_code,name,limit,limit_times,amount,pct_chg', trade_date=d)
        if daily.empty:
            continue
        daily['pct_chg'] = pd.to_numeric(daily['pct_chg'], errors='coerce')
        daily['l2'] = daily['ts_code'].map(code2l2)
        lim_map = dict(zip(limit['ts_code'], limit['limit'])) if not limit.empty else {}
        daily['lim'] = daily['ts_code'].map(lim_map)

        grp = daily.dropna(subset=['l2'])
        for name, g in grp.groupby('l2'):
            up = int((g['pct_chg'] > 0).sum())
            down = int((g['pct_chg'] < 0).sum())
            flat = int((g['pct_chg'] == 0).sum())
            new_l2.append({
                'trade_date': d, 'name': name, 'l1': l2_to_l1.get(name, ''),
                'up': up, 'down': down, 'flat': flat, 'total': up + down + flat,
                'limit_up': int((g['lim'] == 'U').sum()),
                'limit_down': int((g['lim'] == 'D').sum()),
            })

        # 涨跌停个股明细（关联到申万一级，供龙头案例用）
        if not limit.empty:
            lim = limit.copy()
            lim['l2'] = lim['ts_code'].map(code2l2)
            lim['l1'] = lim['l2'].map(l2_to_l1)
            lim['limit_times'] = pd.to_numeric(lim['limit_times'], errors='coerce').fillna(1)
            lim['amount'] = pd.to_numeric(lim['amount'], errors='coerce').fillna(0)
            lim['pct_chg'] = pd.to_numeric(lim['pct_chg'], errors='coerce').fillna(0)
            for _, r in lim.dropna(subset=['l1']).iterrows():
                new_detail.append({
                    'trade_date': d, 'ts_code': r['ts_code'], 'stock_name': r['name'],
                    'l1': r['l1'], 'l2': r['l2'], 'limit': r['limit'],
                    'limit_times': int(r['limit_times']), 'amount': float(r['amount']),
                    'pct_chg': float(r['pct_chg']),
                })
        time.sleep(0.3)

    # 写二级
    merged_l2 = merge_dedup(old_l2, pd.DataFrame(new_l2), ['trade_date', 'name']).sort_values(['trade_date', 'name'])
    if merged_l2.empty:
        print('  二级 breadth 为空')
        return
    merged_l2.to_csv(BREADTH_L2_CSV, index=False)
    print(f'  breadth 二级: {len(merged_l2)}行，最新 {merged_l2["trade_date"].max()}')

    # 写涨跌停明细（龙头案例用）
    merged_detail = merge_dedup(old_detail, pd.DataFrame(new_detail), ['trade_date', 'ts_code'])
    if not merged_detail.empty:
        merged_detail = merged_detail.sort_values(['trade_date', 'l1'])
        merged_detail.to_csv(LIMIT_DETAIL_CSV, index=False)
        print(f'  涨跌停明细: {len(merged_detail)}行，最新 {merged_detail["trade_date"].max()}')

    # 一级 = 二级按 l2_name→l1_name 聚合（涨跌家数可加，口径与二级一致）
    cnt_cols = ['up', 'down', 'flat', 'total', 'limit_up', 'limit_down']
    roll = merged_l2.copy()
    roll['l1'] = roll['name'].map(l2_to_l1)
    roll = roll.dropna(subset=['l1'])
    for c in cnt_cols:
        roll[c] = pd.to_numeric(roll[c], errors='coerce').fillna(0)
    merged_l1 = (roll.groupby(['trade_date', 'l1'])[cnt_cols].sum()
                 .reset_index().rename(columns={'l1': 'name'}).sort_values(['trade_date', 'name']))
    merged_l1.to_csv(BREADTH_L1_CSV, index=False)
    print(f'  breadth 一级(由二级聚合): {len(merged_l1)}行，{merged_l1["name"].nunique()}个行业，最新 {merged_l1["trade_date"].max()}')


# ════════════════════════════════════════════════════════
#  3. 申万一级历史成交额 → 占比 + 分位铺底（增量，分段）
# ════════════════════════════════════════════════════════
SW_L1_CODES = {
    '801010.SI': '农林牧渔', '801030.SI': '基础化工', '801040.SI': '钢铁',
    '801050.SI': '有色金属', '801080.SI': '电子', '801110.SI': '家用电器',
    '801120.SI': '食品饮料', '801130.SI': '纺织服饰', '801140.SI': '轻工制造',
    '801150.SI': '医药生物', '801160.SI': '公用事业', '801170.SI': '交通运输',
    '801180.SI': '房地产', '801200.SI': '商贸零售', '801210.SI': '社会服务',
    '801230.SI': '综合', '801710.SI': '建筑材料', '801720.SI': '建筑装饰',
    '801730.SI': '电力设备', '801740.SI': '国防军工', '801750.SI': '计算机',
    '801760.SI': '传媒', '801770.SI': '通信', '801780.SI': '银行',
    '801790.SI': '非银金融', '801880.SI': '汽车', '801890.SI': '机械设备',
    '801950.SI': '煤炭', '801960.SI': '石油石化', '801970.SI': '环保',
    '801980.SI': '美容护理',
}


def fetch_share_hist():
    """
    拉申万一级行业历史成交额，算横截面占比（每日 31 个行业占比合计=1）。
    逐行业拉取（每个一级指数单独调用，避免 sw_daily 4000行截断）。
    """
    print('增量拉取申万一级占比历史...')
    old = read_csv(SHARE_HIST_CSV)
    start = incremental_start(old, fallback=SHARE_HIST_START)

    parts = []
    for code, name in SW_L1_CODES.items():
        df = ts_api('sw_daily', fields='ts_code,trade_date,amount', ts_code=code, start_date=start, end_date=END_DATE)
        if not df.empty:
            parts.append(df)
        time.sleep(0.25)
    if not parts and old.empty:
        print('  无数据')
        return
    new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=['ts_code', 'trade_date', 'amount'])
    if not new.empty:
        new['trade_date'] = new['trade_date'].map(norm_date)
        new['amount'] = pd.to_numeric(new['amount'], errors='coerce')
        new['name'] = new['ts_code'].map(SW_L1_CODES)

    merged = merge_dedup(old, new, ['ts_code', 'trade_date']).sort_values(['trade_date', 'ts_code'])
    # 重算占比（横截面：每个交易日 31 行业 amount 归一）
    merged['amount'] = pd.to_numeric(merged['amount'], errors='coerce')
    merged['share'] = merged.groupby('trade_date')['amount'].transform(lambda x: x / x.sum())
    merged.to_csv(SHARE_HIST_CSV, index=False)
    dates_n = merged['trade_date'].nunique()
    print(f'  占比历史: {len(merged)}行 / {dates_n}天，{merged["trade_date"].min()} ~ {merged["trade_date"].max()}')


def main():
    print('=' * 50)
    print('行业 breadth + 占比 - 增量更新')
    print('=' * 50)
    fetch_share_hist()
    fetch_breadth()
    print('\n breadth/占比 数据更新完成')


if __name__ == '__main__':
    main()
