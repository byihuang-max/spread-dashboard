#!/usr/bin/env python3
import hashlib
import requests
import time
import pandas as pd

APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com/fof/subfund/track/list'

def generate_sign(params, app_key):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_gamt_core():
    """获取GAMT核心资产分类（type=4）"""
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': 1,
        'pagesize': 50,
        'type': 4,  # 4 = 入池产品 = GAMT核心资产
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    print(f"正在请求 GAMT核心资产 列表 (type=4)...")
    response = requests.get(BASE_URL, params=params, timeout=10)
    print(f"响应状态码: {response.status_code}")
    data = response.json()
    
    if data.get('error_code') == 0:
        fund_list = data['data']['list']
        count = data['data']['count']
        print(f"\n✅ 获取成功！总共 {count} 只，本页 {len(fund_list)} 只:\n")
        for i, f in enumerate(fund_list):
            print(f"  {i+1}. {f.get('fund_short_name')}")
        return fund_list
    else:
        print(f"❌ 请求错误: {data.get('msg')}")
        return None

if __name__ == '__main__':
    data = fetch_gamt_core()
    if data:
        df = pd.DataFrame(data)
        df.to_csv('gamt_core_fund_list.csv', index=False, encoding='utf-8-sig')
        print(f"\n📁 数据已保存到 gamt_core_fund_list.csv")
