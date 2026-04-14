#!/usr/bin/env python3
"""
HALO 交易数据拉取 - iFind 版本
替代 Yahoo Finance，避免限流问题
"""
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PRICE_CSV_IFIND = DATA_DIR / "halo_prices_ifind.csv"

# iFind 配置
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTA0LTEyIDE2OjU1OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7InJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNS0yNyAxOTowNDoxMiIsInVzZXJJZCI6Ijg1MDMwMzMwMiJ9fQ==.B196D7D08D4DD409D2DF46092AF4EECABC774987317390F4D126DE1EF493F421'

# Yahoo Finance → iFind 代码映射
CODE_MAP = {
    # 美股：去掉后缀，加 .O
    "CEG": "CEG.O", "GEV": "GEV.O", "NEE": "NEE.O", "ETN": "ETN.O",
    "LMT": "LMT.O", "RTX": "RTX.O", "XOM": "XOM.O", "JPM": "JPM.O",
    "SPY": "SPY.O", "QQQ": "QQQ.O",
    # 日股：保持 .T
    "9501.T": "9501.T", "9503.T": "9503.T", "7011.T": "7011.T", 
    "7012.T": "7012.T", "8058.T": "8058.T", "8306.T": "8306.T",
    # 韩股：保持 .KS
    "015760.KS": "015760.KS", "012450.KS": "012450.KS", 
    "009540.KS": "009540.KS", "005490.KS": "005490.KS", "105560.KS": "105560.KS",
    # A股：.SS → .SH, .SZ 保持
    "600900.SS": "600900.SH", "601985.SS": "601985.SH",
    "600150.SS": "600150.SH", "600760.SS": "600760.SH",
    "601857.SS": "601857.SH", "600036.SS": "600036.SH",
    "000300.SS": "000300.SH",
    # 指数
    "^N225": "N225.GI", "^KS11": "KS11.GI",
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
    """拉取历史数据"""
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
    print("="*60)
    print("HALO 交易数据拉取（iFind 版本）")
    print("="*60)
    
    token = get_token()
    if not token:
        print("❌ 无法获取 token")
        exit(1)
    
    print("✅ Token 获取成功")
    
    # 测试拉取最近一周数据
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    print(f"\n拉取日期: {start} ~ {end}")
    print(f"测试股票: 5只")
    
    test_codes = ['QQQ.O', '600900.SH', '9501.T', '015760.KS', 'XOM.O']
    
    for code in test_codes:
        result = ifind_history(token, code, start, end)
        if result:
            dates = result.get('time', [])
            closes = result.get('table', {}).get('close', [])
            print(f"✅ {code:15} {len(dates)} 天")
        else:
            print(f"❌ {code:15} 无数据")
    
    print("\n" + "="*60)
    print("测试完成！如果成功，可以继续完整拉取")
