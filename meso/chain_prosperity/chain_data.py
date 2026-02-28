#!/usr/bin/env python3
"""
中观景气度 - 产业链数据拉取
4条链: 科技芯片 / 创新药 / 周期 / 消费
"""
import os, sys, time, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAyLTA5IDE5OjE3OjQwIn0=.eyJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyIjp7ImFjY291bnQiOiJncnN6aDAwMSIsImF1dGhVc2VySW5mbyI6eyJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbXSwiaGFzQUlQcmVkaWN0IjpmYWxzZSwiaGFzQUlUYWxrIjpmYWxzZSwiaGFzQ0lDQyI6ZmFsc2UsImhhc0NTSSI6ZmFsc2UsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1heE9uTGluZSI6MSwibm9EaXNrIjpmYWxzZSwicHJvZHVjdFR5cGUiOiJTVVBFUkNPTU1BTkRQUk9EVUNUIiwicmVmcmVzaFRva2VuRXhwaXJlZFRpbWUiOiIyMDI2LTAzLTA5IDE5OjAwOjU1Iiwic2Vzc3Npb24iOiI0YzRjYjhhNTdiNWQwYzA3N2UxNTEwMzIxN2M2YWNjYSIsInNpZEluZm8iOns2NDoiMTExMTExMTExMTExMTExMTExMTExMTExIiwxOiIxMDEiLDI6IjEiLDY3OiIxMDExMTExMTExMTExMTExMTExMTExMTEiLDM6IjEiLDY5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw1OiIxIiw2OiIxIiw3MToiMTExMTExMTExMTExMTExMTExMTExMTAwIiw3OiIxMTExMTExMTExMSIsODoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDEiLDEzODoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTM5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDA6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQyOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDM6IjExIiw4MDoiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MToiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MjoiMTExMTExMTExMTExMTExMTExMTEwMTEwIiw4MzoiMTExMTExMTExMTExMTExMTExMDAwMDAwIiw4NToiMDExMTExMTExMTExMTExMTExMTExMTExIiw4NzoiMTExMTExMTEwMDExMTExMDExMTExMTExIiw4OToiMTExMTExMTEwMTEwMTExMTExMTAxMTExIiw5MDoiMTExMTEwMTExMTExMTExMTExMTExMTExMTAiLDkzOiIxMTExMTExMTExMTExMTExMTAwMDAxMTExIiw5NDoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsOTY6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk5OiIxMDAiLDEwMDoiMTExMTAxMTExMTExMTExMTExMCIsMTAyOiIxIiw0NDoiMTEiLDEwOToiMSIsNTM6IjExMTExMTExMTExMTExMTExMTExMTExMSIsNTQ6IjExMDAwMDAwMDAxMTAwMDAwMTAxMDAwMDAxMDAxMDAwMDAwIiw1NzoiMDAwMDAwMDAwMDAwMDAwMDAwMDAxMDAwMDAwMDAiLDYyOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDYzOiIxMTExMTExMTExMTExMTExMTExMTExMTEifSwidGltZXN0YW1wIjoiMTc3MDYzNTg2MDcxOSIsInRyYW5zQXV0aCI6ZmFsc2UsInR0bFZhbHVlIjowLCJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyVHlwZSI6Ik9GRklDSUFMIiwid2lmaW5kTGltaXRNYXAiOnt9fX0=.7AAB9445C9074F4FD9C933A4ECF96C3359428E3393255673AFE507504D9E7270'


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
                print(f"  API error {api_name}: {j.get('msg','')[:60]}")
                return pd.DataFrame()
            data = j.get('data', {})
            return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return pd.DataFrame()


def get_ifind_token():
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
    except Exception as e:
        print(f"  iFind token error: {e}")
    return None


def ifind_rt(access_token, codes, indicators='latest,change,pct_change'):
    try:
        r = requests.post(f'{IFIND_BASE}/real_time_quotation',
            json={'codes': codes, 'indicators': indicators},
            headers={'Content-Type': 'application/json', 'access_token': access_token},
            timeout=15)
        return r.json()
    except Exception as e:
        print(f"  iFind error: {e}")
        return None


# ═══════════════════════════════════════════
# 链配置: 每条链的上中下游 + 数据指标
# ═══════════════════════════════════════════

# ETF 代码 → 用于 fund_daily (价格) + fund_share (份额)
CHAIN_ETFS = {
    'tech': {
        'upstream': [],  # SOXX via iFind
        'midstream': ['512480.SH'],  # 芯片ETF
        'downstream': ['159732.SZ', '588000.SH'],  # 消费电子ETF, 科创50ETF
    },
    'pharma': {
        'upstream': [],  # CRO用行业指数
        'midstream': ['159992.SZ'],  # 创新药ETF
        'downstream': ['512010.SH'],  # 医药ETF
    },
    'cycle': {
        'upstream': [],  # 期货
        'midstream': [],  # 期货
        'downstream': ['516950.SH', '512200.SH'],  # 基建ETF, 房地产ETF
    },
    'consumer': {
        'upstream': [],  # 期货
        'midstream': ['512690.SH'],  # 白酒ETF
        'downstream': ['159928.SZ'],  # 消费ETF
    },
}

