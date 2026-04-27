#!/usr/bin/env python3
"""火富牛API净值抓取 - 直接HTTP调用"""
import requests, json, time, hashlib
from datetime import datetime

APPID = 'hfnogbr8zceiiygdkhw'
APPKEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com'

# 5个代表产品
PRODUCTS = [
    {'name': '超量子中证1000增强9号A类', 'code': 'XZ916A', 'benchmark': '000852', 'tab': 'quant-stock'},
    {'name': '简文致盛尊享一号', 'code': 'SAVV99', 'benchmark': '000001', 'tab': 'momentum-stock'},
    {'name': '铭跃行远均衡专享九号', 'code': 'SAJX53', 'benchmark': 'NHCI', 'tab': 'cta'},
    {'name': '赢仕安盈二号', 'code': 'SLQ349', 'benchmark': '000832', 'tab': 'convertible'},
    {'name': '量客长阳一号', 'code': 'SLL241', 'benchmark': '000001', 'tab': 'arbitrage'},
]

def sign(params):
    """生成签名"""
    sorted_params = sorted(params.items())
    sign_str = '&'.join([f"{k}={v}" for k, v in sorted_params]) + APPKEY
    return hashlib.md5(sign_str.encode()).hexdigest().upper()

def fetch_fund_nav(reg_code, start_date='2025-01-01'):
    """拉取产品净值"""
    params = {
        'appid': APPID,
        'reg_code': reg_code,
        'start_date': start_date,
        'order_by': 'price_date',
        'order': '1'
    }
    params['sign'] = sign(params)
    
    session = requests.Session()
    session.trust_env = False  # 直连不走代理
    
    try:
        resp = session.get(f'{BASE_URL}/api/fund/company_price', params=params, timeout=10)
        print(f"  状态码: {resp.status_code}")
        print(f"  原始响应: {resp.text[:200]}")
        data = resp.json()
        if data.get('code') == 200:
            return data.get('data', [])
    except Exception as e:
        print(f"  ⚠️ 拉取失败: {e}")
    return []

def fetch_index(code, start_date='2025-01-01'):
    """拉取指数行情"""
    params = {
        'appid': APPID,
        'code': code,
        'start_date': start_date,
    }
    params['sign'] = sign(params)
    
    session = requests.Session()
    session.trust_env = False
    
    try:
        resp = session.get(f'{BASE_URL}/api/index/price', params=params, timeout=10)
        data = resp.json()
        if data.get('code') == 200:
            return data.get('data', [])
    except Exception as e:
        print(f"  ⚠️ 拉取失败: {e}")
    return []

if __name__ == '__main__':
    print("测试火富牛API连接...")
    for p in PRODUCTS[:1]:  # 先测试第一个
        print(f"\n{p['name']} ({p['code']})")
        navs = fetch_fund_nav(p['code'])
        print(f"  净值条数: {len(navs)}")
        if navs:
            print(f"  最新: {navs[-1]}")
