#!/usr/bin/env python3
"""经济基本面 - 数据拉取: 原有 PMI/CPI/PPI + MCP 月频增长/信用字段"""
import os, time, json, datetime as dt
import requests
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'
MCP_CONFIG = '/Users/apple/.openclaw/extensions/ifind-finance-data/mcp_config.json'
MCP_BASE = 'https://api-mcp.51ifind.com:8643/ds-mcp-servers/hexin-ifind-ds-edb-mcp'

MCP_FIELDS = {
    'industrial_production_yoy': '规模以上工业增加值:当月同比',
    'retail_sales_yoy': '社会消费品零售总额:当月同比',
    'exports_yoy': '出口金额(人民币计价):总值:累计同比',
    'fai_ytd_yoy': '固定资产投资(不含农户)完成额:累计同比',
    'manufacturing_investment_ytd_yoy': '固定资产投资(不含农户)完成额:制造业:累计同比',
    'infrastructure_investment_ytd_yoy': '固定资产投资(不含农户)完成额:基础设施建设投资:累计同比',
    'real_estate_investment_ytd_yoy': '房地产开发投资:累计同比',
    'tsf_stock_yoy': '社会融资规模存量:期末同比',
    'tsf_stock_value': '社会融资规模存量:期末值',
    'gov_bond_share_in_tsf': '社会融资规模存量:政府债券:占比',
    'household_medium_long_loan': '金融机构:人民币贷款:累计增加:住户:中长期',
    'corp_medium_long_loan': '金融机构:人民币贷款:累计增加:企(事)业单位:中长期',
    'm1_yoy': 'M1(货币):同比',
    'm2_yoy': 'M2(货币和准货币):同比',
    'property_sales_area_yoy': '商品房销售面积:累计同比',
}


def ts_api(api_name, fields='', **kwargs):
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    for attempt in range(3):
        try:
            r = requests.post(TUSHARE_URL, json=body, timeout=30, proxies={'http': None, 'https': None})
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


def read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_month(csv_path, date_col='month'):
    df = read_csv(csv_path)
    if df.empty:
        return None
    return str(df[date_col].max())


def next_month(yyyymm_str):
    y, m = int(yyyymm_str[:4]), int(yyyymm_str[4:6])
    m += 1
    if m > 12:
        y += 1
        m = 1
    return f"{y:04d}{m:02d}"


def incremental_save(new_df, csv_path, date_col='month'):
    if new_df.empty:
        print('  无新数据')
        return
    old = read_csv(csv_path)
    combined = pd.concat([old, new_df])
    combined[date_col] = combined[date_col].astype(str)
    combined = combined.drop_duplicates(subset=[date_col]).sort_values(date_col)
    combined.to_csv(csv_path, index=False)
    print(f"  新增 {len(new_df)} 条, 合计 {len(combined)} 条")


