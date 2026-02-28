#!/usr/bin/env python3
"""
拥挤度监控 - 数据拉取
三路资金：北向(moneyflow_hsgt) + ETF净流入(fund_share) + 两融(margin_detail)
行业资金流向：moneyflow_ind_dc (申万行业)
"""
import os, sys, json, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL_PRIVATE = 'https://api.tushare.pro'
TUSHARE_URL_OFFICIAL = 'https://api.tushare.pro'
TUSHARE_URL = TUSHARE_URL_OFFICIAL  # 私有服务器不稳定，统一用官方

# 宽基ETF: 代码 -> 名称
ETF_MAP = {
    '510300.SH': '沪深300ETF',
    '510050.SH': '上证50ETF',
    '159915.SZ': '创业板ETF',
    '588000.SH': '科创50ETF',
    '512100.SH': '中证1000ETF',
    '510500.SH': '中证500ETF',
    '159338.SZ': 'A500ETF',
}

def ts_api(api_name, fields='', **kwargs):
    """调用 Tushare API"""
    extra = kwargs.pop('use_official', None)  # ignored, always official
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params,
    }
    if fields:
        body['fields'] = fields
    url = TUSHARE_URL
    for attempt in range(3):
        try:
            r = requests.post(url, json=body, timeout=30)
            j = r.json()
            if j.get('code') != 0:
                print(f"  API error {api_name}: {j.get('msg')}")
                return pd.DataFrame()
            data = j.get('data', {})
            cols = data.get('fields', [])
            items = data.get('items', [])
            return pd.DataFrame(items, columns=cols)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed for {api_name}: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_trade_dates(n=250):
    """获取最近n个交易日"""
    end = dt.date.today().strftime('%Y%m%d')
    start = (dt.date.today() - dt.timedelta(days=n*2)).strftime('%Y%m%d')
    df = ts_api('trade_cal', fields='cal_date,is_open',
                exchange='SSE', start_date=start, end_date=end, use_official=True)
    if df.empty:
        return []
    df = df[df['is_open'] == 1].sort_values('cal_date')
    return df['cal_date'].tolist()[-n:]


def fetch_northbound(trade_dates):
    """北向资金 - 每日净买入"""
    print("拉取北向资金...")
    start = trade_dates[0]
    end = trade_dates[-1]
    df = ts_api('moneyflow_hsgt',
                fields='trade_date,north_money',
                start_date=start, end_date=end)
    if df.empty:
        print("  北向数据为空!")
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values('trade_date')
    # north_money 单位是百万，转为亿
    df['north_money'] = pd.to_numeric(df['north_money'], errors='coerce')
    df['north_net'] = df['north_money'] / 100
    return df[['trade_date', 'north_net']].reset_index(drop=True)


def fetch_etf_flow(trade_dates):
    """ETF份额变化 -> 净流入估算"""
    print("拉取ETF份额...")
    start = trade_dates[0]
    end = trade_dates[-1]
    all_data = []
    for code, name in ETF_MAP.items():
        df = ts_api('fund_share',
                    fields='ts_code,trade_date,fd_share',
                    ts_code=code, start_date=start, end_date=end)
        if df.empty:
            print(f"  {name}({code}) 无数据")
            continue
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['fd_share'] = pd.to_numeric(df['fd_share'], errors='coerce')
        df = df.sort_values('trade_date')
        df['share_chg'] = df['fd_share'].diff()
        df['etf_name'] = name
        all_data.append(df)
        time.sleep(0.3)

    if not all_data:
        return pd.DataFrame()
    
    combined = pd.concat(all_data)
    # 汇总每日总份额变化
    daily = combined.groupby('trade_date')['share_chg'].sum().reset_index()
    daily.columns = ['trade_date', 'etf_share_chg']
    return daily