# 期货品种 (用 fut_mapping 拿主力合约)
FUTURES = {
    'cycle_up': ['CU.SHF', 'AL.SHF', 'I.DCE', 'ZC.ZCE'],     # 铜/铝/铁矿/煤炭
    'cycle_mid': ['RB.SHF', 'FG.ZCE', 'SA.ZCE'],               # 螺纹/玻璃/纯碱
    'consumer_up': ['LH.DCE', 'A.DCE', 'P.DCE'],                # 生猪/大豆/棕榈油
}

FUTURES_NAMES = {
    'CU.SHF': '铜', 'AL.SHF': '铝', 'I.DCE': '铁矿石', 'ZC.ZCE': '煤炭',
    'RB.SHF': '螺纹钢', 'FG.ZCE': '玻璃', 'SA.ZCE': '纯碱',
    'LH.DCE': '生猪', 'A.DCE': '大豆', 'P.DCE': '棕榈油',
}

# 申万行业指数
SW_INDICES = {
    'tech': '801080.SI',     # 电子
    'pharma': '801150.SI',   # 医药生物
    'cycle_steel': '801040.SI',  # 钢铁
    'cycle_chem': '801030.SI',   # 基础化工
    'consumer_food': '801120.SI', # 食品饮料
    'consumer_retail': '801200.SI', # 商贸零售
}

ETF_NAMES = {
    '512480.SH': '芯片ETF', '159732.SZ': '消费电子ETF', '588000.SH': '科创50ETF',
    '159992.SZ': '创新药ETF', '512010.SH': '医药ETF',
    '516950.SH': '基建ETF', '512200.SH': '房地产ETF',
    '512690.SH': '白酒ETF', '159928.SZ': '消费ETF',
}

# iFind 海外指标
IFIND_CODES = {
    'SOXX': 'SOXX.O',  # 费城半导体ETF
}


def read_cached_csv(path):
    """读取已有缓存CSV，不存在则返回空DataFrame"""
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_date(csv_path, date_col='trade_date'):
    """获取缓存CSV中最后一个日期（字符串），无数据返回None"""
    df = read_cached_csv(csv_path)
    if df.empty or date_col not in df.columns:
        return None
    return str(df[date_col].max())


def incremental_start(csv_path, default_start, date_col='trade_date', label=''):
    """根据缓存CSV决定增量起始日期"""
    last = get_last_date(csv_path, date_col)
    if last:
        start = (pd.Timestamp(str(last)) + pd.Timedelta(days=1)).strftime('%Y%m%d')
        if label:
            print(f"  增量拉取 {label}: 从 {start} 到今天")
        return start
    return default_start


def save_incremental(csv_path, new_df, date_col='trade_date'):
    """将新数据追加到已有CSV，去重+排序"""
    if new_df.empty:
        return
    old = read_cached_csv(csv_path)
    if old.empty:
        combined = new_df
    else:
        combined = pd.concat([old, new_df])
        # 用 ts_code+date_col 去重（多品种共存的CSV）
        dedup_cols = [date_col]
        if 'ts_code' in combined.columns:
            dedup_cols = ['ts_code', date_col]
        if 'generic' in combined.columns:
            dedup_cols.append('generic')
        combined = combined.drop_duplicates(subset=dedup_cols).sort_values(date_col)
    combined.to_csv(csv_path, index=False)


