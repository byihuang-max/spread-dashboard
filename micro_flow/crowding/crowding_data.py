#!/usr/bin/env python3
"""
拥挤度监控 - 数据拉取（CSV增量模式）
三路资金：北向(moneyflow_hsgt) + 宽基ETF净流入(fund_share) + 两融(margin)
行业维度：申万一级涨跌+成交额(sw_daily) + 行业ETF份额变化(fund_share)
"""
import os, sys, json, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# CSV文件
NORTHBOUND_CSV = os.path.join(CACHE_DIR, 'northbound.csv')
ETF_FLOW_CSV = os.path.join(CACHE_DIR, 'etf_flow.csv')
MARGIN_CSV = os.path.join(CACHE_DIR, 'margin.csv')
SW_DAILY_CSV = os.path.join(CACHE_DIR, 'sw_daily.csv')
INDUSTRY_ETF_CSV = os.path.join(CACHE_DIR, 'industry_etf.csv')

# ── 宽基ETF（用于三路资金）──
BROAD_ETF_MAP = {
    '510300.SH': '沪深300ETF',
    '510050.SH': '上证50ETF',
    '159915.SZ': '创业板ETF',
    '588000.SH': '科创50ETF',
    '512100.SH': '中证1000ETF',
    '510500.SH': '中证500ETF',
    '159338.SZ': 'A500ETF',
}

# ── 申万一级行业 → 代表性ETF ──
INDUSTRY_ETF_MAP = {
    '银行':     '512800.SH',
    '非银金融': '512070.SH',
    '国防军工': '512660.SH',
    '医药生物': '512010.SH',
    '食品饮料': '515180.SH',
    '有色金属': '512400.SH',
    '电子':     '159870.SZ',
    '计算机':   '512580.SH',
    '电力设备': '516160.SH',
    '汽车':     '516110.SH',
    '机械设备': '516950.SH',
    '基础化工': '516220.SH',
    '钢铁':     '515210.SH',
    '煤炭':     '515220.SH',
    '房地产':   '512200.SH',
    '建筑装饰': '516970.SH',
    '通信':     '515880.SH',
    '传媒':     '512980.SH',
    '家用电器': '159996.SZ',
    '农林牧渔': '159825.SZ',
    '公用事业': '159928.SZ',
    '社会服务': '159766.SZ',
    '美容护理': '562800.SH',
    '石油石化': '515790.SH',
    '交通运输': '512690.SH',
}


def ts_api(api_name, fields='', **kwargs):
    """调用 Tushare API"""
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30)
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt+1} failed for {api_name}: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_csv_last_date(csv_path, date_col='trade_date'):
    """获取CSV最后日期"""
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path)
        if df.empty or date_col not in df.columns:
            return None
        return df[date_col].max()
    except:
        return None


def get_start_date(csv_path, default_days=400):
    """获取起始日期：CSV最后日期+1天 或 默认回溯"""
    last = get_csv_last_date(csv_path)
    if last:
        next_day = pd.to_datetime(last) + pd.Timedelta(days=1)
        return next_day.strftime('%Y%m%d')
    return (dt.date.today() - dt.timedelta(days=default_days)).strftime('%Y%m%d')


def fetch_northbound():
    print("拉取北向资金...")
    start = get_start_date(NORTHBOUND_CSV)
    end = dt.date.today().strftime('%Y%m%d')
    
    df = ts_api('moneyflow_hsgt', fields='trade_date,north_money',
                start_date=start, end_date=end)
    if df.empty:
        print("  无新数据")
        return
    
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
    df['north_money'] = pd.to_numeric(df['north_money'], errors='coerce')
    df['north_net'] = df['north_money'] / 100
    df = df[['trade_date', 'north_net']].sort_values('trade_date')
    
    # 合并到CSV
    if os.path.exists(NORTHBOUND_CSV):
        old = pd.read_csv(NORTHBOUND_CSV)
        df = pd.concat([old, df]).drop_duplicates('trade_date').sort_values('trade_date')
    
    df.to_csv(NORTHBOUND_CSV, index=False)
    print(f"  北向资金: {len(df)}条")


