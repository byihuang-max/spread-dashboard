import sys
import requests
import hashlib
import time
import pandas as pd
from datetime import datetime, timedelta

# 配置信息
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com'

def generate_sign(params: dict, app_key: str) -> str:
    """生成签名：对参数key升序排序，按key=value拼接，加上密钥后md5"""
    sorted_items = sorted([(k, v) for k, v in params.items() if k != 'sign'])
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_items]) + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

# 第一步：先列出所有跟踪的基金
def list_all_funds():
    all_funds = []
    page = 1
    while True:
        url = f'{BASE_URL}/fof/subfund/track/list'
        tm = int(time.time())
        params = {
            'app_id': APP_ID,
            'page': page,
            'pagesize': 50,
            'type': 1,
            'tm': tm
        }
        params['sign'] = generate_sign(params, APP_KEY)
        
        response = requests.get(url, params=params, timeout=(5, 15))
        data = response.json()
        if data.get('error_code') != 0:
            print(f"获取列表出错: {data.get('msg')}")
            break
        
        funds = data.get('data', {}).get('List', []) or data.get('data', {}).get('list', [])
        if not funds:
            break
        
        all_funds.extend(funds)
        page += 1
    
    print(f"共获取到 {len(all_funds)} 只基金:")
    for i, f in enumerate(all_funds[:10]):
        print(f"{i+1}. {f.get('fund_short_name')} - {f.get('register_number')}")
    
    return all_funds

# 尝试获取净值，根据火富牛常见接口
def get_fund_nav(register_num, start_date, end_date):
    url = f'{BASE_URL}/fof/subfund/nav/getByFund'
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'register_num': register_num,
        'start_date': start_date,
        'end_date': end_date,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    response = requests.get(url, params=params, timeout=(5, 15))
    try:
        data = response.json()
        if data.get('error_code') == 0:
            nav_list = data.get('data', {}).get('list', [])
            return pd.DataFrame(nav_list)
        else:
            print(f"获取失败: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"解析失败: {e}, 响应: {response.text[:200]}")
        return None

if __name__ == '__main__':
    funds = list_all_funds()
    if not funds:
        print("未获取到基金")
        sys.exit(1)
    
    # 日期计算：当前是2026-03-30周一
    # 上周五=2026-03-27，上上周五=2026-03-20
    last_friday = '2026-03-27'
    prev_prev_friday = '2026-03-20'
    
    print(f"\n需要获取的日期区间: {prev_prev_friday} 到 {last_friday}")
    
    # 取前3只基金测试
    results = []
    for fund in funds[:3]:
        name = fund.get('fund_short_name')
        reg = fund.get('register_number')
        print(f"\n正在获取 {name} ({reg})...")
        
        nav_df = get_fund_nav(reg, prev_prev_friday, last_friday)
        if nav_df is None or nav_df.empty:
            print("  无数据")
            continue
        
        print(f"  获取到 {len(nav_df)} 条净值记录")
        
        # 查找两个周五的净值
        nav_prev = nav_df[nav_df['date'] == prev_prev_friday]
        nav_last = nav_df[nav_df['date'] == last_friday]
        
        if nav_prev.empty or nav_last.empty:
            # 如果日期不在周末或节假日，找最近交易日
            print(f"  找不到完全匹配日期，尝试最近交易日...")
            nav_df_sorted = nav_df.sort_values('date')
            if not nav_prev.empty:
                prev_val = nav_prev.iloc[0]['nav']
                prev_date = prev_prev_friday
            else:
                prev_row = nav_df_sorted[nav_df_sorted['date'] <= prev_prev_friday].iloc[-1] if not nav_df_sorted[nav_df_sorted['date'] <= prev_prev_friday].empty else None
                if not prev_row:
                    print("  找不到上上周五附近数据")
                    continue
                prev_val = prev_row['nav']
                prev_date = prev_row['date']
            
            if not nav_last.empty:
                last_val = nav_last.iloc[0]['nav']
                last_date = last_friday
            else:
                last_row = nav_df_sorted[nav_df_sorted['date'] <= last_friday].iloc[-1] if not nav_df_sorted[nav_df_sorted['date'] <= last_friday].empty else None
                if not last_row:
                    print("  找不到上周五附近数据")
                    continue
                last_val = last_row['nav']
                last_date = last_row['date']
        else:
            prev_val = nav_prev.iloc[0]['nav']
            prev_date = prev_prev_friday
            last_val = nav_last.iloc[0]['nav']
            last_date = last_friday
        
        ret = (float(last_val) - float(prev_val)) / float(prev_val) * 100
        results.append({
            '基金名称': name,
            '备案号': reg,
            '上上周五日期': prev_date,
            '上上周五净值': float(prev_val),
            '上周五日期': last_date,
            '上周五净值': float(last_val),
            '周收益率(%)': round(ret, 2)
        })
    
    print("\n======= 最终计算结果 =======")
    if results:
        df = pd.DataFrame(results)
        print(df.to_string(index=False))
    else:
        print("未获取到有效数据")
