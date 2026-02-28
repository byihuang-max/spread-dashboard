#!/usr/bin/env python3
"""
期权情绪面板 - 数据拉取
标的：300ETF(510300) / 500ETF(510500) / 科创50ETF(588000)
数据：opt_basic(合约信息) + opt_daily(日线含OI) + ETF日线(标的价格)
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

# 关注的标的
UNDERLYINGS = {
    'OP000300.SH': {'name': '沪深300',    'etf': '000300.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
    'OP000016.SH': {'name': '上证50',     'etf': '000016.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
    'OP510500.SH': {'name': '中证500ETF', 'etf': '510500.SH', 'exchange': 'SSE',   'price_src': 'fund_daily'},
    'OP000852.SH': {'name': '中证1000',   'etf': '000852.SH', 'exchange': 'CFFEX', 'price_src': 'index_daily'},
}


def ts_api(api_name, fields='', **kwargs):
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
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_trade_dates(n=60):
    end = dt.date.today().strftime('%Y%m%d')
    start = (dt.date.today() - dt.timedelta(days=n * 2)).strftime('%Y%m%d')
    df = ts_api('trade_cal', fields='cal_date,is_open',
                exchange='SSE', start_date=start, end_date=end)
    if df.empty:
        return []
    df = df[df['is_open'] == 1].sort_values('cal_date')
    return df['cal_date'].tolist()[-n:]


def fetch_opt_basic():
    """获取全部活跃期权合约信息"""
    print("拉取期权合约信息...")
    all_contracts = []
    for opt_code, info in UNDERLYINGS.items():
        df = ts_api('opt_basic',
                    fields='ts_code,name,opt_code,call_put,exercise_price,maturity_date,list_date,delist_date,per_unit',
                    exchange=info['exchange'], opt_code=opt_code)
        if df.empty:
            print(f"  {info['name']} 无合约")
            continue
        # 只保留未到期的
        today = dt.date.today().strftime('%Y%m%d')
        df = df[df['delist_date'] >= today].copy()
        df['underlying'] = opt_code
        df['underlying_name'] = info['name']
        all_contracts.append(df)
        print(f"  {info['name']}: {len(df)}个活跃合约")
        time.sleep(0.3)
    if not all_contracts:
        return pd.DataFrame()
    return pd.concat(all_contracts).reset_index(drop=True)


def _read_cache(fname):
    """读取缓存CSV，不存在则返回空DataFrame"""
    path = os.path.join(CACHE_DIR, fname)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def _get_last_date(fname, date_col='trade_date'):
    """获取缓存CSV中最后日期"""
    df = _read_cache(fname)
    if df.empty or date_col not in df.columns:
        return None
    return str(df[date_col].max())


def _save_incremental(new_data, fname, date_col='trade_date'):
    """增量追加写入CSV，去重排序"""
    if new_data.empty:
        return
    path = os.path.join(CACHE_DIR, fname)
    old = _read_cache(fname)
    combined = pd.concat([old, new_data]).drop_duplicates(
        subset=[c for c in [date_col, 'ts_code'] if c in new_data.columns]
    ).sort_values(date_col)
    combined.to_csv(path, index=False)


def fetch_opt_daily(trade_dates):
    """拉取期权日线（按天拉，包含OI）- 增量模式"""
    print("拉取期权日线...")
    cache_fname = 'opt_daily.csv'
    last = _get_last_date(cache_fname)

    if last:
        # 增量：只拉 last_date+1 之后的交易日
        start = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        recent = [td for td in trade_dates if td >= start]
        if not recent:
            print(f"  期权日线已是最新（最后日期 {last}），跳过")
            return pd.DataFrame()
        print(f"  增量拉取期权日线: 从 {recent[0]} 到 {recent[-1]}")
    else:
        recent = trade_dates[-25:]  # 首次全量：25天够算20日分位
        print(f"  首次全量拉取: {recent[0]} ~ {recent[-1]}")

    all_data = []
    for td in recent:
        for ex in sorted(set(info['exchange'] for info in UNDERLYINGS.values())):
            df = ts_api('opt_daily',
                        fields='ts_code,trade_date,close,settle,vol,amount,oi',
                        trade_date=td, exchange=ex)
            if not df.empty:
                all_data.append(df)
            time.sleep(0.35)
    if not all_data:
        print("  期权日线无新数据!")
        return pd.DataFrame()
    result = pd.concat(all_data).reset_index(drop=True)
    print(f"  期权日线新增: {len(result)}条, {len(recent)}天")
    return result


def fetch_etf_daily(trade_dates):
    """拉取标的ETF日线（用于BS模型）- 增量模式"""
    print("拉取标的ETF价格...")
    cache_fname = 'etf_daily.csv'
    last = _get_last_date(cache_fname)

    if last:
        start = (pd.Timestamp(last) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        end = trade_dates[-1]
        if start > end:
            print(f"  ETF日线已是最新（最后日期 {last}），跳过")
            return pd.DataFrame()
        print(f"  增量拉取ETF日线: 从 {start} 到 {end}")
    else:
        start, end = trade_dates[0], trade_dates[-1]
        print(f"  首次全量拉取: {start} ~ {end}")

    all_data = []
    for opt_code, info in UNDERLYINGS.items():
        src = info.get('price_src', 'fund_daily')
        df = ts_api(src,
                    fields='ts_code,trade_date,close',
                    ts_code=info['etf'], start_date=start, end_date=end)
        if df.empty and src == 'fund_daily':
            df = ts_api('daily',
                        fields='ts_code,trade_date,close',
                        ts_code=info['etf'], start_date=start, end_date=end)
        if df.empty and src == 'index_daily':
            df = ts_api('daily',
                        fields='ts_code,trade_date,close',
                        ts_code=info['etf'], start_date=start, end_date=end)
        if not df.empty:
            all_data.append(df)
            print(f"  {info['name']}: {len(df)}条")
        time.sleep(0.3)
    if not all_data:
        return pd.DataFrame()
    return pd.concat(all_data).reset_index(drop=True)


def main():
    print("=" * 50)
    print("期权情绪面板 - 数据拉取")
    print("=" * 50)

    trade_dates = get_trade_dates(60)
    if not trade_dates:
        print("获取交易日失败!")
        sys.exit(1)
    print(f"交易日: {trade_dates[0]} ~ {trade_dates[-1]}, 共{len(trade_dates)}天")

    contracts = fetch_opt_basic()
    opt_daily = fetch_opt_daily(trade_dates)
    etf_daily = fetch_etf_daily(trade_dates)

    # 合约信息：全量覆盖（合约会新增/到期）
    if not contracts.empty:
        contracts.to_csv(os.path.join(CACHE_DIR, 'opt_contracts.csv'), index=False)
        print(f"  合约: {len(contracts)}条（全量刷新）")

    # 期权日线、ETF日线：增量追加
    for name, df, fname in [
        ('期权日线', opt_daily, 'opt_daily.csv'),
        ('ETF日线', etf_daily, 'etf_daily.csv'),
    ]:
        if not df.empty:
            _save_incremental(df, fname)
            total = len(_read_cache(fname))
            print(f"  {name}: 新增{len(df)}条, 总计{total}条")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
