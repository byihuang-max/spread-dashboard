#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO PE剪刀差 - 用 AkShare/百度美股估值数据拉取个股 PE(TTM)
重资产（公用事业+能源+国防）vs 轻资产（金融）
"""

import json
import ssl
import http.client
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_JSON = DATA_DIR / "halo_financials.json"
PE_HISTORY_CSV = DATA_DIR / "pe_scissors_history.csv"

# 重资产组（能源+国防+公用事业）
HEAVY_ASSETS = {
    'SO': '南方电力',
    'NEE': 'NextEra',
    'DUK': '杜克能源',
    'XOM': '埃克森美孚',
    'LMT': '洛克希德',
    'RTX': '雷神',
    'GD': '通用动力',
    'NOC': '诺斯罗普',
}

# 轻资产组（金融）
LIGHT_ASSETS = {
    'JPM': '摩根大通',
    'GS': '高盛',
    'MS': '摩根士丹利',
    'BAC': '美国银行',
}


def fetch_baidu_us_valuation(symbol: str, indicator: str = '市盈率(TTM)', period: str = '近一年') -> pd.DataFrame:
    """直接调用百度 finance 新地址，绕过旧 gushitong 地址失效问题。"""
    params = {
        'openapi': '1',
        'dspName': 'iphone',
        'tn': 'tangram',
        'client': 'app',
        'query': indicator,
        'code': symbol,
        'word': '',
        'resource_id': '51171',
        'market': 'us',
        'tag': indicator,
        'chart_select': period,
        'industry_select': '',
        'skip_industry': '1',
        'finClientType': 'pc',
    }
    ctx = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection('finance.baidu.com', context=ctx, timeout=20)
    conn.request(
        'GET',
        f"/opendata?{urllib.parse.urlencode(params)}",
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json,text/plain,*/*',
        },
    )
    resp = conn.getresponse()
    body = resp.read()
    if resp.status != 200:
        raise RuntimeError(f'HTTP {resp.status}')
    payload = json.loads(body)
    chart = payload['Result'][0]['DisplayData']['resultData']['tplData']['result']['chartInfo'][0]['body']
    df = pd.DataFrame(chart)
    df.columns = ['date', 'value']
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.dropna().copy()
    df = df[df['value'] > 0].copy()
    return df


def collect_group_pe(group_dict: dict[str, str]) -> dict[str, pd.DataFrame]:
    results = {}
    for symbol, name in group_dict.items():
        try:
            df = fetch_baidu_us_valuation(symbol)
            if df.empty:
                print(f"  ⚠️  {name}({symbol}) 无 PE 数据")
                continue
            results[symbol] = df
            print(f"  ✅ {name}({symbol}): {len(df)} 条")
        except Exception as e:
            print(f"  ❌ {name}({symbol}) 拉取失败: {e}")
    return results


def average_group_pe(pe_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for symbol, df in pe_map.items():
        temp = df.rename(columns={'value': symbol}).copy()
        frames.append(temp)
    if not frames:
        return pd.DataFrame(columns=['date', 'avg_pe'])
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on='date', how='outer')
    value_cols = [c for c in merged.columns if c != 'date']
    merged['avg_pe'] = merged[value_cols].mean(axis=1, skipna=True)
    merged = merged[['date', 'avg_pe']].sort_values('date').reset_index(drop=True)
    return merged


def calc_scissors(heavy_df: pd.DataFrame, light_df: pd.DataFrame) -> dict:
    merged = heavy_df.merge(light_df, on='date', how='inner', suffixes=('_heavy', '_light'))
    merged['pe_gap'] = merged['avg_pe_heavy'] - merged['avg_pe_light']
    merged = merged.dropna().sort_values('date').reset_index(drop=True)

    history = []
    for _, row in merged.tail(252).iterrows():
        history.append({
            'date': row['date'],
            'heavy_pe': round(float(row['avg_pe_heavy']), 2),
            'light_pe': round(float(row['avg_pe_light']), 2),
            'pe_gap': round(float(row['pe_gap']), 2),
        })

    latest = history[-1] if history else None
    return {
        'latest': latest,
        'history': history,
        'interpretation': (
            f"重资产 PE {latest['heavy_pe']:.1f} vs 轻资产 PE {latest['light_pe']:.1f}，"
            + ('重资产估值更便宜' if latest and latest['pe_gap'] < 0 else '轻资产估值更便宜')
        ) if latest else None,
    }


def save_csv(history: list[dict]) -> None:
    if not history:
        return
    pd.DataFrame(history).to_csv(PE_HISTORY_CSV, index=False, encoding='utf-8-sig')


def main():
    print('=' * 60)
    print('HALO PE剪刀差计算（AkShare/百度美股估值）')
    print('=' * 60)

    print('⏳ 拉取重资产组 PE...')
    heavy_data = collect_group_pe(HEAVY_ASSETS)

    print('⏳ 拉取轻资产组 PE...')
    light_data = collect_group_pe(LIGHT_ASSETS)

    heavy_avg = average_group_pe(heavy_data)
    light_avg = average_group_pe(light_data)
    scissors = calc_scissors(heavy_avg, light_avg)

    if OUTPUT_JSON.exists():
        existing = json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))
    else:
        existing = {}

    # 空结果保护：如果本次没拉到有效 PE 剪刀差，保留旧文件不覆盖
    if not scissors.get('latest'):
        print('⚠️ PE 剪刀差数据为空，保留旧文件不覆盖')
        return

    existing['eps_scissors'] = scissors
    existing['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    OUTPUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
    save_csv(scissors.get('history', []))

    print('=' * 60)
    if scissors.get('latest'):
        latest = scissors['latest']
        print('✅ PE剪刀差恢复成功:')
        print(f"   日期: {latest['date']}")
        print(f"   重资产PE: {latest['heavy_pe']}")
        print(f"   轻资产PE: {latest['light_pe']}")
        print(f"   差距: {latest['pe_gap']}")
        print(f"   历史点数: {len(scissors['history'])}")
    else:
        print('⚠️ 未生成有效 PE 剪刀差')
    print(f'✅ 结果已保存：{OUTPUT_JSON}')
    print('=' * 60)


if __name__ == '__main__':
    main()
