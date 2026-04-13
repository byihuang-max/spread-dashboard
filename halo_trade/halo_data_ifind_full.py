#!/usr/bin/env python3
"""
HALO 交易数据拉取 - iFind 完整版
全部用美股+A股，替代日韩个股
"""
import requests
import pandas as pd
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PRICE_CSV = DATA_DIR / "halo_prices_ifind.csv"
PRICE_JSON = DATA_DIR / "halo_prices_ifind.json"

# iFind 配置：复用自选股跟踪器里的当前有效 token 源
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTA0LTEyIDE2OjU1OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7InJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNS0yNyAxOTowNDoxMiIsInVzZXJJZCI6Ijg1MDMwMzMwMiJ9fQ==.B196D7D08D4DD409D2DF46092AF4EECABC774987317390F4D126DE1EF493F421'

# HALO 股票池（全部用美股+A股）
HALO_STOCKS = {
    "AI能耗": {
        "🇺🇸 南方电力": "SO.N",
        "🇺🇸 NextEra能源": "NEE.N",
        "🇺🇸 杜克能源": "DUK.N",
        "🇺🇸 伊顿": "ETN.N",
        "🇨🇳 长江电力": "600900.SH",
        "🇨🇳 中国核电": "601985.SH",
    },
    "地缘重装": {
        "🇺🇸 洛克希德": "LMT.N",
        "🇺🇸 雷神": "RTX.N",
        "🇺🇸 通用动力": "GD.N",
        "🇺🇸 诺斯罗普": "NOC.N",
        "🇨🇳 中国船舶": "600150.SH",
        "🇨🇳 中航沈飞": "600760.SH",
    },
    "价值兑现": {
        "🇺🇸 埃克森美孚": "XOM.N",
        "🇺🇸 摩根大通": "JPM.N",
        "🇺🇸 高盛": "GS.N",
        "🇺🇸 摩根士丹利": "MS.N",
        "🇺🇸 美国银行": "BAC.N",
        "🇨🇳 中国石油": "601857.SH",
        "🇨🇳 招商银行": "600036.SH",
    },
}

# 基准指数
BENCHMARKS = {
    "标普500ETF": "513500.SH",
    "沪深300": "000300.SH",
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
    print("HALO 交易数据拉取（iFind 完整版）")
    print("="*60)
    
    token = get_token()
    if not token:
        print("❌ 无法获取 token")
        exit(1)
    
    print("✅ Token 获取成功")
    
    # 拉取一年数据
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    print(f"\n拉取日期: {start} ~ {end}")
    print(f"股票数量: {sum(len(v) for v in HALO_STOCKS.values())} 只")
    print()
    
    all_data = []
    
    # 拉取所有股票
    for theme, stocks in HALO_STOCKS.items():
        print(f"\n【{theme}】")
        for name, code in stocks.items():
            result = ifind_history(token, code, start, end)
            if result:
                dates = result.get('time', [])
                closes = result.get('table', {}).get('close', [])
                volumes = result.get('table', {}).get('volume', [])
                
                if dates and closes:
                    print(f"  ✅ {name:20} {len(dates):3}天")
                    for i, date in enumerate(dates):
                        all_data.append({
                            'date': date,
                            'code': code,
                            'name': name,
                            'theme': theme,
                            'close': closes[i] if i < len(closes) else None,
                            'volume': volumes[i] if i < len(volumes) else None,
                        })
                else:
                    print(f"  ⚠️  {name:20} 无数据")
            else:
                print(f"  ❌ {name:20} 拉取失败")
            
            time.sleep(0.5)  # 避免请求过快
    
    # 拉取基准指数
    print(f"\n【基准指数】")
    for name, code in BENCHMARKS.items():
        result = ifind_history(token, code, start, end)
        if result:
            dates = result.get('time', [])
            closes = result.get('table', {}).get('close', [])
            if dates and closes:
                print(f"  ✅ {name:20} {len(dates):3}天")
                for i, date in enumerate(dates):
                    all_data.append({
                        'date': date,
                        'code': code,
                        'name': name,
                        'theme': '基准',
                        'close': closes[i] if i < len(closes) else None,
                        'volume': None,
                    })
        time.sleep(0.5)
    
    # 保存数据
    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(PRICE_CSV, index=False)
        print(f"\n✅ CSV 已保存: {PRICE_CSV}")
        print(f"   总记录数: {len(df)}")
        
        # 转换为 JSON 格式（按股票分组）
        json_data = {}
        for code in df['code'].unique():
            code_df = df[df['code'] == code].sort_values('date')
            json_data[code] = {
                'name': code_df.iloc[0]['name'],
                'theme': code_df.iloc[0]['theme'],
                'dates': code_df['date'].tolist(),
                'closes': code_df['close'].tolist(),
                'volumes': code_df['volume'].tolist(),
            }
        
        with open(PRICE_JSON, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"✅ JSON 已保存: {PRICE_JSON}")
    else:
        print("\n❌ 没有数据")
    
    print("\n" + "="*60)
    print("✅ 完成！")
