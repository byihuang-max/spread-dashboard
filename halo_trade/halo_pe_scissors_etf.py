#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO PE剪刀差 - 恢复早期稳定口径
用 yfinance 直接拉 ETF trailingPE
重资产：XLU / XLE / ITA
轻资产：IGV / XLK
"""

import yfinance as yf
import json
from datetime import datetime
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_JSON = DATA_DIR / "halo_financials.json"
PE_HISTORY_CSV = DATA_DIR / "pe_scissors_history.csv"

HEAVY_ASSET_ETFS = {
    "公用事业": "XLU",
    "能源": "XLE",
    "国防": "ITA",
}

LIGHT_ASSET_ETFS = {
    "软件": "IGV",
    "科技": "XLK",
}


def fetch_pe_ratios(etf_dict):
    results = {}
    for name, ticker in etf_dict.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            pe = info.get('trailingPE')
            if pe and pe > 0:
                results[ticker] = {
                    'name': name,
                    'ticker': ticker,
                    'pe': round(float(pe), 2),
                }
                print(f"  ✅ {name}({ticker}): PE={pe:.2f}")
            else:
                print(f"  ⚠️ {name}({ticker}) PE 数据缺失")
        except Exception as e:
            print(f"  ❌ {name}({ticker}) 拉取失败: {e}")
    return results


def calculate_eps_scissors():
    print("⏳ 拉取 ETF PE 数据...")
    heavy_data = fetch_pe_ratios(HEAVY_ASSET_ETFS)
    light_data = fetch_pe_ratios(LIGHT_ASSET_ETFS)

    if not heavy_data or not light_data:
        print("⚠️ PE 数据不足，跳过剪刀差计算")
        return None

    heavy_pe = sum(d['pe'] for d in heavy_data.values()) / len(heavy_data)
    light_pe = sum(d['pe'] for d in light_data.values()) / len(light_data)
    pe_gap = heavy_pe - light_pe
    heavy_yield = (1 / heavy_pe) * 100
    light_yield = (1 / light_pe) * 100
    yield_gap = heavy_yield - light_yield

    today = datetime.now().strftime('%Y-%m-%d')
    new_row = {
        'date': today,
        'heavy_pe': round(heavy_pe, 2),
        'light_pe': round(light_pe, 2),
        'pe_gap': round(pe_gap, 2),
        'yield_gap': round(yield_gap, 2),
    }

    if PE_HISTORY_CSV.exists():
        history_df = pd.read_csv(PE_HISTORY_CSV)
        history_df = history_df[history_df['date'] != today]
        history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        history_df = pd.DataFrame([new_row])

    history_df = history_df.tail(252)
    history_df.to_csv(PE_HISTORY_CSV, index=False)

    return {
        'heavy_asset_pe': round(heavy_pe, 2),
        'light_asset_pe': round(light_pe, 2),
        'pe_gap': round(pe_gap, 2),
        'heavy_earnings_yield': round(heavy_yield, 2),
        'light_earnings_yield': round(light_yield, 2),
        'yield_gap': round(yield_gap, 2),
        'interpretation': f"重资产 PE {heavy_pe:.1f} vs 轻资产 PE {light_pe:.1f}，" + ("重资产估值更便宜" if pe_gap < 0 else "轻资产估值更便宜"),
        'heavy_details': list(heavy_data.values()),
        'light_details': list(light_data.values()),
        'history': history_df.to_dict('records'),
    }


if __name__ == '__main__':
    print('=' * 60)
    print('HALO PE剪刀差计算（ETF trailingPE）')
    print('=' * 60)

    if OUTPUT_JSON.exists():
        existing = json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))
    else:
        existing = {}

    eps_scissors = calculate_eps_scissors()
    existing['eps_scissors'] = eps_scissors
    existing['update_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    OUTPUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')

    if eps_scissors:
        print(f"✅ PE剪刀差: 重资产 {eps_scissors['heavy_asset_pe']} vs 轻资产 {eps_scissors['light_asset_pe']}")
        print(f"   {eps_scissors['interpretation']}")
        print(f"   历史点数: {len(eps_scissors['history'])}")
    print(f"✅ 结果已保存：{OUTPUT_JSON}")
