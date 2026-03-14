#!/usr/bin/env python3
"""
反脆弱交易看板 - iFind 数据源
"""
import requests
import json
import os
import time
from datetime import datetime, timedelta

# iFind 配置
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAzLTA4IDE5OjE0OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7ImFjY291bnQiOiJnbG1zc2YwMDEiLCJhdXRoVXNlckluZm8iOnsiY3NpIjp0cnVlLCJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbIjExIiwiMjIiLCIyNSIsIjI2IiwiMTYiLCIxOCIsIjE5IiwiMSIsIjIiLCIzIiwiNCIsIjUiLCI2IiwiNyIsIjgiLCI5IiwiMjAiLCIxMCIsIjIxIl0sImhhc0FJUHJlZGljdCI6ZmFsc2UsImhhc0FJVGFsayI6ZmFsc2UsImhhc0NJQ0MiOmZhbHNlLCJoYXNDU0kiOnRydWUsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1hcmtldENvZGUiOiIxNjszMjsxNDQ7MTc2OzExMjs4ODs0ODsxMjg7MTY4LTE7MTg0OzIwMDsyMTY7MTA0OzEyMDsxMzY7MjMyOzU2Ozk2OzE2MDs2NDsiLCJtYXhPbkxpbmUiOjEsIm5vRGlzayI6ZmFsc2UsInByb2R1Y3RUeXBlIjoiU1VQRVJDT01NQU5EUFJPRFVDVCIsInJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNC0wNyAxOTowNDoxMiIsInNlc3NzaW9uIjoiYjk1N2Y1ZGU5OGNmOGMwNzhiZjk2Yzk4ZDRhOTllMDQiLCJzaWRJbmZvIjp7NjQ6IjExMTExMTExMTExMTExMTExMTExMTExMSIsMToiMTAxIiwyOiIxIiw2NzoiMTAxMTExMTExMTExMTExMTExMTExMTExIiwzOiIxIiw2OToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsNToiMSIsNjoiMSIsNzE6IjExMTExMTExMTExMTExMTExMTExMTEwMCIsNzoiMTExMTExMTExMTEiLDg6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMDAxIiwxMzg6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDEzOToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQwOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDE6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MjoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQzOiIxMSIsODA6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODE6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODI6IjExMTExMTExMTExMTExMTExMTExMDExMCIsODM6IjExMTExMTExMTExMTExMTExMTAwMDAwMCIsODU6IjAxMTExMTExMTExMTExMTExMTExMTExMSIsODc6IjExMTExMTExMDAxMTExMTAxMTExMTExMSIsODk6IjExMTExMTExMDExMDExMTExMTEwMTExMSIsOTA6IjExMTExMDExMTExMTExMTExMTExMTExMTEwIiw5MzoiMTExMTExMTExMTExMTExMTEwMDAwMTExMSIsOTQ6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk2OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw5OToiMTAwIiwxMDA6IjExMTEwMTExMTExMTExMTExMTAiLDEwMjoiMSIsNDQ6IjExIiwxMDk6IjEiLDUzOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDU0OiIxMTAwMDAwMDAwMTEwMDAwMDEwMTAwMDAwMTAwMTAwMDAwMCIsNTc6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMTAwMDAwMDAwIiw2MjoiMTExMTExMTExMTExMTExMTExMTExMTExIiw2MzoiMTExMTExMTExMTExMTExMTExMTExMTExIn0sInRpbWVzdGFtcCI6IjE3NzI5Njg0NDM1MzUiLCJ0cmFuc0F1dGgiOmZhbHNlLCJ0dGxWYWx1ZSI6MCwidWlkIjoiODUwMzAzMzAyIiwidXNlclR5cGUiOiJPRkZJQ0lBTCIsIndpZmluZExpbWl0TWFwIjp7fX19.A21F30AC0984CEB66A0A09F2D733E3705CAD6C1C0D51225C0761C1BF945A2BFF'

_DIR = os.path.dirname(os.path.abspath(__file__))

# iFind 资产映射
IFIND_ASSETS = {
    '纳斯达克100': 'NDX.GI',
    '日经225': 'N225.GI',
    '韩国KOSPI': 'KS11.GI',
    '科创50ETF': '588000.SH',
    '恒生科技ETF': '03033.HK',
    '纳斯达克ETF': 'QQQ.O',
}

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

def ifind_history(token, code, start, end):
    try:
        r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
            json={
                'codes': code,
                'indicators': 'close,volume',
                'startdate': start,
                'enddate': end,
            },
            headers={'Content-Type': 'application/json', 'access_token': token},
            timeout=30)
        d = r.json()
        if d.get('errorcode') == 0:
            tables = d.get('tables', [])
            if tables:
                return tables[0]
    except Exception as e:
        print(f"  ❌ {code} 失败: {e}")
    return None

if __name__ == '__main__':
    print("反脆弱数据拉取（iFind）")
    
    token = get_token()
    if not token:
        print("❌ Token 获取失败")
        exit(1)
    
    print("✅ Token 获取成功")
    
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    print(f"\n拉取日期: {start} ~ {end}\n")
    
    for name, code in IFIND_ASSETS.items():
        result = ifind_history(token, code, start, end)
        if result:
            dates = result.get('time', [])
            closes = result.get('table', {}).get('close', [])
            if dates and closes:
                print(f"✅ {name:15} {len(dates):2}天, 最新: {closes[-1]:.2f}")
            else:
                print(f"⚠️  {name:15} 返回但无数据")
        else:
            print(f"❌ {name:15} 拉取失败")
        
        time.sleep(0.5)
    
    print("\n✅ 测试完成")
