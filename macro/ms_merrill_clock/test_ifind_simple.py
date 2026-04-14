#!/usr/bin/env python3
"""
简化测试：打印完整响应，看看iFind到底返回了什么
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

def test_code(token, name, code):
    print(f"\n{'='*60}")
    print(f"测试: {name} ({code})")
    print(f"{'='*60}")
    
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # 测试 cmd_edb
    print("\n[cmd_edb]")
    try:
        r = requests.post(f'{IFIND_BASE}/cmd_edb',
            json={'codes': code, 'startdate': start, 'enddate': end},
            headers={'Content-Type': 'application/json', 'access_token': token},
            timeout=30)
        print(f"状态码: {r.status_code}")
        print(f"响应头: {dict(r.headers)}")
        print(f"响应文本前500字符:\n{r.text[:500]}")
        if r.text:
            try:
                d = r.json()
                print(f"\nJSON解析成功:")
                print(f"  errorcode: {d.get('errorcode')}")
                print(f"  errmsg: {d.get('errmsg')}")
                print(f"  keys: {list(d.keys())}")
                if 'tables' in d:
                    print(f"  tables数量: {len(d['tables'])}")
                    if d['tables']:
                        print(f"  第一个table keys: {list(d['tables'][0].keys())}")
            except:
                print("JSON解析失败")
    except Exception as e:
        print(f"异常: {e}")

if __name__ == '__main__':
    token = get_token()
    if not token:
        print("❌ 无法获取token")
        exit(1)
    
    print("✅ Token获取成功\n")
    
    # 测试几个代码
    test_code(token, "Shibor 3M", "M0041652")  # 这个应该是R007
    test_code(token, "社融总量", "M0000545")
    test_code(token, "AAA企业债", "M0048501")
