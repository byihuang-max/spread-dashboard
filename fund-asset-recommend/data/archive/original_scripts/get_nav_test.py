import requests
import hashlib
import time
import pandas as pd
from datetime import datetime, timedelta

# 配置
APP_ID = 'hfnogbr8zceiiygdkhw'
APP_KEY = 'c6e941fd6aad65ceede2d780262d11ee'
BASE_URL = 'https://mallapi.huofuniu.com'

def generate_sign(params, app_key):
    sorted_items = sorted([(k, v) for k, v in params.items() if k != 'sign'])
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_items]) + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

# 先确认日期
last_friday = '2026-03-27'
prev_prev_friday = '2026-03-20'

print(f"按照规则确定的日期：")
print(f"- 上周五：{last_friday}")
print(f"- 上上周五：{prev_prev_friday}")
print()

# 获取前3只基金测试
funds = [
    {"name": "长城证券金满六月2号", "reg": "SP4391"},
    {"name": "中粮信托-通达1号", "reg": "SR7167"},
    {"name": "新纪元开元20号", "reg": "SR7367"},
]

# 尝试常见的净值接口
possible_paths = [
    "/fof/subfund/nav/getByFund",
    "/fof/subfund/nav/list",
    "/fof/fund/nav/get",
    "/api/v1/fund/nav",
]

results = []

for fund in funds:
    name = fund["name"]
    reg = fund["reg"]
    print(f"正在测试 {name} ({reg})...")
    
    found = False
    for path in possible_paths:
        url = BASE_URL + path
        tm = int(time.time())
        params = {
            "app_id": APP_ID,
            "register_number": reg,
            "register_num": reg,
            "fund_code": reg,
            "start_date": prev_prev_friday,
            "end_date": last_friday,
            "tm": tm
        }
        # 清理空值
        params = {k: v for k, v in params.items() if v is not None}
        params["sign"] = generate_sign(params, APP_KEY)
        
        try:
            resp = requests.get(url, params=params, timeout=(5, 15))
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            if data.get("error_code") != 0:
                print(f"  {path} -> 错误: {data.get('msg')}")
                continue
            
            nav_list = data.get("data", {}).get("list", [])
            if nav_list and len(nav_list) > 0:
                print(f"  {path} -> 成功获取 {len(nav_list)} 条净值")
                df = pd.DataFrame(nav_list)
                
                # 找两个日期的净值
                df_prev = df[df['date'] == prev_prev_friday]
                df_last = df[df['date'] == last_friday]
                
                if not df_prev.empty and not df_last.empty:
                    nav_prev = float(df_prev.iloc[0]['nav'])
                    nav_last = float(df_last.iloc[0]['nav'])
                    ret = (nav_last - nav_prev) / nav_prev * 100
                    results.append({
                        "基金": name,
                        "上上周五": prev_prev_friday,
                        "上上净值": nav_prev,
                        "上周五": last_friday,
                        "上周五净值": nav_last,
                        "周收益率%": round(ret, 2)
                    })
                    found = True
                    break
        except Exception as e:
            print(f"  {path} -> 异常: {str(e)[:50]}")
            continue
    
    if not found:
        print(f"  未获取到有效数据")
    
    print()

print("="*50)
print("最终测试结果：")
print("="*50)
if results:
    df_result = pd.DataFrame(results)
    print(df_result.to_string(index=False))
else:
    print("未获取到任何基金的净值数据，请确认净值接口路径是否正确")
