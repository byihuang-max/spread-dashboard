#!/usr/bin/env python3
import hashlib
import requests
import time
import pandas as pd

# 配置信息
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com/fof/subfund/track/list'

def generate_sign(params, app_key):
    """生成签名：按key升序排序，拼接key=value，最后拼接app_key，算md5"""
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_data(page=1, pagesize=50, type=3):
    """获取数据 - type=3 是团队跟踪"""
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': pagesize,
        'type': type,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    print(f"正在请求火富牛API - 团队跟踪 (page={page}, pagesize={pagesize})...")
    response = requests.get(BASE_URL, params=params, timeout=10)
    print(f"响应状态码: {response.status_code}")
    data = response.json()
    
    if data.get('error_code') == 0:
        fund_list = data['data']['list']
        count = data['data']['count']
        print(f"\n获取到 {len(fund_list)} 只基金，总共 {count} 只:")
        for i, f in enumerate(fund_list):
            print(f"  {i+1}. {f.get('fund_short_name')}")
        return fund_list, count
    else:
        print(f"请求错误: {data.get('msg')}")
        return None, 0

if __name__ == '__main__':
    # 获取第一页50只，找GAMT核心资产
    data, total = fetch_data(page=1, pagesize=50, type=3)
    if data:
        df = pd.DataFrame(data)
        df.to_csv('huofuniu_team_track.csv', index=False, encoding='utf-8-sig')
        print(f"\n数据已保存到 huofuniu_team_track.csv")
