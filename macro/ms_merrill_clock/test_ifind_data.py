#!/usr/bin/env python3
"""
测试 iFind 能否获取大摩四象限所需数据
1. 社融结构（居民/企业信贷占比）
2. 企业债利差（AAA/AA企业债 - 国债）
3. R007-DR007利差
"""
import requests
import json
from datetime import datetime, timedelta

# iFind 配置
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAzLTA4IDE5OjE0OjAzIn0=.eyJ1aWQiOiI4NTAzMDMzMDIiLCJ1c2VyIjp7ImFjY291bnQiOiJnbG1zc2YwMDEiLCJhdXRoVXNlckluZm8iOnsiY3NpIjp0cnVlLCJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbIjExIiwiMjIiLCIyNSIsIjI2IiwiMTYiLCIxOCIsIjE5IiwiMSIsIjIiLCIzIiwiNCIsIjUiLCI2IiwiNyIsIjgiLCI5IiwiMjAiLCIxMCIsIjIxIl0sImhhc0FJUHJlZGljdCI6ZmFsc2UsImhhc0FJVGFsayI6ZmFsc2UsImhhc0NJQ0MiOmZhbHNlLCJoYXNDU0kiOnRydWUsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1hcmtldENvZGUiOiIxNjszMjsxNDQ7MTc2OzExMjs4ODs0ODsxMjg7MTY4LTE7MTg0OzIwMDsyMTY7MTA0OzEyMDsxMzY7MjMyOzU2Ozk2OzE2MDs2NDsiLCJtYXhPbkxpbmUiOjEsIm5vRGlzayI6ZmFsc2UsInByb2R1Y3RUeXBlIjoiU1VQRVJDT01NQU5EUFJPRFVDVCIsInJlZnJlc2hUb2tlbkV4cGlyZWRUaW1lIjoiMjAyNi0wNC0wNyAxOTowNDoxMiIsInNlc3NzaW9uIjoiYjk1N2Y1ZGU5OGNmOGMwNzhiZjk2Yzk4ZDRhOTllMDQiLCJzaWRJbmZvIjp7NjQ6IjExMTExMTExMTExMTExMTExMTExMTExMSIsMToiMTAxIiwyOiIxIiw2NzoiMTAxMTExMTExMTExMTExMTExMTExMTExIiwzOiIxIiw2OToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsNToiMSIsNjoiMSIsNzE6IjExMTExMTExMTExMTExMTExMTExMTEwMCIsNzoiMTExMTExMTExMTEiLDg6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMDAxIiwxMzg6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDEzOToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQwOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDE6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MjoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQzOiIxMSIsODA6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODE6IjExMTExMTExMTExMTExMTExMTExMTExMSIsODI6IjExMTExMTExMTExMTExMTExMTExMDExMCIsODM6IjExMTExMTExMTExMTExMTExMTAwMDAwMCIsODU6IjAxMTExMTExMTExMTExMTExMTExMTExMSIsODc6IjExMTExMTExMDAxMTExMTAxMTExMTExMSIsODk6IjExMTExMTExMDExMDExMTExMTEwMTExMSIsOTA6IjExMTExMDExMTExMTExMTExMTExMTExMTEwIiw5MzoiMTExMTExMTExMTExMTExMTEwMDAwMTExMSIsOTQ6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk2OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw5OToiMTAwIiwxMDA6IjExMTEwMTExMTExMTExMTExMTAiLDEwMjoiMSIsNDQ6IjExIiwxMDk6IjEiLDUzOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDU0OiIxMTAwMDAwMDAwMTEwMDAwMDEwMTAwMDAwMTAwMTAwMDAwMCIsNTc6IjAwMDAwMDAwMDAwMDAwMDAwMDAwMTAwMDAwMDAwIiw2MjoiMTExMTExMTExMTExMTExMTExMTExMTExIiw2MzoiMTExMTExMTExMTExMTExMTExMTExMTExIn0sInRpbWVzdGFtcCI6IjE3NzI5Njg0NDM1MzUiLCJ0cmFuc0F1dGgiOmZhbHNlLCJ0dGxWYWx1ZSI6MCwidWlkIjoiODUwMzAzMzAyIiwidXNlclR5cGUiOiJPRkZJQ0lBTCIsIndpZmluZExpbWl0TWFwIjp7fX19.A21F30AC0984CEB66A0A09F2D733E3705CAD6C1C0D51225C0761C1BF945A2BFF'

def get_token():
    """获取 access token"""
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
        else:
            print(f"❌ Token 错误: {d}")
    except Exception as e:
        print(f"❌ Token 异常: {e}")
    return None

