#!/usr/bin/env python3
"""
拥挤度监控 - 数据拉取
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
    '银行':     '512800.SH',   # 银行ETF
    '非银金融': '512070.SH',   # 非银ETF
    '国防军工': '512660.SH',   # 军工ETF
    '医药生物': '512010.SH',   # 医药ETF
    '食品饮料': '515180.SH',   # 食品饮料ETF
    '有色金属': '512400.SH',   # 有色ETF
    '电子':     '159870.SZ',   # 电子ETF
    '计算机':   '512580.SH',   # 计算机ETF
    '电力设备': '516160.SH',   # 新能源ETF
    '汽车':     '516110.SH',   # 汽车ETF
    '机械设备': '516950.SH',   # 机械ETF
    '基础化工': '516220.SH',   # 化工ETF（备用159870）
    '钢铁':     '515210.SH',   # 钢铁ETF
    '煤炭':     '515220.SH',   # 煤炭ETF
    '房地产':   '512200.SH',   # 房地产ETF
    '建筑装饰': '516970.SH',   # 基建ETF
    '通信':     '515880.SH',   # 通信ETF
    '传媒':     '512980.SH',   # 传媒ETF
    '家用电器': '159996.SZ',   # 家电ETF
    '农林牧渔': '159825.SZ',   # 农业ETF
    '公用事业': '159928.SZ',   # 消费ETF（公用事业无专属ETF，用电力ETF）
    '社会服务': '159766.SZ',   # 旅游ETF
    '美容护理': '562800.SH',   # 美容ETF
    '石油石化': '515790.SH',   # 石化ETF
    '交通运输': '512690.SH',   # 酒ETF→改交运暂无，用物流ETF
}


def ts_api(api_name, fields='', **kwargs):
    """调用 Tushare API"""
    kwargs.pop('use_official', None)
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


def get_trade_dates(n=250):
    end = dt.date.today().strftime('%Y%m%d')
    start = (dt.date.today() - dt.timedelta(days=n*2)).strftime('%Y%m%d')
    df = ts_api('trade_cal', fields='cal_date,is_open',
                exchange='SSE', start_date=start, end_date=end)
    if df.empty:
        return []
    df = df[df['is_open'] == 1].sort_values('cal_date')
    return df['cal_date'].tolist()[-n:]


def fetch_northbound(trade_dates):
    print("拉取北向资金...")
    df = ts_api('moneyflow_hsgt', fields='trade_date,north_money',
                start_date=trade_dates[0], end_date=trade_dates[-1])
    if df.empty:
        print("  北向数据为空!")
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values('trade_date')
    df['north_money'] = pd.to_numeric(df['north_money'], errors='coerce')
    df['north_net'] = df['north_money'] / 100
    return df[['trade_date', 'north_net']].reset_index(drop=True)


def fetch_etf_flow(trade_dates):
    print("拉取宽基ETF份额...")
    start, end = trade_dates[0], trade_dates[-1]
    all_data = []
    for code, name in BROAD_ETF_MAP.items():
        df = ts_api('fund_share', fields='ts_code,trade_date,fd_share',
                    ts_code=code, start_date=start, end_date=end)
        if df.empty:
            continue
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
        df = df.sort_values('trade_date')
        df['share_chg'] = df['fd_share'].diff()
        all_data.append(df)
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    combined = pd.concat(all_data)
    daily = combined.groupby('trade_date')['share_chg'].sum().reset_index()
    daily.columns = ['trade_date', 'etf_share_chg']
    return daily


def fetch_margin(trade_dates):
    print("拉取两融数据...")
    start, end = trade_dates[0], trade_dates[-1]
    df = ts_api('margin', fields='trade_date,rzye,rqye',
                exchange_id='', start_date=start, end_date=end)
    if df.empty:
        df = ts_api('margin', fields='trade_date,rzye,rqye',
                    start_date=start, end_date=end)
    if df.empty:
        print("  两融数据为空!")
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.groupby('trade_date').agg({'rzye': 'sum', 'rqye': 'sum'}).reset_index()
    df = df.sort_values('trade_date')
    df['rzye'] = pd.to_numeric(df['rzye'], errors='coerce')
    df['rqye'] = pd.to_numeric(df['rqye'], errors='coerce')
    df['margin_balance'] = (df['rzye'] + df['rqye']) / 1e8
    df['margin_chg'] = df['margin_balance'].diff()
    return df[['trade_date', 'margin_balance', 'margin_chg']].reset_index(drop=True)


def fetch_sw_daily(trade_dates):
    """申万一级行业 涨跌幅+成交额，拉30天（用于算MA20拥挤度）"""
    print("拉取申万行业数据...")
    clf = ts_api('index_classify', fields='index_code,industry_name',
                 level='L1', src='SW2021')
    if clf.empty:
        print("  获取行业分类失败!")
        return pd.DataFrame()
    l1_codes = set(clf['index_code'].tolist())

    recent = trade_dates[-30:]
    all_data = []
    for td in recent:
        df = ts_api('sw_daily',
                    fields='ts_code,name,pct_change,amount,trade_date',
                    trade_date=td)
        if not df.empty:
            df = df[df['ts_code'].isin(l1_codes)].copy()
            df['pct_change'] = pd.to_numeric(df['pct_change'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            all_data.append(df)
        time.sleep(0.3)
    if not all_data:
        print("  申万行业数据为空!")
        return pd.DataFrame()
    result = pd.concat(all_data).reset_index(drop=True)
    print(f"  申万一级: {result['name'].nunique()}个, {len(recent)}天")
    return result


def fetch_industry_etf(trade_dates):
    """行业ETF份额变化（最近10天）"""
    print("拉取行业ETF份额...")
    recent = trade_dates[-10:]
    start, end = recent[0], recent[-1]
    all_data = []
    for industry, etf_code in INDUSTRY_ETF_MAP.items():
        df = ts_api('fund_share', fields='ts_code,trade_date,fd_share',
                    ts_code=etf_code, start_date=start, end_date=end)
        if df.empty:
            print(f"  {industry}({etf_code}) 无数据")
            continue
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
        df = df.sort_values('trade_date')
        df['share_chg'] = df['fd_share'].diff()
        df['industry'] = industry
        all_data.append(df)
        time.sleep(0.3)
    if not all_data:
        print("  行业ETF数据为空!")
        return pd.DataFrame()
    return pd.concat(all_data).reset_index(drop=True)


def main():
    print("=" * 50)
    print("拥挤度监控 - 数据拉取")
    print("=" * 50)

    trade_dates = get_trade_dates(250)
    if not trade_dates:
        print("获取交易日失败!")
        sys.exit(1)
    print(f"交易日范围: {trade_dates[0]} ~ {trade_dates[-1]}, 共{len(trade_dates)}天")

    north_df = fetch_northbound(trade_dates)
    etf_df = fetch_etf_flow(trade_dates)
    margin_df = fetch_margin(trade_dates)
    sw_df = fetch_sw_daily(trade_dates)
    ind_etf_df = fetch_industry_etf(trade_dates)

    for name, df, fname in [
        ('北向', north_df, 'northbound.csv'),
        ('宽基ETF', etf_df, 'etf_flow.csv'),
        ('两融', margin_df, 'margin.csv'),
        ('申万行业', sw_df, 'sw_daily.csv'),
        ('行业ETF', ind_etf_df, 'industry_etf.csv'),
    ]:
        if not df.empty:
            df.to_csv(os.path.join(CACHE_DIR, fname), index=False)
            print(f"  {name}: {len(df)}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
