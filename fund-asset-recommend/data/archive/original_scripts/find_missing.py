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

def search_name(keyword, page=1, pagesize=50):
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': pagesize,
        'type': 3,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    response = requests.get(BASE_URL, params=params, timeout=10)
    data = response.json()
    
    if data.get('error_code') == 0:
        fund_list = data['data']['list']
        found = [f for f in fund_list if keyword in f.get('fund_short_name', '')]
        if found:
            print(f"\n🔍 找到 '{keyword}':")
            for f in found:
                print(f"  - {f.get('fund_short_name')}")
        else:
            print(f"\n🔍 '{keyword}' 未找到在第 {page} 页")
        return found
    return []

if __name__ == '__main__':
    keywords = ['涌泉君安', '波克', '顾锝', '积沐领航', '太衍光年']
    all_found = []
    for keyword in keywords:
        # 检查page 13-15
        for page in [13, 14, 15, 16]:
            print(f"\n=== 搜索 page {page}, keyword: {keyword} ===")
            found = search_name(keyword, page=page, pagesize=50)
            all_found.extend(found)
            time.sleep(1)
    
    print(f"\n✅ 搜索完成，总共找到 {len(all_found)} 只:")
    df = pd.DataFrame(all_found)
    df.to_csv('missing_found.csv', index=False, encoding='utf-8-sig')
    print(df)
