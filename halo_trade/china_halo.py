#!/usr/bin/env python3
"""
中国版 HALO：境内重资产 vs 轻资产趋势判断
阶段一：基础版本 + 罗素3000拟合
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests

try:
    import yfinance as yf
except ImportError:
    print("⚠️ yfinance 未安装，跳过美国市场对比")
    yf = None

# Tushare 配置
TUSHARE_TOKEN = "8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae"
TUSHARE_API = "https://api.tushare.pro"

def tushare_query(api_name, fields, **params):
    """Tushare API 查询"""
    data = {
        "api_name": api_name,
        "token": TUSHARE_TOKEN,
        "params": params,
        "fields": fields
    }
    try:
        resp = requests.post(TUSHARE_API, json=data, timeout=30, proxies={'http': None, 'https': None})
        result = resp.json()
        if result['code'] != 0:
            print(f"❌ Tushare API 错误: {result.get('msg', 'Unknown')}")
            return pd.DataFrame()
        
        df = pd.DataFrame(result['data']['items'], columns=result['data']['fields'])
        return df
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return pd.DataFrame()

def fetch_sw_industry_data(days=252):
    """拉取申万一级行业指数数据（近一年）"""
    print("📊 拉取申万一级行业数据...")
    
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    
    # 重资产行业
    heavy_industries = {
        '801050.SI': '有色金属',
        '801040.SI': '钢铁', 
        '801950.SI': '煤炭',
        '801160.SI': '公用事业',  # 电力+燃气+水务
        '801020.SI': '石油石化',
        '801720.SI': '建筑装饰'
    }
    
    # 轻资产行业
    light_industries = {
        '801750.SI': '计算机',
        '801760.SI': '传媒',
        '801080.SI': '电子',
        '801150.SI': '医药生物'
    }
    
    all_codes = list(heavy_industries.keys()) + list(light_industries.keys())
    
    df_list = []
    for code in all_codes:
        print(f"  拉取 {code}...")
        df = tushare_query(
            'sw_daily',
            '',  # 不指定字段，返回全部
            ts_code=code,
            start_date=start_date,
            end_date=end_date
        )
        if not df.empty:
            # 第一次打印字段名，调试用
            if len(df_list) == 0:
                print(f"    字段: {df.columns.tolist()}")
            df_list.append(df)
        else:
            print(f"    ⚠️ {code} 无数据")
    
    if not df_list:
        print("❌ 未获取到数据")
        return pd.DataFrame(), heavy_industries, light_industries
    
    all_data = pd.concat(df_list, ignore_index=True)
    all_data['trade_date'] = pd.to_datetime(all_data['trade_date'])
    all_data['close'] = pd.to_numeric(all_data['close'], errors='coerce')
    all_data['pct_change'] = pd.to_numeric(all_data['pct_change'], errors='coerce')
    
    print(f"✅ 获取 {len(all_data)} 条数据")
    return all_data, heavy_industries, light_industries

def fetch_us_sector_data(days=252):
    """拉取美国行业ETF数据（罗素3000拟合）"""
    if yf is None:
        return pd.DataFrame(), {}, {}
    
    print("🇺🇸 拉取美国行业ETF数据（罗素3000拟合）...")
    
    # 重资产行业ETF
    heavy_etfs = {
        'XLE': '能源',
        'XLU': '公用事业',
        'XLI': '工业',
        'XLB': '材料'
    }
    
    # 轻资产行业ETF
    light_etfs = {
        'XLK': '科技',
        'XLV': '医疗',
        'XLC': '通信服务',
        'XLY': '可选消费'
    }
    
    all_tickers = list(heavy_etfs.keys()) + list(light_etfs.keys())
    
    try:
        # 拉取数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        data = yf.download(all_tickers, start=start_date, end=end_date, progress=False)
        
        if data.empty:
            print("❌ 未获取到美国数据")
            return pd.DataFrame(), heavy_etfs, light_etfs
        
        # 提取收盘价
        if len(all_tickers) > 1:
            prices = data['Close']
        else:
            prices = data[['Close']]
        
        # 计算日收益率
        returns = prices.pct_change() * 100
        returns = returns.dropna()
        
        # 转换为长格式
        df_list = []
        for ticker in all_tickers:
            if ticker in returns.columns:
                temp = pd.DataFrame({
                    'ticker': ticker,
                    'trade_date': returns.index,
                    'pct_change': returns[ticker].values
                })
                df_list.append(temp)
        
        if not df_list:
            print("❌ 数据处理失败")
            return pd.DataFrame(), heavy_etfs, light_etfs
        
        all_data = pd.concat(df_list, ignore_index=True)
        print(f"✅ 获取 {len(all_data)} 条数据")
        return all_data, heavy_etfs, light_etfs
        
    except Exception as e:
        print(f"❌ 拉取失败: {e}")
        return pd.DataFrame(), heavy_etfs, light_etfs

def calculate_us_asset_style_index(df, heavy_dict, light_dict):
    """计算美国重资产/轻资产组合指数（等权）"""
    if df.empty:
        return pd.DataFrame()
    
    print("🧮 计算美国重资产/轻资产指数...")
    
    # 透视表：日期 × ticker
    pivot = df.pivot(index='trade_date', columns='ticker', values='pct_change')
    pivot = pivot.sort_index()
    
    # 重资产等权日收益率
    heavy_cols = [c for c in pivot.columns if c in heavy_dict]
    heavy_ret = pivot[heavy_cols].mean(axis=1)
    
    # 轻资产等权日收益率
    light_cols = [c for c in pivot.columns if c in light_dict]
    light_ret = pivot[light_cols].mean(axis=1)
    
    # 归一化净值（起点=100）
    heavy_nav = (1 + heavy_ret / 100).cumprod() * 100
    light_nav = (1 + light_ret / 100).cumprod() * 100
    
    # 相对强弱（重资产 / 轻资产）
    relative_strength = heavy_nav / light_nav * 100
    
    result = pd.DataFrame({
        'trade_date': pivot.index,
        'heavy_nav': heavy_nav.values,
        'light_nav': light_nav.values,
        'relative_strength': relative_strength.values
    })
    
    print(f"✅ 计算完成，{len(result)} 个交易日")
    return result

def calculate_asset_style_index(df, heavy_dict, light_dict):
    """计算重资产/轻资产组合指数（等权）"""
    print("🧮 计算重资产/轻资产指数...")
    
    # 透视表：日期 × 行业代码
    pivot = df.pivot(index='trade_date', columns='ts_code', values='pct_change')
    pivot = pivot.sort_index()
    
    # 重资产等权日收益率
    heavy_cols = [c for c in pivot.columns if c in heavy_dict]
    heavy_ret = pivot[heavy_cols].mean(axis=1)
    
    # 轻资产等权日收益率
    light_cols = [c for c in pivot.columns if c in light_dict]
    light_ret = pivot[light_cols].mean(axis=1)
    
    # 归一化净值（起点=100）
    heavy_nav = (1 + heavy_ret / 100).cumprod() * 100
    light_nav = (1 + light_ret / 100).cumprod() * 100
    
    # 相对强弱（重资产 / 轻资产）
    relative_strength = heavy_nav / light_nav * 100
    
    result = pd.DataFrame({
        'trade_date': pivot.index,
        'heavy_nav': heavy_nav.values,
        'light_nav': light_nav.values,
        'relative_strength': relative_strength.values,
        'heavy_ret': heavy_ret.values,
        'light_ret': light_ret.values
    })
    
    print(f"✅ 计算完成，{len(result)} 个交易日")
    return result

def generate_signal(result):
    """生成趋势判断信号"""
    print("🎯 生成趋势信号...")
    
    latest = result.iloc[-1]
    
    # MA20/MA60 趋势
    result['rs_ma20'] = result['relative_strength'].rolling(20).mean()
    result['rs_ma60'] = result['relative_strength'].rolling(60).mean()
    
    latest_rs = latest['relative_strength']
    ma20 = result['rs_ma20'].iloc[-1]
    ma60 = result['rs_ma60'].iloc[-1]
    
    # 20日动量
    momentum_20d = (latest_rs / result['relative_strength'].iloc[-21] - 1) * 100 if len(result) > 21 else 0
    
    # 60日动量
    momentum_60d = (latest_rs / result['relative_strength'].iloc[-61] - 1) * 100 if len(result) > 61 else 0
    
    # 趋势判断
    if latest_rs > ma20 and ma20 > ma60 and momentum_20d > 0:
        trend = "🔴 重资产占优"
        signal = "加配重资产（能源/有色/公用事业）"
    elif latest_rs < ma20 and ma20 < ma60 and momentum_20d < 0:
        trend = "🟢 轻资产占优"
        signal = "加配轻资产（科技/医药/消费）"
    else:
        trend = "🟡 震荡切换"
        signal = "均衡配置，观察趋势确认"
    
    signal_data = {
        'trend': trend,
        'signal': signal,
        'latest_rs': round(latest_rs, 2),
        'ma20': round(ma20, 2),
        'ma60': round(ma60, 2),
        'momentum_20d': round(momentum_20d, 2),
        'momentum_60d': round(momentum_60d, 2),
        'heavy_nav': round(latest['heavy_nav'], 2),
        'light_nav': round(latest['light_nav'], 2),
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    print(f"✅ {trend}")
    return signal_data, result

def main():
    print("=" * 60)
    print("🇨🇳 中国版 HALO - 重资产 vs 轻资产趋势判断")
    print("=" * 60)
    
    # 1. 拉取中国数据
    df_cn, heavy_dict_cn, light_dict_cn = fetch_sw_industry_data(days=252)
    if df_cn.empty:
        print("❌ 中国数据拉取失败")
        return
    
    # 2. 计算中国指数
    result_cn = calculate_asset_style_index(df_cn, heavy_dict_cn, light_dict_cn)
    
    # 3. 生成中国信号
    signal_data_cn, result_cn_with_ma = generate_signal(result_cn)
    
    # 4. 拉取美国数据（罗素3000拟合）
    df_us, heavy_dict_us, light_dict_us = fetch_us_sector_data(days=252)
    
    # 5. 计算美国指数
    result_us = calculate_us_asset_style_index(df_us, heavy_dict_us, light_dict_us) if not df_us.empty else pd.DataFrame()
    
    # 6. 美国信号
    signal_data_us = {}
    if not result_us.empty:
        result_us['rs_ma20'] = result_us['relative_strength'].rolling(20).mean()
        result_us['rs_ma60'] = result_us['relative_strength'].rolling(60).mean()
        latest_us = result_us.iloc[-1]
        
        momentum_20d_us = (latest_us['relative_strength'] / result_us['relative_strength'].iloc[-21] - 1) * 100 if len(result_us) > 21 else 0
        
        if latest_us['relative_strength'] > latest_us['rs_ma20'] and latest_us['rs_ma20'] > latest_us['rs_ma60']:
            trend_us = "🔴 重资产占优"
        elif latest_us['relative_strength'] < latest_us['rs_ma20'] and latest_us['rs_ma20'] < latest_us['rs_ma60']:
            trend_us = "🟢 轻资产占优"
        else:
            trend_us = "🟡 震荡切换"
        
        signal_data_us = {
            'trend': trend_us,
            'latest_rs': round(latest_us['relative_strength'], 2),
            'ma20': round(latest_us['rs_ma20'], 2),
            'ma60': round(latest_us['rs_ma60'], 2),
            'momentum_20d': round(momentum_20d_us, 2),
            'heavy_nav': round(latest_us['heavy_nav'], 2),
            'light_nav': round(latest_us['light_nav'], 2)
        }
    
    # 7. 保存输出
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    # 合并输出
    output_data = {
        'china': signal_data_cn,
        'us': signal_data_us,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # JSON
    json_path = os.path.join(data_dir, 'china_halo.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 保存 JSON: {json_path}")
    
    # CSV（中国完整时序）
    csv_path = os.path.join(data_dir, 'china_halo_history.csv')
    result_cn_with_ma.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ 保存 CSV: {csv_path}")
    
    # CSV（美国完整时序）
    if not result_us.empty:
        csv_path_us = os.path.join(data_dir, 'us_halo_history.csv')
        result_us.to_csv(csv_path_us, index=False, encoding='utf-8-sig')
        print(f"✅ 保存 CSV: {csv_path_us}")
    
    # 打印结果
    print("\n" + "=" * 60)
    print("📊 中国市场")
    print("=" * 60)
    print(f"趋势: {signal_data_cn['trend']}")
    print(f"建议: {signal_data_cn['signal']}")
    print(f"相对强弱: {signal_data_cn['latest_rs']} (MA20: {signal_data_cn['ma20']}, MA60: {signal_data_cn['ma60']})")
    print(f"20日动量: {signal_data_cn['momentum_20d']:.2f}%")
    print(f"重资产净值: {signal_data_cn['heavy_nav']} | 轻资产净值: {signal_data_cn['light_nav']}")
    
    if signal_data_us:
        print("\n" + "=" * 60)
        print("📊 美国市场（罗素3000拟合）")
        print("=" * 60)
        print(f"趋势: {signal_data_us['trend']}")
        print(f"相对强弱: {signal_data_us['latest_rs']} (MA20: {signal_data_us['ma20']}, MA60: {signal_data_us['ma60']})")
        print(f"20日动量: {signal_data_us['momentum_20d']:.2f}%")
        print(f"重资产净值: {signal_data_us['heavy_nav']} | 轻资产净值: {signal_data_us['light_nav']}")
        print("\n拟合方式: XLE+XLU+XLI+XLB (重资产) vs XLK+XLV+XLC+XLY (轻资产)")
    
    print("=" * 60)

if __name__ == '__main__':
    main()
