#!/usr/bin/env python3
import hashlib
import requests
import time
import pandas as pd
from urllib.parse import urlencode

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
    # 读取匹配好的备案号
    match_df = pd.read_csv('matched_regcodes.csv')
    
    # 我们需要精确匹配到我们要的那20只，这里选最准确的：
    target_map = {
        "顽岩": ("顽岩中证500指数增强1号", "SSA143"),
        "正仁": ("正仁股票择时一期", "SLZ218"),
        "正仁双创": ("正仁双创择时一号", "SXG834"),
        "瀚鑫纸鸢": ("瀚鑫泰安十一号", "SDH201"),
        "积沐领航": ("积沐领航者", None),  # 还没找到精确匹配，需要手动确认
        "太衍光年": ("太衍光年中证2000指数增强二号", None),
        "时间红利": ("时间序列红利增强一号", "SSV122"),
        "赢仕安盈": ("赢仕安盈二号", "SLQ349"),
        "具力芒种": ("具力芒种1号", "STE836"),
        "旌安思源": ("旌安思源1号B", None),
        "创世纪顾锝": ("创世纪顾锝新锐一号", "SACQ68"),
        "立心": ("立心-私募学院菁英353号", "SCJ476"),
        "翔云": ("翔云50二号A类", "VB166A"),
        "特夫": ("特夫郁金香全量化", "SQX078"),
        "铭跃行远": ("铭跃行远均衡一号", "SVZ009"),
        "碳硅": ("碳硅一号", "SXJ836"),
        "涌泉君安": ("涌泉君安三号", "SZM385"),
        "海鹏扬帆": ("海鹏扬帆", "SSR379"),
        "格林鲲鹏": ("格林基金鲲鹏六号", "SVZ638"),
        "波克": ("波克宏观配置一号", "SZR639"),
    }
    
    all_results = []
    final_list = []
    
    for target_name, (full_name, reg_code) in target_map.items():
        if reg_code is None:
            # 从匹配列表找
            match_row = match_df[match_df['target'] == target_name].iloc[0]
            full_name = match_row['found_name']
            reg_code = match_row['register_number']
        print(f"\n>>>>> 获取 {target_name} - {full_name} [{reg_code}]")
        nav_data = fetch_fund_nav(reg_code)
        if nav_data:
            print(f"  ✅ 获取成功，{len(nav_data)} 条净值")
            for item in nav_data:
                item['fund_target'] = target_name
                item['full_name'] =full_name
                item['reg_code'] = reg_code
                all_results.append(item)
            # 计算最新收益
            if len(nav_data) >= 1:
                # 按日期排序
                nav_data_sorted = sorted(nav_data, key=lambda x: x['price_date'], reverse=True)
                latest = nav_data_sorted[0]
                print(f"  📊 最新: 日期={latest['price_date']}, 复权净值={latest['cumulative_nav']}, 周收益={float(latest['price_change'])*100:.2f}%")
                final_list.append({
                    "name": full_name,
                    "reg_code": reg_code,
                    "latest_date": latest['price_date'],
                    "latest_nav": float(latest['cumulative_nav']),
                    "weekly_change": float(latest['price_change']) * 100
                })
        time.sleep(0.8)
    
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv('all_funds_latest_nav.csv', index=False, encoding='utf-8-sig')
        print(f"\n✅ 完成，获取到 {len(all_results)} 只基金最新净值，保存到 all_funds_latest_nav.csv")
        print("\n📊 汇总最新每周收益:")
        for item in final_list:
            print(f"  {item['name']}: 日期={item['latest_date']}, 近一周={item['weekly_change']:.2f}%")
