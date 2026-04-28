#!/usr/bin/env python3
import hashlib
import requests
import time
import pandas as pd

# 配置信息
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com/price'

def generate_sign(params, app_key):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_fund_nav(reg_code, start_date='2025-03-22', end_date='2026-03-22'):
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'reg_code': reg_code,
        'order': '0',
        'order_by': 'price_date',
        'start_date': start_date,
        'end_date': end_date,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=15)
        data = response.json()
        if data.get('error_code') == 0:
            nav_list = data['data']
            return nav_list
        else:
            print(f"  ❌ 错误: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        return None

if __name__ == '__main__':
    # 读取匹配好的列表
    match_df = pd.read_csv('matched_full_team_list.csv')
    print(f"读取到 {len(match_df)} 只目标基金")
    
    all_results = []
    final_summary = []
    
    for idx, row in match_df.iterrows():
        target_name = row['target']
        full_name = row['name']
        reg_code = row['reg_code']
        price_type = row['price_type']
        print(f"\n>>>>> [{idx+1}/{len(match_df)}] {target_name} - {full_name} [{reg_code}]")
        nav_data = fetch_fund_nav(reg_code)
        if nav_data:
            print(f"  ✅ 获取成功，{len(nav_data)} 条净值")
            for item in nav_data:
                item['target_name'] = target_name
                item['full_name'] = full_name
                item['reg_code'] = reg_code
                all_results.append(item)
            # 计算最新收益
            if len(nav_data) > 0:
                nav_data_sorted = sorted(nav_data, key=lambda x: x['price_date'], reverse=True)
                latest = nav_data_sorted[0]
                weekly_change = float(latest['price_change']) * 100
                print(f"  📊 最新日期: {latest['price_date']}, 周收益: {weekly_change:.2f}%")
                final_summary.append({
                    "target_name": target_name,
                    "full_name": full_name,
                    "reg_code": reg_code,
                    "latest_date": latest['price_date'],
                    "weekly_change": weekly_change,
                    "latest_cumulative": float(latest['cumulative_nav'])
                })
        time.sleep(0.6)
    
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv('all_full_nav_data.csv', index=False, encoding='utf-8-sig')
        print(f"\n✅ 完成，总共 {len(all_results)} 条净值数据保存到 all_full_nav_data.csv")
        print("\n📊 最新每周收益汇总:")
        for item in final_summary:
            print(f"  {item['full_name']}: 日期={item['latest_date']}, 周收益={item['weekly_change']:.2f}%")
