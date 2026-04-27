#!/usr/bin/env python3
"""
测试 iFind 全球股票数据接口
验证能否替代 Yahoo Finance 拉取 HALO 交易数据
"""
import requests
import json
from datetime import datetime, timedelta

# iFind 配置
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTA0LTEyIDE2OjU1OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7InJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNS0yNyAxOTowNDoxMiIsInVzZXJJZCI6Ijg1MDMwMzMwMiJ9fQ==.B196D7D08D4DD409D2DF46092AF4EECABC774987317390F4D126DE1EF493F421'

def get_token():
    """获取 access_token"""
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            print(f"✅ Token 获取成功，过期时间: {d['data'].get('expires_in', 'N/A')}秒")
            return d['data']['access_token']
        print(f"❌ Token 错误: {d.get('errmsg', '未知')}")
    except Exception as e:
        print(f"❌ Token 连接失败: {e}")
    return None

# HALO 交易需要的股票（测试几个代表性的）
TEST_STOCKS = {
    # 美股
    'CEG.O': '星座能源',
    'NEE.O': 'NextEra Energy',
    'XOM.O': '埃克森美孚',
    'JPM.O': '摩根大通',
    'SPY.O': '标普500ETF',
    
    # 日股
    '9501.T': '东京电力',
    '7011.T': '三菱重工',
    '8058.T': '三菱商事',
    
    # 韩股
    '015760.KS': '韩国电力',
    '012450.KS': '韩华能源',
    
    # A股
    '600900.SS': '长江电力',
    '601985.SS': '中国核电',
    '000300.SS': '沪深300',
}

def test_ifind_stocks(token):
    """测试 iFind 能否拉取这些股票"""
    print("\n" + "="*60)
    print("测试 iFind 全球股票数据")
    print("="*60)
    
    # 测试日期：最近5个交易日
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    success = []
    failed = []
    
    for code, name in TEST_STOCKS.items():
        try:
            r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
                json={
                    'codes': code,
                    'indicators': 'close,volume',
                    'startdate': start_date,
                    'enddate': end_date,
                },
                headers={'access-token': token},
                timeout=10
            )
            d = r.json()
            
            if d.get('errorcode') == 0 and d.get('data'):
                data = d['data'].get(code, {})
                if data.get('close'):
                    print(f"✅ {code:15} {name:15} 数据点: {len(data['close'])}")
                    success.append((code, name))
                else:
                    print(f"❌ {code:15} {name:15} 无数据")
                    failed.append((code, name, '无数据'))
            else:
                err = d.get('errmsg', '未知错误')
                print(f"❌ {code:15} {name:15} 错误: {err}")
                failed.append((code, name, err))
        except Exception as e:
            print(f"❌ {code:15} {name:15} 异常: {e}")
            failed.append((code, name, str(e)))
    
    print("\n" + "="*60)
    print(f"✅ 成功: {len(success)}/{len(TEST_STOCKS)}")
    print(f"❌ 失败: {len(failed)}/{len(TEST_STOCKS)}")
    print("="*60)
    
    if failed:
        print("\n失败列表:")
        for code, name, err in failed:
            print(f"  {code:15} {name:15} {err}")

if __name__ == '__main__':
    token = get_token()
    if token:
        test_ifind_stocks(token)
    else:
        print("❌ 无法获取 token，测试终止")
