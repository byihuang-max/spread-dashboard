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

def fetch_page(page):
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': 50,
        'type': 3,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    response = requests.get(BASE_URL, params=params, timeout=10)
    data = response.json()
    
    if data.get('error_code') == 0:
        fund_list = data['data']['list']
        print(f"\n=== 第 {page} 页 - {len(fund_list)} 只基金 ===")
        for i, f in enumerate(fund_list):
            print(f"  { (page-1)*50 + i+1 }. {f.get('fund_short_name')}")
        return fund_list
    else:
        print(f"错误: {data.get('msg')}")
        return []

if __name__ == '__main__':
    all_funds = []
    # 获取前4页，共200只，找GAMT核心产品
    for page in [2, 3, 4]:
        page_data = fetch_page(page)
        all_funds.extend(page_data)
        time.sleep(1)
    
    df = pd.DataFrame(all_funds)
    df.to_csv('huofuniu_team_track_page2-4.csv', index=False, encoding='utf-8-sig')
    print(f"\n总共获取 {len(all_funds)} 只基金，已保存")
