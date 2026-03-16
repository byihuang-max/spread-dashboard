#!/usr/bin/env python3
"""
根据iFind API手册测试EDB接口
手册显示EDB在第7节，URL应该是类似 /api/v1/edb_xxx 的格式
"""
import requests
import json
from datetime import datetime, timedelta

IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAzLTA4IDE5OjE0OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7ImFjY291bnQiOiJnbG1zc2YwMDEiLCJhdXRoVXNlckluZm8iOnsiY3NpIjp0cnVlLCJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbIjExIiwiMjIiLCIyNSIsIjI2IiwiMTYiLCIxOCIsIjE5IiwiMSIsIjIiLCIzIiwiNCIsIjUiLCI2IiwiNyIsIjgiLCI5IiwiMjAiLCIxMCIsIjIxIl0sImhhc0FJUHJlZGljdCI6ZmFsc2UsImhhc0FJVGFsayI6ZmFsc2UsImhhc0NJQ0MiOmZhbHNlLCJoYXNDU0kiOnRydWUsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1hcmtldENvZGUiOiIxNjszMjsxNDQ7MTc2OzExMjs4ODs0ODsxMjg7MTY4LTE7MTg0OzIwMDsyMTY7MTA0OzEyMDsxMzY7MjMyOzU2Ozk2OzE2MDs2NDsiLCJtYXhPbkxpbmUiOjEsIm5vRGlzayI6ZmFsc2UsInByb2R1Y3RUeXBlIjoiU1VQRVJDT01NQU5EUFJPRFVDVCIsInJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNC0wNyAxOTowNDoxMiIsInNlc3NzaW9uIjoiYjk1N2Y1ZGU5OGNmOGMwNzhiZjk2Yzk4ZDRhOTllMDQiLCJzaWRJbmZvIjp7NjQ6IjExMTExMTExMTExMTExMTExMTExMTExMSIsMToiMTAxIiwyOiIxIiw2NzoiMTAxMTExMTExMTExMTExMTExMTExMTExIiwzOiIxIiw2OToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsNToiMSIsNjoiMSIsNzE6IjExMTExMTExMTExMTExMTExMTExMTEwMCIsNzoiMTExMTExMTExMTEiLDg6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMDAxIiwxMzg6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDEzOToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQwOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDE6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MjoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQzOiIxMSIsODA6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODE6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODI6IjExMTExMTExMTExMTExMTExMTExMDExMCIsODM6IjExMTExMTExMTExMTExMTExMTAwMDAwMCIsODU6IjAxMTExMTExMTExMTExMTExMTExMTExMSIsODc6IjExMTExMTExMDAxMTExMTAxMTExMTExMSIsODk6IjExMTExMTExMDExMDExMTExMTEwMTExMSIsOTA6IjExMTExMDExMTExMTExMTExMTExMTExMTEwIiw5MzoiMTExMTExMTExMTExMTExMTEwMDAwMTExMSIsOTQ6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk2OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw5OToiMTAwIiwxMDA6IjExMTEwMTExMTExMTExMTExMTAiLDEwMjoiMSIsNDQ6IjExIiwxMDk6IjEiLDUzOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDU0OiIxMTAwMDAwMDAwMTEwMDAwMDEwMTAwMDAwMTAwMTAwMDAwMCIsNTc6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMTAwMDAwMDAwIiw2MjoiMTExMTExMTExMTExMTExMTExMTExMTExIiw2MzoiMTExMTExMTExMTExMTExMTExMTExMTExIn0sInRpbWVzdGFtcCI6IjE3NzI5Njg0NDM1MzUiLCJ0cmFuc0F1dGgiOmZhbHNlLCJ0dGxWYWx1ZSI6MCwidWlkIjoiODUwMzAzMzAyIiwidXNlclR5cGUiOiJPRkZJQ0lBTCIsIndpZmluZExpbWl0TWFwIjp7fX19.A21F30AC0984CEB66A0A09F2D733E3705CAD6C1C0D51225C0761C1BF945A2BFF'

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

def test_edb_formats(token, code):
    """测试不同的EDB接口格式"""
    print(f"\n{'='*60}")
    print(f"测试指标ID: {code}")
    print(f"{'='*60}")
    
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    # 根据手册，尝试不同的参数格式
    test_cases = [
        {
            'name': '格式1: 类似date_sequence',
            'url': f'{IFIND_BASE}/edb_sequence',
            'body': {
                'codes': code,
                'startdate': start,
                'enddate': end
            }
        },
        {
            'name': '格式2: 类似basic_data',
            'url': f'{IFIND_BASE}/edb_data',
            'body': {
                'codes': code,
                'indipara': [{'indicator': code}]
            }
        },
        {
            'name': '格式3: 简单codes',
            'url': f'{IFIND_BASE}/economic_data',
            'body': {
                'codes': code,
                'start_date': start,
                'end_date': end
            }
        },
        {
            'name': '格式4: 直接用指标ID',
            'url': f'{IFIND_BASE}/edb',
            'body': {
                'indicator_id': code,
                'startdate': start,
                'enddate': end
            }
        }
    ]
    
    for test in test_cases:
        print(f"\n[{test['name']}]")
        print(f"  URL: {test['url']}")
        print(f"  Body: {test['body']}")
        
        try:
            r = requests.post(
                test['url'],
                json=test['body'],
                headers={'Content-Type': 'application/json', 'access_token': token},
                timeout=30
            )
            
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
                        if tables:
                            print(f"  ✅ 成功！返回数据")
                            print(f"  tables: {len(tables)}")
                            if tables[0].get('time'):
                                print(f"  数据点数: {len(tables[0]['time'])}")
                            return True
                    else:
                        print(f"  ❌ 错误: {d.get('errmsg')}")
                except Exception as e:
                    print(f"  响应解析失败: {e}")
                    print(f"  响应文本: {r.text[:200]}")
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")
    
    return False

if __name__ == '__main__':
    token = get_token()
    if not token:
        print("❌ 无法获取token")
        exit(1)
    
    print("✅ Token获取成功\n")
    
    # 测试Roni提供的真实指标ID
    test_edb_formats(token, "M002816448")