class EDBMCPClient:
    def __init__(self):
        cfg = json.load(open(MCP_CONFIG, 'r', encoding='utf-8'))
        self.auth_token = cfg['auth_token']
        self.session_id = None
        self.req_id = 0

    def _headers(self):
        h = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'Authorization': self.auth_token,
        }
        if self.session_id:
            h['Mcp-Session-Id'] = self.session_id
        return h

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    def init(self):
        if self.session_id:
            return
        payload = {
            'jsonrpc': '2.0',
            'id': self._next_id(),
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-03-26',
                'capabilities': {},
                'clientInfo': {'name': 'gamt-fundamentals', 'version': '1.0.0'},
            },
        }
        resp = requests.post(MCP_BASE, json=payload, headers=self._headers(), verify=False, timeout=30)
        resp.raise_for_status()
        self.session_id = resp.headers.get('Mcp-Session-Id')
        notify = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
        requests.post(MCP_BASE, json=notify, headers=self._headers(), verify=False, timeout=10)

    def get_edb_data(self, query):
        self.init()
        payload = {
            'jsonrpc': '2.0',
            'id': self._next_id(),
            'method': 'tools/call',
            'params': {'name': 'get_edb_data', 'arguments': {'query': query}},
        }
        resp = requests.post(MCP_BASE, json=payload, headers=self._headers(), verify=False, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        content = (((data or {}).get('result') or {}).get('content') or [])
        if not content:
            return None
        text = content[0].get('text', '')
        outer = json.loads(text)
        datas = ((outer.get('data') or {}).get('datas') or [])
        if not datas:
            return None
        return datas[0].get('data')


def fetch_mcp_series(client, field_key, indicator_name, start='202301', end=None):
    end = end or dt.date.today().strftime('%Y%m')
    print(f'拉取 MCP {field_key}... ({indicator_name})')
    try:
        data = client.get_edb_data(f'{indicator_name} {start}-{end}')
        if not data or 'data' not in data:
            print('  无返回')
            return pd.DataFrame()
        rows = data['data']
        if not rows:
            print('  空数据')
            return pd.DataFrame()
        out = []
        for row in rows:
            if len(row) < 2:
                continue
            date_str = str(row[0])[:10]
            val = pd.to_numeric(row[1], errors='coerce')
            if pd.isna(val):
                continue
            month = date_str[:7].replace('-', '')
            out.append({'month': month, field_key: float(val)})
        df = pd.DataFrame(out)
        if df.empty:
            print('  解析后为空')
            return df
        return df.groupby('month', as_index=False).last().sort_values('month')
    except Exception as e:
        print(f'  MCP failed: {e}')
        return pd.DataFrame()


def merge_field_csv(field_key, df):
    path = os.path.join(CACHE_DIR, f'{field_key}.csv')
    incremental_save(df, path)


def main():
    print('=' * 50)
    print('经济基本面 - 数据拉取 (含 MCP 月频字段)')
    print('=' * 50)

    default_start = (dt.date.today() - dt.timedelta(days=750)).strftime('%Y%m')
    end_m = dt.date.today().strftime('%Y%m')

    pmi_path = os.path.join(CACHE_DIR, 'pmi.csv')
    last = get_last_month(pmi_path)
    start_m = next_month(last) if last else default_start
    print(f'拉取 PMI... (从 {start_m} 到 {end_m})')
    if start_m <= end_m:
        pmi = ts_api('cn_pmi', start_month=start_m, end_month=end_m)
        if not pmi.empty:
            col_map = {}
            for c in pmi.columns:
                cl = c.upper()
                if cl == 'MONTH': col_map[c] = 'month'
                elif cl == 'PMI010000': col_map[c] = 'pmi'
                elif cl == 'PMI020100': col_map[c] = 'pmi_nmp'
                elif cl == 'PMI': col_map[c] = 'pmi'
                elif cl == 'PMI_NMP': col_map[c] = 'pmi_nmp'
            pmi = pmi.rename(columns=col_map)
            keep = [c for c in ['month', 'pmi', 'pmi_nmp'] if c in pmi.columns]
            pmi = pmi[keep]
            incremental_save(pmi, pmi_path)

    time.sleep(0.5)
    cpi_path = os.path.join(CACHE_DIR, 'cpi.csv')
    last = get_last_month(cpi_path)
    start_m = next_month(last) if last else default_start
    print(f'拉取 CPI... (从 {start_m} 到 {end_m})')
    if start_m <= end_m:
        cpi = ts_api('cn_cpi', fields='month,nt_yoy', start_month=start_m, end_month=end_m)
        incremental_save(cpi, cpi_path)

    time.sleep(0.5)
    ppi_path = os.path.join(CACHE_DIR, 'ppi.csv')
    last = get_last_month(ppi_path)
    start_m = next_month(last) if last else default_start
    print(f'拉取 PPI... (从 {start_m} 到 {end_m})')
    if start_m <= end_m:
        ppi = ts_api('cn_ppi', fields='month,ppi_yoy', start_month=start_m, end_month=end_m)
        incremental_save(ppi, ppi_path)

    print('\n拉取 MCP 月频字段...')
    client = EDBMCPClient()
    for idx, (field_key, indicator_name) in enumerate(MCP_FIELDS.items()):
        df = fetch_mcp_series(client, field_key, indicator_name, start='202301', end=end_m)
        merge_field_csv(field_key, df)
        if idx < len(MCP_FIELDS) - 1:
            time.sleep(1.2)

    print('\n数据拉取完成!')


if __name__ == '__main__':
    requests.packages.urllib3.disable_warnings()  # type: ignore
    main()
