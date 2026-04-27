#!/usr/bin/env python3
"""
业绩预告API测试脚本
测试Tushare API获取业绩预告数据的可行性
"""
import requests
import pandas as pd
from datetime import datetime
import time

# Tushare私有地址
TUSHARE_TOKEN = "33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd"
TUSHARE_SERVER = "http://lianghua.nanyangqiankun.top"

def tushare_query(api_name, fields='', **params):
    """直连Tushare私有地址"""
    data = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params,
        'fields': fields
    }
    try:
        resp = requests.post(TUSHARE_SERVER, json=data, timeout=10)
        result = resp.json()
        if result['code'] != 0:
            print(f"API错误: {result['msg']}")
            return None
        df = pd.DataFrame(result['data']['items'], columns=result['data']['fields'])
        return df
    except Exception as e:
        print(f"请求失败: {e}")
        return None


def get_index_components(index_code='000300.SH', limit=10):
    """获取指数成分股（测试用，只取前N只）"""
    print(f"\n获取{index_code}成分股...")
    df = tushare_query('index_weight',
                       index_code=index_code,
                       fields='con_code,trade_date,weight')
    if df is None or len(df) == 0:
        return []
    
    # 取最新一期的成分股
    latest_date = df['trade_date'].max()
    df_latest = df[df['trade_date'] == latest_date]
    stocks = df_latest['con_code'].unique()[:limit]
    print(f"  最新日期: {latest_date}, 成分股数: {len(df_latest)}, 测试取前{limit}只")
    return stocks.tolist()


def get_forecast_batch(ts_codes, end_date='20241231'):
    """批量获取业绩预告"""
    results = []
    total = len(ts_codes)
    
    for i, ts_code in enumerate(ts_codes):
        print(f"  [{i+1}/{total}] {ts_code}...", end='')
        df = tushare_query('forecast',
                          ts_code=ts_code,
                          fields='ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,summary')
        
        if df is not None and len(df) > 0:
            # 筛选指定报告期的最新预告
            df_period = df[df['end_date'] == end_date]
            if len(df_period) > 0:
                # 取最新公告日期的数据
                latest = df_period.sort_values('ann_date', ascending=False).iloc[0]
                results.append(latest)
                print(f" ✓ {latest['type']}")
            else:
                print(" - 无数据")
        else:
            print(" - 失败")
        
        time.sleep(0.1)  # 避免请求过快
    
    return pd.DataFrame(results) if results else None


def classify_forecast_type(forecast_type):
    """分类业绩预告类型"""
    if pd.isna(forecast_type):
        return '未知'
    
    forecast_type = str(forecast_type).strip()
    
    # 预喜类型
    if forecast_type in ['预增', '略增', '扭亏', '续盈']:
        return '预喜'
    # 悲观类型
    elif forecast_type in ['预减', '略减', '首亏', '续亏', '增亏', '减亏']:
        return '悲观'
    # 中性
    elif forecast_type in ['不确定']:
        return '中性'
    else:
        return '其他'


def main():
    print("="*60)
    print("业绩预告API测试")
    print("="*60)
    
    # 1. 获取沪深300成分股（测试用，只取10只）
    stocks = get_index_components('000300.SH', limit=10)
    if not stocks:
        print("获取成分股失败")
        return
    
    # 2. 批量获取业绩预告
    print(f"\n获取2024年报业绩预告（end_date=20241231）:")
    df_forecast = get_forecast_batch(stocks, end_date='20241231')
    
    if df_forecast is None or len(df_forecast) == 0:
        print("\n未获取到业绩预告数据")
        return
    
    # 3. 分类统计
    print(f"\n获取到 {len(df_forecast)} 条业绩预告")
    df_forecast['预警分类'] = df_forecast['type'].apply(classify_forecast_type)
    
    print("\n预告类型分布:")
    print(df_forecast['type'].value_counts())
    
    print("\n预警分类分布:")
    print(df_forecast['预警分类'].value_counts())
    
    print(f"\n悲观比例: {df_forecast['预警分类'].value_counts(normalize=True).get('悲观', 0):.2%}")
    print(f"预喜比例: {df_forecast['预警分类'].value_counts(normalize=True).get('预喜', 0):.2%}")
    
    print("\n详细数据:")
    print(df_forecast[['ts_code', 'ann_date', 'type', '预警分类', 'p_change_min', 'p_change_max']])
    
    print("\n" + "="*60)
    print("测试结论:")
    print("✓ API可用，能获取到2024年报业绩预告数据")
    print("✓ 数据结构符合预期，可以进行分类统计")
    print("✓ 下一步：扩展到全部指数成分股，添加民营/国有分类")


if __name__ == '__main__':
    main()
