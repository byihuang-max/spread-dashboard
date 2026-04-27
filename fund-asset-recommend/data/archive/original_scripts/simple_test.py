import requests
import hashlib
import time

# 配置
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com'

def generate_sign(params, app_key):
    sorted_items = sorted([(k, v) for k, v in params.items() if k != 'sign'])
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_items]) + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

# 测试基金列表
url = f'{BASE_URL}/fof/subfund/track/list'
tm = int(time.time())
params = {
    'app_id': APP_ID,
    'page': 1,
    'pagesize': 10,
    'type': 1,
    'tm': tm
}
params['sign'] = generate_sign(params, APP_KEY)

print(f"请求URL: {url}")
print(f"参数: {params}")

try:
    response = requests.get(url, params=params, timeout=(10, 20))
    print(f"\n状态码: {response.status_code}")
    print(f"响应内容前500字符: {response.text[:500]}")
except Exception as e:
    print(f"请求失败: {e}")
