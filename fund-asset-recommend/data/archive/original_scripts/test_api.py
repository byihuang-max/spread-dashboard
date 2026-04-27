#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import time
import requests

# 配置信息
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"
API_PATH = "/fof/subfund/track/list"

def generate_sign(params, app_key):
    """生成签名：参数key升序排序，拼接key=value，最后拼接密钥，计算md5"""
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = "&".join([f"{k}={v}" for k, v in sorted_params]) + app_key
    print(f"签名字符串: {sign_str}")
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    print(f"签名结果: {sign}")
    return sign

def test_api():
    tm = int(time.time())
    params = {
        "app_id": APP_ID,
        "page": 1,
        "pagesize": 10,
        "tm": tm,
        "type": 1
    }
    sign = generate_sign(params, APP_KEY)
    params["sign"] = sign
    
    url = BASE_URL + API_PATH
    print(f"\n请求URL: {url}")
    print(f"请求参数: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=10, verify=False)
        print(f"\n状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
    except Exception as e:
        print(f"\n请求异常: {e}")

if __name__ == "__main__":
    test_api()
