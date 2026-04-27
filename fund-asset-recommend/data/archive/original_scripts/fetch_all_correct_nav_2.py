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
    # 我们最终要的20只产品 准确匹配 名称/备案号
    our_20 = [
        # (我们的简称, 火富牛找到的全名, 备案号)
        ("顽岩量化选股1号", "顽岩中证500指数增强1号", "SSA143"),
        ("正仁股票择时一期", "正仁股票择时一期", "SLZ218"),
        ("双创择时（正仁双创）", "正仁双创择时一号", "SXG834"),
        ("微盘择时（瀚鑫纸鸢量化优选）", "瀚鑫泰安十一号", "SDH201"),
        ("1000指增（积沐领航者）", None, None),  # 需要找
        ("2000指增T0（太衍光年）", None, None),
        ("红利指增（时间序列红利增强）", "时间序列红利增强一号", "SSV122"),
        ("转债多头集中类（赢仕安盈）", "赢仕安盈二号", "SLQ349"),
        ("转债多头分散类（具力芒种）", "具力芒种1号", "STE836"),
        ("短线择时（旌安思源）", None, None),
        ("趋势策略（创世纪顾锝灵活多策略）", "创世纪顾锝新锐一号", "SACQ68"),
        ("主线择时（立心）", "立心-私募学院菁英353号", "SCJ476"),
        ("大盘择时（翔云）", "翔云50二号A类", "VB166A"),
        ("量化打板（特夫）", "特夫郁金香全量化", "SQX078"),
        ("量化时序cta（铭跃行远)", "铭跃行远均衡一号", "SVZ009"),
        ("化工-碳硅1号", "碳硅一号", "SXJ836"),
        ("黑色-涌泉君安三号", "涌泉君安三号", "SZM385"),
        ("农产品-海鹏扬帆", "海鹏扬帆", "SSR379"),
        ("黄金大类（格林基金鲲鹏）", "格林基金鲲鹏六号", "SVZ638"),
        ("宏观大类（波克）", "波克平衡多策略一号", "SZR639"),
    ]
    
    all_results = []
    final_summary = []
    
    for our_name, full_name, reg_code in our_20:
        if reg_code is None:
            print(f"\n⚠️ {our_name} 缺少备案号，跳过")
            continue
        print(f"\n>>>>> 获取 {our_name} - {full_name} [{reg_code}]")
        nav_data = fetch_fund_nav(reg_code)
        if nav_data:
            print(f"  ✅ 获取成功，{len(nav_data)} 条净值")
            for item in nav_data:
                item['our_name'] = our_name
                item['full_name'] = full_name
                item['reg_code'] = reg_code
                all_results.append(item)
            # 计算最新收益
            if len(nav_data) >= 1:
                nav_data_sorted = sorted(nav_data, key=lambda x: x['price_date'], reverse=True)
                latest = nav_data_sorted[0]
                weekly_change = float(latest['price_change']) * 100
                print(f"  📊 最新: 日期={latest['price_date']}, 周收益={weekly_change:.2f}%")
                final_summary.append({
                    "our_name": our_name,
                    "full_name": full_name,
                    "reg_code": reg_code,
                    "latest_date": latest['price_date'],
                    "weekly_change": weekly_change,
                    "latest_nav": float(latest['cumulative_nav'])
                })
        time.sleep(0.8)
    
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv('all_funds_latest_nav.csv', index=False, encoding='utf-8-sig')
        print(f"\n✅ 完成，总共 {len(all_results)} 条净值数据，保存到 all_funds_latest_nav.csv")
        print("\n📊 最新每周收益汇总:")
        for item in final_summary:
            print(f"  {item['our_name']}: 日期={item['latest_date']}, 周收益={item['weekly_change']:.2f}%")
