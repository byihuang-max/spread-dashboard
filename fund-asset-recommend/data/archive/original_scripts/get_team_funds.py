import requests
import hashlib
import time
import pandas as pd

# 配置
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com'

def generate_sign(params, app_key):
    sorted_items = sorted([(k, v) for k, v in params.items() if k != 'sign'])
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_items]) + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

# 获取团队跟踪(type=3)的基金列表
url = f'{BASE_URL}/fof/subfund/track/list'
tm = int(time.time())
params = {
    'app_id': APP_ID,
    'page': 1,
    'pagesize': 50,
    'type': 3,  # 3.团队跟踪
    'tm': tm
}
params['sign'] = generate_sign(params, APP_KEY)

response = requests.get(url, params=params, timeout=(5, 15))
data = response.json()

if data.get('error_code') != 0:
    print(f"错误: {data.get('msg')}")
else:
    funds = data.get('data', {}).get('list', [])
    print(f"团队跟踪(type=3)一共 {len(funds)} 只产品:\n")
    for i, f in enumerate(funds, 1):
        print(f"{i}. {f.get('fund_short_name')} - {f.get('register_number')}")
    
    # 保存到文件
    df = pd.DataFrame(funds)
    df.to_csv('/Users/huangqingmeng/.openclaw/workspace/team_funds.csv', index=False)
    print(f"\n已保存到 team_funds.csv")