def fetch_margin(trade_dates):
    """两融余额"""
    print("拉取两融数据...")
    start = trade_dates[0]
    end = trade_dates[-1]
    df = ts_api('margin',
                fields='trade_date,rzye,rqye',
                exchange_id='', start_date=start, end_date=end)
    if df.empty:
        # 试试不带 exchange_id
        df = ts_api('margin',
                    fields='trade_date,rzye,rqye',
                    start_date=start, end_date=end)
    if df.empty:
        print("  两融数据为空!")
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    # 可能有多个交易所的数据，按日汇总
    df = df.groupby('trade_date').agg({'rzye': 'sum', 'rqye': 'sum'}).reset_index()
    df = df.sort_values('trade_date')
    # rzye 单位元，转亿
    df['rzye'] = pd.to_numeric(df['rzye'], errors='coerce')
    df['rqye'] = pd.to_numeric(df['rqye'], errors='coerce')
    df['margin_balance'] = (df['rzye'] + df['rqye']) / 1e8
    df['margin_chg'] = df['margin_balance'].diff()
    return df[['trade_date', 'margin_balance', 'margin_chg']].reset_index(drop=True)


def fetch_industry_flow(trade_dates):
    """申万一级行业涨跌幅+成交额（sw_daily）"""
    print("拉取申万行业数据...")
    
    # 1. 获取申万一级行业代码
    clf = ts_api('index_classify', fields='index_code,industry_name',
                 level='L1', src='SW2021')
    if clf.empty:
        print("  获取行业分类失败!")
        return pd.DataFrame()
    l1_codes = set(clf['index_code'].tolist())
    l1_names = dict(zip(clf['index_code'], clf['industry_name']))
    
    # 2. 拉最近10个交易日的 sw_daily
    recent = trade_dates[-10:]
    all_data = []
    for td in recent:
        df = ts_api('sw_daily',
                    fields='ts_code,name,pct_change,amount,trade_date',
                    trade_date=td)
        if not df.empty:
            # 只保留一级行业
            df = df[df['ts_code'].isin(l1_codes)].copy()
            df['pct_change'] = pd.to_numeric(df['pct_change'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            all_data.append(df)
        time.sleep(0.3)
    
    if not all_data:
        print("  申万行业数据为空!")
        return pd.DataFrame()
    
    result = pd.concat(all_data).reset_index(drop=True)
    print(f"  申万一级行业: {result['name'].nunique()}个, {len(recent)}个交易日")
    return result


def main():
    print("=" * 50)
    print("拥挤度监控 - 数据拉取")
    print("=" * 50)
    
    trade_dates = get_trade_dates(250)
    if not trade_dates:
        print("获取交易日失败!")
        sys.exit(1)
    print(f"交易日范围: {trade_dates[0]} ~ {trade_dates[-1]}, 共{len(trade_dates)}天")
    
    # 拉取三路数据
    north_df = fetch_northbound(trade_dates)
    etf_df = fetch_etf_flow(trade_dates)
    margin_df = fetch_margin(trade_dates)
    industry_df = fetch_industry_flow(trade_dates)
    
    # 保存缓存
    if not north_df.empty:
        north_df.to_csv(os.path.join(CACHE_DIR, 'northbound.csv'), index=False)
        print(f"  北向: {len(north_df)}条")
    if not etf_df.empty:
        etf_df.to_csv(os.path.join(CACHE_DIR, 'etf_flow.csv'), index=False)
        print(f"  ETF: {len(etf_df)}条")
    if not margin_df.empty:
        margin_df.to_csv(os.path.join(CACHE_DIR, 'margin.csv'), index=False)
        print(f"  两融: {len(margin_df)}条")
    if not industry_df.empty:
        industry_df.to_csv(os.path.join(CACHE_DIR, 'industry_flow.csv'), index=False)
        print(f"  行业: {len(industry_df)}条")
    
    print("\n数据拉取完成!")
    return north_df, etf_df, margin_df, industry_df


if __name__ == '__main__':
    main()
