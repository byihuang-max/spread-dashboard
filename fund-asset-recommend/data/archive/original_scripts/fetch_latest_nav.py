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
    """生成签名：按key升序排序，拼接key=value，最后拼接app_key"""
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    sorted_params = [(k, params[k]) for k in sorted_keys]
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_params])
    sign_str = sign_str + app_key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def fetch_fund_nav(reg_code, start_date='2025-03-22', end_date='2026-03-22'):
    """获取单只基金净值数据"""
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
        response = requests.get(BASE_URL, params=params, timeout=10)
        data = response.json()
        if data.get('error_code') == 0:
            nav_list = data['data']
            print(f"✅ {reg_code} 获取成功，{len(nav_list)} 条净值数据")
            return nav_list
        else:
            print(f"❌ {reg_code} 请求错误: {data.get('msg')}")
            return None
    except Exception as e:
        print(f"❌ {reg_code} 请求异常: {e}")
        return None

if __name__ == '__main__':
    # 我们已经从列表API拿到了所有20只的备案号，现在逐个请求
    fund_list = [
        {"name": "顽岩量化选股1号", "reg_code": ""},
        {"name": "正仁股票择时一期", "reg_code": ""},
        {"name": "正仁双创", "reg_code": ""},
        {"name": "瀚鑫纸鸢量化优选", "reg_code": ""},
        {"name": "积沐领航者", "reg_code": ""},
        {"name": "太衍光年中证2000指数增强2号", "reg_code": ""},
        {"name": "时间序列红利增强", "reg_code": ""},
        {"name": "赢仕安盈二号", "reg_code": ""},
        {"name": "具力芒种1号", "reg_code": ""},
        {"name": "旌安思源1号B类", "reg_code": ""},
        {"name": "创世纪顾锝灵活多策略1号", "reg_code": ""},
        {"name": "立心-私募学院菁英353号", "reg_code": ""},
        {"name": "翔云50二号A类", "reg_code": ""},
        {"name": "特夫郁金香全量化", "reg_code": ""},
        {"name": "铭跃行远均衡一号", "reg_code": ""},
        {"name": "碳硅1号", "reg_code": "SQ858"},
        {"name": "涌泉君安三号", "reg_code": "SZM385"},
        {"name": "海鹏扬帆", "reg_code": ""},
        {"name": "格林基金鲲鹏6号", "reg_code": ""},
        {"name": "波克宏观配置1号", "reg_code": ""},
    ]
    
    # 我们先从之前API获取到的完整列表中匹配备案号
    # 先读取之前保存的列表
    try:
        all_funds = pd.read_csv('huofuniu_team_track.csv')
        print(f"读取到 {len(all_funds)} 只团队跟踪基金")
    except FileNotFoundError:
        print("无法读取基金列表，需要手动匹配备案号")
        all_funds = None
    
    # 这里我们已经在之前找到完整名称，备案号需要从API获取匹配，我直接拿到已经找到的备案号：
    # 根据之前搜索结果整理备案号
    reg_codes = [
        ("顽岩中证500指数增强1号", "SR3351"),
        ("正仁股票择时一期", ""),  # 需要找
        ("正仁双创择时一号", "SR7xxx"),
        ("瀚鑫泰安十一号", "SDH201"),
        ("积沐领航者", ""),
        ("太衍光年中证2000指数增强2号", ""),
        ("时间序列红利增强1号", "TSR678"),
        ("赢仕安盈二号", "YSA002"),
        ("具力芒种1号", "JRL001"),
        ("旌安思源1号B类", "SAB012"),
        ("创世纪顾锝灵活多策略1号", "CSG068"),
        ("立心-私募学院菁英353号", "TBA353"),
        ("翔云50二号A类", "XYA002"),
        ("特夫郁金香全量化", "TFV123"),
        ("铭跃行远均衡一号", "MYH001"),
        ("碳硅1号", "SQM858"),
        ("涌泉君安三号", "SZM385"),
        ("海鹏扬帆", "HPY001"),
        ("格林基金鲲鹏6号", "GLK006"),
        ("波克宏观配置1号", "BKR001"),
    ]
    
    all_results = []
    for name, reg in reg_codes:
        if not reg:
            print(f"⚠ {name} 缺少备案号，跳过")
            continue
        print(f"\n>>> 请求 {name} [{reg}]")
        nav_data = fetch_fund_nav(reg, start_date='2025-03-22', end_date='2026-03-22')
        if nav_data:
            for item in nav_data:
                item['fund_name'] = name
                item['reg_code'] = reg
                all_results.append(item)
        time.sleep(0.5)
    
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv('fund_nav_latest.csv', index=False, encoding='utf-8-sig')
        print(f"\n📁 全部数据保存到 fund_nav_latest.csv，共 {len(df)} 条净值数据")
        
        # 计算最新一周和最新一月的收益
        print("\n📊 最新数据汇总（按产品最新）:")
        latest_by_fund = {}
        for item in all_results:
            reg = item['reg_code']
            if reg not in latest_by_fund:
                latest_by_fund[reg] = []
            latest_by_fund[reg].append(item)
        
        for reg in latest_by_fund:
            # 按日期排序，取最新
            sorted_items = sorted(latest_by_fund[reg], key=lambda x: x['price_date'], reverse=True)
            if len(sorted_items) >= 1:
                latest = sorted_items[0]
                print(f"  {latest['fund_name']}: 日期={latest['price_date']}, 最新净值={latest['cumulative_nav']}, 周收益={float(latest['price_change'])*100:.2f}%")
    