def fetch_etf_flow():
    print("拉取宽基ETF份额...")
    start = get_start_date(ETF_FLOW_CSV)
    end = dt.date.today().strftime('%Y%m%d')
    
    all_data = []
    for code, name in BROAD_ETF_MAP.items():
        df = ts_api('fund_share', fields='ts_code,trade_date,fd_share',
                    ts_code=code, start_date=start, end_date=end)
        if not df.empty:
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
            df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
            all_data.append(df)
        time.sleep(0.3)
    
    if not all_data:
        print("  无新数据")
        return
    
    combined = pd.concat(all_data)
    combined = combined.sort_values(['ts_code', 'trade_date'])
    combined['share_chg'] = combined.groupby('ts_code')['fd_share'].diff()
    
    daily = combined.groupby('trade_date')['share_chg'].sum().reset_index()
    daily.columns = ['trade_date', 'etf_share_chg']
    
    # 合并到CSV
    if os.path.exists(ETF_FLOW_CSV):
        old = pd.read_csv(ETF_FLOW_CSV)
        daily = pd.concat([old, daily]).drop_duplicates('trade_date').sort_values('trade_date')
    
    daily.to_csv(ETF_FLOW_CSV, index=False)
    print(f"  ETF份额: {len(daily)}条")


def fetch_margin():
    print("拉取两融数据...")
    start = get_start_date(MARGIN_CSV)
    end = dt.date.today().strftime('%Y%m%d')
    
    df = ts_api('margin', fields='trade_date,rzye,rqye',
                start_date=start, end_date=end)
    if df.empty:
        print("  无新数据")
        return
    
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
    df['rzye'] = pd.to_numeric(df['rzye'], errors='coerce')
    df['rqye'] = pd.to_numeric(df['rqye'], errors='coerce')
    df['margin_balance'] = df['rzye'] + df['rqye']
    df = df[['trade_date', 'margin_balance']].sort_values('trade_date')
    
    # 合并到CSV
    if os.path.exists(MARGIN_CSV):
        old = pd.read_csv(MARGIN_CSV)
        df = pd.concat([old, df]).drop_duplicates('trade_date').sort_values('trade_date')
    
    df.to_csv(MARGIN_CSV, index=False)
    print(f"  两融余额: {len(df)}条")


def fetch_sw_daily():
    print("拉取申万一级行业...")
    start = get_start_date(SW_DAILY_CSV)
    end = dt.date.today().strftime('%Y%m%d')
    
    # 申万一级行业代码
    sw_codes = [
        '801010.SI', '801020.SI', '801030.SI', '801040.SI', '801050.SI',
        '801080.SI', '801110.SI', '801120.SI', '801130.SI', '801140.SI',
        '801150.SI', '801160.SI', '801170.SI', '801180.SI', '801200.SI',
        '801210.SI', '801230.SI', '801710.SI', '801720.SI', '801730.SI',
        '801740.SI', '801750.SI', '801760.SI', '801770.SI', '801780.SI',
        '801790.SI', '801880.SI', '801890.SI', '801950.SI', '801960.SI', '801970.SI'
    ]
    
    all_data = []
    for code in sw_codes:
        df = ts_api('index_daily', fields='ts_code,trade_date,close,pct_chg,amount',
                    ts_code=code, start_date=start, end_date=end)
        if not df.empty:
            all_data.append(df)
        time.sleep(0.2)
    
    if not all_data:
        print("  无新数据")
        return
    
    df = pd.concat(all_data)
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
    df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # 合并到CSV
    if os.path.exists(SW_DAILY_CSV):
        old = pd.read_csv(SW_DAILY_CSV)
        df = pd.concat([old, df]).drop_duplicates(['ts_code', 'trade_date']).sort_values(['ts_code', 'trade_date'])
    
    df.to_csv(SW_DAILY_CSV, index=False)
    print(f"  申万行业: {len(df)}条")


def fetch_industry_etf():
    print("拉取行业ETF份额...")
    start = get_start_date(INDUSTRY_ETF_CSV)
    end = dt.date.today().strftime('%Y%m%d')
    
    all_data = []
    for industry, code in INDUSTRY_ETF_MAP.items():
        df = ts_api('fund_share', fields='ts_code,trade_date,fd_share',
                    ts_code=code, start_date=start, end_date=end)
        if not df.empty:
            df['industry'] = industry
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
            df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
            all_data.append(df)
        time.sleep(0.3)
    
    if not all_data:
        print("  无新数据")
        return
    
    combined = pd.concat(all_data)
    
    # 合并到CSV
    if os.path.exists(INDUSTRY_ETF_CSV):
        old = pd.read_csv(INDUSTRY_ETF_CSV)
        combined = pd.concat([old, combined]).drop_duplicates(['ts_code', 'trade_date']).sort_values(['ts_code', 'trade_date'])
    
    combined.to_csv(INDUSTRY_ETF_CSV, index=False)
    print(f"  行业ETF: {len(combined)}条")


def main():
    print("=" * 50)
    print("拥挤度监控 - 数据拉取（增量模式）")
    print("=" * 50)
    
    fetch_northbound()
    fetch_etf_flow()
    fetch_margin()
    fetch_sw_daily()
    fetch_industry_etf()
    
    print("\n✅ 数据拉取完成")


if __name__ == '__main__':
    main()