def main():
    print("=" * 50)
    print("中观景气度 - 产业链数据拉取")
    print("=" * 50)

    end = dt.date.today().strftime('%Y%m%d')
    start_60d = (dt.date.today() - dt.timedelta(days=400)).strftime('%Y%m%d')
    start_5d = (dt.date.today() - dt.timedelta(days=10)).strftime('%Y%m%d')

    # ── 1. ETF价格 (fund_daily) ──
    print("\n[1/5] 拉取ETF价格...")
    all_etfs = set()
    for chain in CHAIN_ETFS.values():
        for tier in chain.values():
            all_etfs.update(tier)

    etf_price_path = os.path.join(CACHE_DIR, 'etf_price.csv')
    etf_price_start = incremental_start(etf_price_path, start_60d, 'trade_date', 'ETF价格')

    if etf_price_start <= end:
        etf_price_data = []
        for code in sorted(all_etfs):
            df = ts_api('fund_daily', ts_code=code,
                         start_date=etf_price_start, end_date=end,
                         fields='ts_code,trade_date,close,pre_close,pct_chg')
            if not df.empty:
                etf_price_data.append(df)
                print(f"  {ETF_NAMES.get(code, code)}: {len(df)}条")
            time.sleep(0.3)

        if etf_price_data:
            save_incremental(etf_price_path, pd.concat(etf_price_data), 'trade_date')
    else:
        print("  已是最新，跳过")

    # ── 2. ETF份额 (fund_share) ──
    print("\n[2/5] 拉取ETF份额...")
    etf_share_path = os.path.join(CACHE_DIR, 'etf_share.csv')
    etf_share_start = incremental_start(etf_share_path, start_60d, 'trade_date', 'ETF份额')

    if etf_share_start <= end:
        etf_share_data = []
        for code in sorted(all_etfs):
            df = ts_api('fund_share', ts_code=code,
                         start_date=etf_share_start, end_date=end)
            if not df.empty:
                etf_share_data.append(df[['ts_code', 'trade_date', 'fd_share']])
                print(f"  {ETF_NAMES.get(code, code)}: {len(df)}条")
            time.sleep(0.3)

        if etf_share_data:
            save_incremental(etf_share_path, pd.concat(etf_share_data), 'trade_date')
    else:
        print("  已是最新，跳过")

    # ── 3. 期货主力合约 ──
    print("\n[3/5] 拉取期货主力合约...")
    # 先拿映射
    all_fut_codes = set()
    for codes in FUTURES.values():
        all_fut_codes.update(codes)

    mappings = {}
    for code in sorted(all_fut_codes):
        # 郑商所用 fut_basic 找主力（mapping不返回数据）
        exchange = code.split('.')[-1]
        if exchange in ('ZCE',):
            symbol_prefix = code.split('.')[0]
            basics = ts_api('fut_basic', exchange='CZCE', fut_type='1',
                            fields='ts_code,symbol,name,list_date,delist_date')
            if not basics.empty:
                matched = basics[basics['symbol'].str.startswith(symbol_prefix)]
                matched = matched[matched['delist_date'] >= end]
                matched = matched.sort_values('delist_date')
                if not matched.empty:
                    # 取最近到期的（主力合约）
                    mappings[code] = matched.iloc[0]['ts_code']
                    print(f"  {FUTURES_NAMES.get(code, code)} 主力(CZCE): {mappings[code]}")
        else:
            df = ts_api('fut_mapping', ts_code=code,
                         start_date=start_5d, end_date=end)
            if not df.empty:
                df = df.sort_values('trade_date', ascending=False)
                mappings[code] = df.iloc[0]['mapping_ts_code']
                print(f"  {FUTURES_NAMES.get(code, code)} 主力: {mappings[code]}")
        time.sleep(0.3)

    # 拿期货日线（增量）
    futures_path = os.path.join(CACHE_DIR, 'futures.csv')
    futures_start = incremental_start(futures_path, start_60d, 'trade_date', '期货日线')

    if futures_start <= end:
        fut_data = []
        for generic, main_code in mappings.items():
            df = ts_api('fut_daily', ts_code=main_code,
                         start_date=futures_start, end_date=end,
                         fields='ts_code,trade_date,close,settle,vol,oi')
            if not df.empty:
                df['generic'] = generic
                df['name'] = FUTURES_NAMES.get(generic, generic)
                fut_data.append(df)
                print(f"  {FUTURES_NAMES.get(generic, generic)}: {len(df)}条")
            time.sleep(0.3)

        if fut_data:
            save_incremental(futures_path, pd.concat(fut_data), 'trade_date')
    else:
        print("  已是最新，跳过")

    # ── 4. 申万行业指数 ──
    print("\n[4/5] 拉取申万行业指数...")
    sw_path = os.path.join(CACHE_DIR, 'sw_indices.csv')
    sw_start = incremental_start(sw_path, start_60d, 'trade_date', '申万指数')

    if sw_start <= end:
        sw_data = []
        for key, code in SW_INDICES.items():
            df = ts_api('sw_daily', ts_code=code,
                         start_date=sw_start, end_date=end,
                         fields='ts_code,trade_date,name,close,pct_change')
            if not df.empty:
                sw_data.append(df)
                print(f"  {df.iloc[0]['name'] if 'name' in df.columns else key}: {len(df)}条")
            time.sleep(0.3)

        # 补充南华工业品指数
        nh = ts_api('index_daily', ts_code='NHCI.NH',
                    start_date=sw_start, end_date=end,
                    fields='ts_code,trade_date,close,pct_chg')
        if not nh.empty:
            nh['name'] = '南华工业品'
            sw_data.append(nh)
            print(f"  南华工业品: {len(nh)}条")

        if sw_data:
            save_incremental(sw_path, pd.concat(sw_data), 'trade_date')
    else:
        print("  已是最新，跳过")

    # ── 5. iFind海外 (SOXX) ──
    print("\n[5/5] 拉取iFind海外数据...")
    at = get_ifind_token()
    if at:
        resp = ifind_rt(at, 'SOXX.O', 'latest,change,pct_change')
        if resp and resp.get('errorcode') == 0:
            tables = resp.get('tables', [])
            ifind_data = []
            for t in tables:
                code = t.get('thscode', '')
                vals = t.get('table', {})
                ifind_data.append({
                    'code': code,
                    'latest': vals.get('latest', [None])[0],
                    'change': vals.get('change', [None])[0],
                    'pct_change': vals.get('pct_change', [None])[0],
                })
            if ifind_data:
                pd.DataFrame(ifind_data).to_csv(os.path.join(CACHE_DIR, 'ifind_global.csv'), index=False)
                print(f"  SOXX: {ifind_data[0]['latest']}")
    else:
        print("  iFind token 获取失败")

    print("\n数据拉取完成!")


if __name__ == '__main__':
    main()
