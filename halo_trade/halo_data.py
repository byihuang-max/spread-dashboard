#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HALO 交易数据拉取模块
- 拉取全球 HALO 标的近一年股价（美日韩中）
- 增量模式：只拉取缺失日期
- 输出 JSON + CSV
"""

import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 ====================

# 数据存储路径
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PRICE_CSV = DATA_DIR / "halo_prices.csv"
PRICE_JSON = DATA_DIR / "halo_prices.json"

# 全球 HALO 标的池（按主线分类）
HALO_UNIVERSE = {
    "AI能耗": {
        "🇺🇸 Constellation": "CEG",
        "🇺🇸 GE Vernova": "GEV",
        "🇺🇸 NextEra": "NEE",
        "🇺🇸 Eaton": "ETN",
        "🇯🇵 东京电力": "9501.T",
        "🇯🇵 关西电力": "9503.T",
        "🇰🇷 韩国电力": "015760.KS",
        "🇨🇳 长江电力": "600900.SS",
        "🇨🇳 中国核电": "601985.SS",
    },
    "地缘重装": {
        "🇺🇸 洛克希德": "LMT",
        "🇺🇸 雷神": "RTX",
        "🇯🇵 三菱重工": "7011.T",
        "🇯🇵 川崎重工": "7012.T",
        "🇰🇷 韩华航空": "012450.KS",
        "🇰🇷 现代重工": "009540.KS",
        "🇨🇳 中国船舶": "600150.SS",
        "🇨🇳 中航沈飞": "600760.SS",
    },
    "价值兑现": {
        "🇺🇸 埃克森": "XOM",
        "🇺🇸 摩根大通": "JPM",
        "🇯🇵 三菱商事": "8058.T",
        "🇯🇵 三菱UFJ": "8306.T",
        "🇰🇷 浦项制铁": "005490.KS",
        "🇰🇷 KB金融": "105560.KS",
        "🇨🇳 中国石油": "601857.SS",
        "🇨🇳 招商银行": "600036.SS",
    },
}

# 基准指数（各市场）
BENCHMARKS = {
    "🇺🇸 标普500": "SPY",
    "🇯🇵 日经225": "^N225",
    "🇰🇷 KOSPI": "^KS11",
    "🇨🇳 沪深300": "000300.SS",
}

# 合并所有标的（含基准）
ALL_TICKERS = {}
for theme, stocks in HALO_UNIVERSE.items():
    ALL_TICKERS.update(stocks)
ALL_TICKERS.update(BENCHMARKS)


# ==================== 增量拉取逻辑 ====================

def load_existing_data():
    """加载已有数据，返回 DataFrame"""
    if PRICE_CSV.exists():
        df = pd.read_csv(PRICE_CSV, parse_dates=["date"])
        print(f"✅ 加载已有数据：{len(df)} 行，最新日期 {df['date'].max().date()}")
        return df
    else:
        print("📂 无历史数据，将全量拉取")
        return pd.DataFrame()


def get_date_range(existing_df):
    """
    确定需要拉取的日期范围
    - 如果有历史数据：从最新日期+1天 到 今天
    - 如果无历史数据：从一年前 到 今天
    """
    end_date = datetime.now()
    if not existing_df.empty:
        last_date = existing_df["date"].max()
        start_date = last_date + timedelta(days=1)
        if start_date >= end_date:
            print("✅ 数据已是最新，无需拉取")
            return None, None
    else:
        start_date = end_date - timedelta(days=365)
    
    return start_date, end_date


def fetch_prices(tickers, start_date, end_date):
    """
    批量拉取股价（yfinance）
    返回 DataFrame: date | ticker | close | name | theme
    """
    print(f"⏳ 拉取 {len(tickers)} 只标的，{start_date.date()} ~ {end_date.date()}")
    
    # 反向映射：ticker → name
    ticker_to_name = {v: k for k, v in ALL_TICKERS.items()}
    
    # 反向映射：ticker → theme
    ticker_to_theme = {}
    for theme, stocks in HALO_UNIVERSE.items():
        for name, ticker in stocks.items():
            ticker_to_theme[ticker] = theme
    for name, ticker in BENCHMARKS.items():
        ticker_to_theme[ticker] = "基准指数"
    
    all_data = []
    for ticker in tickers:
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if data.empty:
                print(f"  ⚠️  {ticker} 无数据")
                continue
            
            df = data[["Close"]].reset_index()
            df.columns = ["date", "close"]
            df["ticker"] = ticker
            df["name"] = ticker_to_name.get(ticker, ticker)
            df["theme"] = ticker_to_theme.get(ticker, "未分类")
            all_data.append(df)
            print(f"  ✅ {ticker_to_name.get(ticker, ticker)}: {len(df)} 天")
        except Exception as e:
            print(f"  ❌ {ticker} 拉取失败: {e}")
    
    if not all_data:
        return pd.DataFrame()
    
    result = pd.concat(all_data, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"]).dt.date
    return result


# ==================== 保存数据 ====================

def save_data(df):
    """保存为 CSV + JSON"""
    # CSV（完整历史）
    df.to_csv(PRICE_CSV, index=False)
    print(f"✅ CSV 已保存：{PRICE_CSV}（{len(df)} 行）")
    
    # JSON（最新快照 + 元数据）
    latest_date = df["date"].max()
    latest_df = df[df["date"] == latest_date].copy()
    
    # 手动构建 records，确保 date 是字符串
    latest_data = []
    for _, row in latest_df.iterrows():
        latest_data.append({
            "date": str(row["date"]),
            "close": float(row["close"]),
            "ticker": row["ticker"],
            "name": row["name"],
            "theme": row["theme"],
        })
    
    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_date": str(latest_date),
        "total_days": int(len(df["date"].unique())),
        "total_tickers": int(len(df["ticker"].unique())),
        "latest_prices": latest_data,
    }
    
    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 已保存：{PRICE_JSON}")


# ==================== 主流程 ====================

def main():
    print("=" * 60)
    print("HALO 交易数据拉取（增量模式）")
    print("=" * 60)
    
    # 1. 加载已有数据
    existing_df = load_existing_data()
    
    # 2. 确定拉取范围
    start_date, end_date = get_date_range(existing_df)
    if start_date is None:
        return
    
    # 3. 拉取新数据
    new_df = fetch_prices(list(ALL_TICKERS.values()), start_date, end_date)
    if new_df.empty:
        print("⚠️  未拉取到新数据")
        return
    
    # 4. 合并数据
    if not existing_df.empty:
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=["date", "ticker"], keep="last")
        combined_df = combined_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    else:
        combined_df = new_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    
    # 5. 保存
    save_data(combined_df)
    
    print("=" * 60)
    print(f"✅ 完成！共 {len(combined_df)} 行数据")
    print("=" * 60)


if __name__ == "__main__":
    main()
