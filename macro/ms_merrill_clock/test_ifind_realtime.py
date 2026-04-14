#!/usr/bin/env python3
"""
测试用 real_time_quotation 获取宏观数据
"""
import requests
import json

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

def test_realtime(token, name, code):
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"代码: {code}")
    print(f"{'='*60}")
    
    try:
        r = requests.post(f'{IFIND_BASE}/real_time_quotation',
            json={'codes': code, 'indicators': 'latest'},
            headers={'Content-Type': 'application/json', 'access_token': token},
            timeout=30)
        d = r.json()
        print(f"errorcode: {d.get('errorcode')}")
        print(f"errmsg: {d.get('errmsg')}")
        
        if d.get('errorcode') == 0:
            tables = d.get('tables', [])
            if tables:
                print(f"✅ 成功！tables数量: {len(tables)}")
                for t in tables:
                    print(f"  thscode: {t.get('thscode')}")
                    print(f"  table: {t.get('table')}")
                return True
            else:
                print("❌ tables为空")
        else:
            print(f"❌ 错误: {d.get('errmsg')}")
    except Exception as e:
        print(f"❌ 异常: {e}")
    
    return False

if __name__ == '__main__':
    token = get_token()
    if not token:
        print("❌ 无法获取token")
        exit(1)
    
    print("✅ Token获取成功\n")
    
    # 测试不同的代码格式
    tests = [
        ("汇率USDCNY（已知可用）", "USDCNY.FX"),
        ("Shibor 3M", "SHIBOR3M.IR"),
        ("DR007", "DR007.IR"),
        ("R007", "R007.IR"),
        ("10年国债", "CN10YR.IB"),
        ("AAA企业债", "CNAAACRP.IB"),
    ]
    
    for name, code in tests:
        test_realtime(token, name, code)
