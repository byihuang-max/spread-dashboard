#!/usr/bin/env python3
"""
测试 Tushare 能否获取大摩四象限所需数据
1. 社融结构（居民/企业信贷占比）
2. 企业债利差（AAA/AA企业债 - 国债）
3. R007-DR007利差
"""
import requests
import pandas as pd
import json

# Tushare 私有地址
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'

def ts_api(api_name, fields='', **kwargs):
    """调用 Tushare API"""
    params = {k: v for k, v in kwargs.items() if v is not None}
    body = {'api_name': api_name, 'token': TUSHARE_TOKEN, 'params': params}
    if fields:
        body['fields'] = fields
    
    try:
        r = requests.post(TUSHARE_URL, json=body, timeout=30)
        j = r.json()
        if j.get('code') != 0:
            return None, j.get('msg', 'Unknown error')
        data = j.get('data', {})
        df = pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
        return df, None
    except Exception as e:
        return None, str(e)

def test_api(name, api_name, **kwargs):
    """测试单个API"""
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"API: {api_name}")
    print(f"参数: {kwargs}")
    print(f"{'='*60}")
    
    df, error = ts_api(api_name, **kwargs)
    
    if error:
        print(f"❌ 错误: {error}")
        return False
    
    if df is None or df.empty:
        print(f"❌ 无数据")
        return False
    
    print(f"✅ 成功！数据行数: {len(df)}")
    print(f"字段: {list(df.columns)}")
    print(f"\n前3行:")
    print(df.head(3).to_string())
    return True

if __name__ == '__main__':
    print("="*60)
    print("Tushare 数据权限测试 - 大摩四象限")
    print("="*60)
    
    results = {}
    
    # 1. 社融数据
    print("\n" + "="*60)
    print("【1. 社融结构数据】")
    print("="*60)
    
    # cn_m 表（货币供应量）
    results['cn_m'] = test_api(
        "货币供应量（M0/M1/M2）",
        "cn_m",
        start_m="202301",
        end_m="202603"
    )
    
    # 社会融资规模
    results['cn_shrzgm'] = test_api(
        "社会融资规模",
        "cn_shrzgm",
        start_m="202301",
        end_m="202603"
    )
    
    # 2. 利率数据
    print("\n" + "="*60)
    print("【2. 利率数据】")
    print("="*60)
    
    # Shibor
    results['shibor'] = test_api(
        "Shibor利率",
        "shibor",
        start_date="20260101",
        end_date="20260315"
    )
    
    # 国债收益率
    results['yc_cb'] = test_api(
        "国债收益率曲线",
        "yc_cb",
        start_date="20260101",
        end_date="20260315"
    )
    
    # 3. 企业债数据
    print("\n" + "="*60)
    print("【3. 企业债数据】")
    print("="*60)
    
    # 企业债收益率
    results['cn_bond_yield'] = test_api(
        "企业债收益率",
        "cn_bond_yield",
        start_date="20260101",
        end_date="20260315"
    )
    
    # 信用利差
    results['cn_bond_spread'] = test_api(
        "信用利差",
        "cn_bond_spread",
        start_date="20260101",
        end_date="20260315"
    )
    
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
    if results.get('cn_m') or results.get('cn_shrzgm'):
        print("✅ 社融结构数据：可用")
    else:
        print("❌ 社融结构数据：不可用")
    
    # 利率数据
    if results.get('shibor') and results.get('yc_cb'):
        print("✅ R007-DR007利差数据：可用（Shibor表有R007和DR007）")
    else:
        print("❌ R007-DR007利差数据：不可用")
    
    # 企业债利差
    if results.get('cn_bond_yield') or results.get('cn_bond_spread'):
        print("✅ 企业债利差数据：可用")
    else:
        print("❌ 企业债利差数据：不可用")
