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
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTA0LTEyIDE2OjU1OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7InJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNS0yNyAxOTowNDoxMiIsInVzZXJJZCI6Ijg1MDMwMzMwMiJ9fQ==.B196D7D08D4DD409D2DF46092AF4EECABC774987317390F4D126DE1EF493F421'

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
