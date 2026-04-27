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
    # 移除sign参数，对key升序排序
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    # 拼接
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    # md5
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_data(page=1, pagesize=20, type=1):
    """获取数据"""
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': pagesize,
        'type': type,
        'tm': tm
    }
    # 生成签名
    params['sign'] = generate_sign(params, APP_KEY)
    
    print(f"正在请求火富牛API...")
    print(f"参数: {params}")
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        print(f"响应状态码: {response.status_code}")
        data = response.json()
        print(f"响应: {data}")
        
        if data.get('error_code') == 0:
            fund_list = data['data']['list']
            print(f"\n获取到 {len(fund_list)} 只基金:")
            for f in fund_list:
                print(f"  - {f.get('fund_short_name')} / {f.get('fund_name')}")
            return fund_list
        else:
            print(f"请求错误: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"请求异常: {e}")
        return None

if __name__ == '__main__':
    # 获取全部20只产品（pagesize=20）
    data = fetch_data(page=1, pagesize=20, type=1)
    if data:
        df = pd.DataFrame(data)
        df.to_csv('huofuniu_fund_list.csv', index=False, encoding='utf-8-sig')
        print(f"\n数据已保存到 huofuniu_fund_list.csv")
        print(df)
