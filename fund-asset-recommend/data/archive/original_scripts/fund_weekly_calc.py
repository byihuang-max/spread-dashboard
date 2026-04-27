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
    # 移除sign参数，按key升序排序
    sorted_items = sorted([(k, v) for k, v in params.items() if k != 'sign'])
    # 拼接字符串
    sign_str = '&'.join([f'{k}={v}' for k, v in sorted_items]) + app_key
    # 计算md5
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

def get_fund_list(page=1, pagesize=50, type_=1) -> dict:
    """获取跟踪基金列表"""
    url = f'{BASE_URL}/fof/subfund/track/list'
    tm = int(time.time())
    params = {
        'app_id': APP_ID,
        'page': page,
        'pagesize': pagesize,
        'type': type_,
        'tm': tm
    }
    params['sign'] = generate_sign(params, APP_KEY)
    
    response = requests.get(url, params=params)
    return response.json()

def get_nav(fund_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取基金净值数据，尝试多个常见接口路径"""
    possible_paths = [
        '/fof/subfund/nav/list',
        '/fof/subfund/nav/get',
        '/api/fund/nav',
        '/fof/fund/nav/list',
        '/open/fund/nav'
    ]
    
    for path in possible_paths:
        url = f'{BASE_URL}{path}'
        tm = int(time.time())
        params = {
            'app_id': APP_ID,
            'fund_code': fund_code,
            'start_date': start_date,
            'end_date': end_date,
            'tm': tm
        }
        params['sign'] = generate_sign(params, APP_KEY)
        
        response = requests.get(url, params=params)
        if response.status_code == 404:
            continue
        
        try:
            json_data = response.json()
            if json_data.get('error_code', -1) == 0:
                nav_list = json_data.get('data', {}).get('list', []) or json_data.get('data', [])
                if nav_list:
                    return pd.DataFrame(nav_list)
            else:
                print(f"  {path} 错误: {json_data.get('msg')}")
        except Exception as e:
            print(f"  {path} 解析失败: {e}, 响应: {response.text[:100]}")
    
    print(f"  所有尝试的接口都失败")
    return pd.DataFrame()

def find_nearest_trade_date(target_date: datetime, nav_dates: list) -> datetime:
    """在nav_dates中找到小于等于target_date的最近交易日"""
    nav_dates = sorted([datetime.strptime(d, '%Y-%m-%d') for d in nav_dates if d])
    candidates = [d for d in nav_dates if d <= target_date]
    if not candidates:
        return None
    return max(candidates)

def calculate_weekly_return():
    """计算最近完整工作周的收益率"""
    # 步骤1：确定当前时间，计算上周五和上上周五
    today = datetime.now()
    print(f"当前时间: {today.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 找最近的上周五：从今天向前找最近的周五
    current = today
    while current.weekday() != 4:  # 4=周五
        current -= timedelta(days=1)
    last_friday = current
    print(f"找到上周五: {last_friday.strftime('%Y-%m-%d')}")
    
    # 上上周五：从上周五向前5个日历天，再找该日期之前最近交易日
    # 实际上我们需要上上周的周五，直接向前推7天更准确
    prev_prev_friday = last_friday - timedelta(days=7)
    print(f"上上周五: {prev_prev_friday.strftime('%Y-%m-%d')}")
    
    # 获取基金列表
    print("\n获取基金列表...")
    # 尝试不同type值：1-投资-公司产品，4-入池产品，5-FOF底层
    for type_test in [1, 4, 5, 3]:
        fund_list_resp = get_fund_list(page=1, pagesize=20, type_=type_test)
        print(f"type={type_test}, error_code={fund_list_resp.get('error_code')}, msg={fund_list_resp.get('msg')}")
        funds = fund_list_resp.get('data', {}).get('List', []) or fund_list_resp.get('data', {}).get('list', [])
        print(f"  获取到 {len(funds)} 只基金")
        if len(funds) > 0:
            break
    
    # 打印基金列表
    for f in funds[:10]:
        print(f" - {f.get('fund_short_name')} ({f.get('register_number')})")
    
    # 尝试获取净值并计算
    results = []
    for fund in funds[:5]:  # 先处理前5只测试
        short_name = fund.get('fund_short_name')
        reg_num = fund.get('register_number')
        print(f"\n获取 {short_name} 净值...")
        
        # 获取这段时间的净值
        nav_df = get_nav(reg_num, 
                         prev_prev_friday.strftime('%Y-%m-%d'), 
                         last_friday.strftime('%Y-%m-%d'))
        
        if nav_df.empty or 'nav' not in nav_df.columns or 'date' not in nav_df.columns:
            print(f"  无可用净值数据，跳过")
            continue
        
        # 找到对应日期的净值
        nav_dates = nav_df['date'].tolist()
        last_friday_nav_date = find_nearest_trade_date(last_friday, nav_dates)
        prev_prev_friday_nav_date = find_nearest_trade_date(prev_prev_friday, nav_dates)
        
        if not last_friday_nav_date or not prev_prev_friday_nav_date:
            print(f"  找不到对应日期净值，跳过")
            continue
        
        nav_last = nav_df[nav_df['date'] == last_friday_nav_date.strftime('%Y-%m-%d')]['nav'].iloc[0]
        nav_prev = nav_df[nav_df['date'] == prev_prev_friday_nav_date.strftime('%Y-%m-%d')]['nav'].iloc[0]
        
        ret = (float(nav_last) - float(nav_prev)) / float(nav_prev) * 100
        
        results.append({
            '基金名称': short_name,
            '备案号': reg_num,
            '上上周五日期': prev_prev_friday_nav_date.strftime('%Y-%m-%d'),
            '上上周五净值': float(nav_prev),
            '上周五日期': last_friday_nav_date.strftime('%Y-%m-%d'),
            '上周五净值': float(nav_last),
            '周收益率(%)': round(ret, 2)
        })
    
    if results:
        df_result = pd.DataFrame(results)
        print("\n=== 计算结果 ===")
        print(df_result.to_string(index=False))
        return df_result
    else:
        print("\n没有计算出有效结果，请检查接口是否正确")
        return None

if __name__ == '__main__':
    result = calculate_weekly_return()
