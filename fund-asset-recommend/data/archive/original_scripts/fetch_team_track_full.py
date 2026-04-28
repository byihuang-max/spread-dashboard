#!/usr/bin/env python3
import hashlib
import requests
import time
import pandas as pd

APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com/fof/subfund/track/list'

def generate_sign(params, app_key):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_all_team_track(page=1, pagesize=50):
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': pagesize,
        'type': 3,  # 👉 type=3 是团队跟踪
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    print(f"请求团队跟踪 page={page}, pagesize={pagesize}")
    response = requests.get(BASE_URL, params=params, timeout=15)
    data = response.json()
    if data.get('error_code') == 0:
        fund_list = data['data']['list']
        count = data['data']['count']
        print(f"获取成功，本页 {len(fund_list)} 只，总共 {count} 只")
        return fund_list, count
    else:
        print(f"错误: {data.get('msg')}")
        return [], 0

if __name__ == '__main__':
    all_funds = []
    page = 1
    total = None
    while True:
        funds, count = fetch_all_team_track(page=page, pagesize=50)
        all_funds.extend(funds)
        if total is None:
            total = count
        if len(all_funds) >= total:
            break
        page += 1
        time.sleep(0.5)
    
    print(f"\n✅ 完成，总共获取 {len(all_funds)} 只基金")
    df = pd.DataFrame(all_funds)
    df.to_csv('huofuniu_full_team_list.csv', index=False, encoding='utf-8-sig')
    print(f"💾 已保存到 huofuniu_full_team_list.csv")
    
    # 查找我们目标基金
    target_names = [
        "顽岩", "正仁", "双创", "瀚鑫纸鸢", "积沐领航", "太衍光年", 
        "红利", "赢仕安盈", "芒种", "旌安", "顾锝", 
        "立心", "翔云", "特夫", "铭跃", "碳硅", 
        "涌泉", "海鹏", "鲲鹏", "波克"
    ]
    
    found = []
    for target in target_names:
        matches = df[df['fund_short_name'].str.contains(target)]
        if len(matches) > 0:
            print(f"\n🔍 找到 '{target}' 共 {len(matches)} 只:")
            for idx, row in matches.iterrows():
                print(f"   - {row['fund_short_name']} [{row['register_number']}] price_type={row['price_type']}")
                found.append({
                    "target": target,
                    "name": row['fund_short_name'],
                    "reg_code": row['register_number'],
                    "price_type": row['price_type']
                })
    
    df_found = pd.DataFrame(found)
    df_found.to_csv('matched_full_team_list.csv', index=False, encoding='utf-8-sig')
    print(f"\n📝 找到 {len(df_found)} 只，保存到 matched_full_team_list.csv")
