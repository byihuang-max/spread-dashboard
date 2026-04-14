#!/usr/bin/env python3
"""
用真实的指标ID测试 iFind EDB
"""
import requests
import json
from datetime import datetime, timedelta

IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTA0LTEyIDE2OjU1OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7InJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNS0yNyAxOTowNDoxMiIsInVzZXJJZCI6Ijg1MDMwMzMwMiJ9fQ==.B196D7D08D4DD409D2DF46092AF4EECABC774987317390F4D126DE1EF493F421'

def get_token():
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
    except Exception as e:
        print(f"❌ Token 错误: {e}")
    return None

def test_edb(token, name, code):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"指标ID: {code}")
    print(f"{'='*60}")
    
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # 尝试不同的接口路径
    endpoints = [
        'cmd_edb',
        'edb',
        'get_edb',
        'economic_data',
    ]
    
    for endpoint in endpoints:
        print(f"\n[尝试接口: {endpoint}]")
        try:
            url = f'{IFIND_BASE}/{endpoint}'
            r = requests.post(url,
                json={'codes': code, 'startdate': start, 'enddate': end},
                headers={'Content-Type': 'application/json', 'access_token': token},
                timeout=30)
            
            print(f"  状态码: {r.status_code}")
            
            if r.status_code == 404:
                print(f"  ❌ 接口不存在")
                continue
            
            if r.status_code == 200:
                try:
                    d = r.json()
                    print(f"  errorcode: {d.get('errorcode')}")
                    print(f"  errmsg: {d.get('errmsg')}")
                    
                    if d.get('errorcode') == 0:
                        tables = d.get('tables', [])
                        if tables and len(tables) > 0:
                            data = tables[0]
                            dates = data.get('time', [])
                            values = data.get('table', {})
                            if dates and len(dates) > 0:
                                print(f"  ✅ 成功！数据点数: {len(dates)}")
                                print(f"  最新日期: {dates[-1]}")
                                print(f"  字段: {list(values.keys())}")
                                if values:
                                    first_key = list(values.keys())[0]
                                    print(f"  最新值: {values[first_key][-1] if values[first_key] else 'N/A'}")
                                return True
                        print(f"  ❌ 无数据")
                    else:
                        print(f"  ❌ 错误: {d.get('errmsg')}")
                except:
                    print(f"  响应文本: {r.text[:200]}")
        except Exception as e:
            print(f"  ❌ 异常: {e}")
    
    return False

if __name__ == '__main__':
    token = get_token()
    if not token:
        print("❌ 无法获取token")
        exit(1)
    
    print("✅ Token获取成功\n")
    
    # 测试真实的指标ID
    test_edb(token, "上海银行间同业拆放利率(Shibor)(日)", "M002816448")