def test_macro_indicator(token, indicator_name, code, start, end):
    """测试宏观指标"""
    print(f"\n{'='*60}")
    print(f"测试: {indicator_name}")
    print(f"代码: {code}")
    print(f"{'='*60}")
    
    try:
        # 尝试 cmd_edb（经济数据库）- 宏观数据应该用这个
        print("\n[方法1] cmd_edb")
        r = requests.post(f'{IFIND_BASE}/cmd_edb',
            json={
                'codes': code,
                'startdate': start,
                'enddate': end,
            },
            headers={'Content-Type': 'application/json', 'access_token': token},
            timeout=30)
        d = r.json()
        print(f"  返回: errorcode={d.get('errorcode')}, errmsg={d.get('errmsg')}")
        if d.get('errorcode') == 0:
            tables = d.get('tables', [])
            if tables and len(tables) > 0:
                data = tables[0]
                dates = data.get('time', [])
                values = data.get('table', {})
                if dates and len(dates) > 0:
                    print(f"  ✅ 成功！数据点数: {len(dates)}")
                    print(f"  最新: {dates[-1]}")
                    print(f"  字段: {list(values.keys())}")
                    if values:
                        first_key = list(values.keys())[0]
                        print(f"  最新值: {values[first_key][-1] if values[first_key] else 'N/A'}")
                    return True
            print(f"  ❌ 无数据 (tables={len(tables) if tables else 0})")
        else:
            print(f"  ❌ 错误: {d.get('errmsg')}")
        
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    try:
        # 尝试 cmd_history_quotation（历史行情）
        print("\n[方法2] cmd_history_quotation")
        r = requests.post(f'{IFIND_BASE}/cmd_history_quotation',
            json={
                'codes': code,
                'indicators': 'close',
                'startdate': start,
                'enddate': end,
            },
            headers={'Content-Type': 'application/json', 'access_token': token},
            timeout=30)
        d = r.json()
        print(f"  返回: errorcode={d.get('errorcode')}, errmsg={d.get('errmsg')}")
        if d.get('errorcode') == 0:
            tables = d.get('tables', [])
            if tables and len(tables) > 0:
                data = tables[0]
                dates = data.get('time', [])
                values = data.get('table', {}).get('close', [])
                if dates and len(dates) > 0:
                    print(f"  ✅ 成功！数据点数: {len(dates)}")
                    print(f"  最新: {dates[-1]} = {values[-1] if values else 'N/A'}")
                    return True
            print(f"  ❌ 无数据")
        
    except Exception as e:
        print(f"  ❌ 异常: {e}")
    
    return False

if __name__ == '__main__':
    print("="*60)
    print("iFind 数据权限测试 - 大摩四象限")
    print("="*60)
    
    token = get_token()
    if not token:
        print("\n❌ 无法获取 token，退出")
        exit(1)
    
    print("\n✅ Token 获取成功")
    
    # 测试日期范围（最近3年）
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=365*3)).strftime('%Y-%m-%d')
    print(f"\n测试日期: {start} ~ {end}")
    
    # 测试数据列表
    tests = [
        # 1. 社融结构
        ("社融总量", "M0000545"),  # 社会融资规模存量
        ("居民贷款", "M0017142"),  # 金融机构人民币信贷收支表:住户贷款
        ("企业贷款", "M0017126"),  # 金融机构人民币信贷收支表:非金融企业及机关团体贷款
        
        # 2. 企业债利差
        ("AAA企业债收益率", "M0048501"),  # 中债企业债到期收益率(AAA):3年
        ("AA企业债收益率", "M0048502"),   # 中债企业债到期收益率(AA):3年
        ("3年国债收益率", "M0041650"),    # 中债国债到期收益率:3年
        
        # 3. R007-DR007利差
        ("R007", "M0041652"),  # 银行间质押式回购加权利率:7天
        ("DR007", "M0330183"), # 银行间存款类机构以利率债为质押的7天期回购利率
    ]
    
    results = {}
    for name, code in tests:
        success = test_macro_indicator(token, name, code, start, end)
        results[name] = success
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    success_count = sum(results.values())
    total_count = len(results)
    print(f"\n成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    # 数据可用性判断
    print("\n" + "="*60)
    print("数据可用性判断")
    print("="*60)
    
    # 社融结构
    if results.get("社融总量") and results.get("居民贷款") and results.get("企业贷款"):
        print("✅ 社融结构数据：可用（可计算居民/企业信贷占比）")
    else:
        print("❌ 社融结构数据：不可用")
    
    # 企业债利差
    if results.get("AAA企业债收益率") and results.get("3年国债收益率"):
        print("✅ 企业债利差数据：可用（AAA企业债 - 国债）")
    else:
        print("❌ 企业债利差数据：不可用")
    
    # R007-DR007利差
    if results.get("R007") and results.get("DR007"):
        print("✅ R007-DR007利差数据：可用")
    else:
        print("❌ R007-DR007利差数据：不可用")
