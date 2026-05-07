#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选 - 产品池管理 API
================================
提供产品池的提交/验证/审核/下架接口，供 refresh_server.py 调用。

工作流：
  团队提交(pending) → 火富牛API验证(verified/failed) → 管理员审核(approved/rejected)

权限：
  - 提交：tier >= 2（团队成员）
  - 审核/下架/恢复：admin only
"""

import hashlib, time, json, os, sys, threading
import requests

# 确保能 import config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from config import (
    APP_ID, APP_KEY, BASE_URL, POOL_PATH, GROUP_COLORS,
    _load_pool, _save_pool, add_to_pool, update_pool_item, remove_from_pool, get_all_pool,
)


def _api_sign(params):
    """火富牛 API 签名"""
    sorted_keys = sorted(k for k in params if k != 'sign')
    s = '&'.join(f'{k}={params[k]}' for k in sorted_keys) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()


def _api_get(path, params, timeout=15):
    """通用 GET 请求"""
    params['app_id'] = APP_ID
    params['tm'] = str(int(time.time()))
    params['sign'] = _api_sign(params)
    try:
        r = requests.get(f'{BASE_URL}{path}', params=params, timeout=timeout, verify=False)
        data = r.json()
        if data.get('error_code') != 0:
            return None, data.get('msg', str(data))
        return data.get('data'), None
    except Exception as e:
        return None, str(e)


def verify_product(reg_code, source="team"):
    """
    调火富牛 API 验证产品是否存在，尝试拉最近净值。
    返回 (ok, product_info_or_error)
    """
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    path = '/company/price' if source == 'team' else '/price'
    data, err = _api_get(path, {
        'reg_code': reg_code,
        'start_date': start_date,
        'end_date': end_date,
        'order_by': 'price_date',
        'order': '0',
    })

    if data and len(data) > 0:
        # 取产品名（火富牛返回的 fund_name 字段）
        fund_name = data[0].get('fund_name', '') or data[0].get('name', '')
        latest_date = data[0].get('price_date', '')
        latest_nav = data[0].get('cumulative_nav', '')
        return True, {
            'name': fund_name,
            'latest_date': latest_date,
            'latest_nav': latest_nav,
            'nav_count': len(data),
            'source': source,
        }

    # team 接口失败，fallback 到 platform
    if source == 'team':
        return verify_product(reg_code, source='platform')

    return False, err or '未找到该产品净值数据'


def submit_product(reg_code, group, detail, reason, submitted_by, name=None, benchmark=None, benchmark_name=None):
    """
    团队成员提交产品到沙盒池。
    1. 写入 pending 状态（产品名由提交者填写，必填）
    2. 异步调火富牛验证净值可用性
    3. 验证通过 → verified，失败 → failed
    返回 (ok, msg)
    """
    reg_code = reg_code.strip().upper()
    name = (name or '').strip()
    if not reg_code:
        return False, 'reg_code 不能为空'
    if not name:
        return False, '产品名称不能为空'
    if not group:
        return False, '策略分组不能为空'
    if not reason or len(reason.strip()) < 5:
        return False, '推荐理由至少5个字'

    # 检查是否已存在（任何状态）
    pool = _load_pool()
    for p in pool.get('products', []):
        if p.get('code') == reg_code:
            st = p.get('status')
            if st == 'approved':
                return False, f'{reg_code} 已在正式池中'
            elif st in ('pending', 'verified'):
                return False, f'{reg_code} 已提交，等待审核中'
            elif st == 'rejected':
                # 被拒绝过的可以重新提交：更新信息，重置为 pending
                p.update({
                    'name': name,
                    'group': group,
                    'detail': detail or '',
                    'reason': reason.strip(),
                    'submitted_by': submitted_by,
                    'submitted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'pending',
                    'verified': False,
                    'verify_info': None,
                    'review_note': '',
                    'reviewed_by': None,
                    'reviewed_at': None,
                })
                if benchmark:
                    p['benchmark'] = benchmark
                    p['benchmark_name'] = benchmark_name or ''
                _save_pool(pool)
                # 异步验证
                _async_verify(reg_code)
                return True, f'{reg_code} 已重新提交，正在验证...'
            elif st == 'removed':
                # 下架的也可以重新提交
                p.update({
                    'name': name,
                    'group': group,
                    'detail': detail or '',
                    'reason': reason.strip(),
                    'submitted_by': submitted_by,
                    'submitted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'pending',
                    'verified': False,
                    'verify_info': None,
                    'review_note': '',
                    'reviewed_by': None,
                    'reviewed_at': None,
                })
                if benchmark:
                    p['benchmark'] = benchmark
                    p['benchmark_name'] = benchmark_name or ''
                _save_pool(pool)
                _async_verify(reg_code)
                return True, f'{reg_code} 已重新提交，正在验证...'

    # 新产品
    color = GROUP_COLORS.get(group, '#666666')
    item = {
        'code': reg_code,
        'name': name,  # 团队提交时必填，不再依赖火富牛回填
        'group': group,
        'detail': detail or '',
        'color': color,
        'status': 'pending',
        'seed': False,
        'reason': reason.strip(),
        'submitted_by': submitted_by,
        'submitted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'verified': False,
        'verify_info': None,
        'reviewed_by': None,
        'reviewed_at': None,
        'review_note': '',
    }
    if benchmark:
        item['benchmark'] = benchmark
        item['benchmark_name'] = benchmark_name or ''

    pool['products'].append(item)
    _save_pool(pool)

    # 异步验证
    _async_verify(reg_code)

    return True, f'{reg_code} 已提交，正在验证...'


def _async_verify(reg_code):
    """异步线程验证产品"""
    def _do():
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ok, info = verify_product(reg_code)
        pool = _load_pool()
        for p in pool.get('products', []):
            if p.get('code') == reg_code and p.get('status') == 'pending':
                if ok:
                    p['status'] = 'verified'
                    p['verified'] = True
                    p['verify_info'] = info
                else:
                    p['status'] = 'failed'
                    p['verified'] = False
                    p['verify_info'] = {'error': info}
                _save_pool(pool)
                break

    t = threading.Thread(target=_do, daemon=True)
    t.start()


def review_product(reg_code, action, reviewed_by, review_note=''):
    """
    管理员审核产品。
    action: 'approve' | 'reject'
    """
    reg_code = reg_code.strip().upper()
    pool = _load_pool()
    for p in pool.get('products', []):
        if p.get('code') == reg_code:
            current = p.get('status')
            if current not in ('verified', 'failed', 'pending', 'rejected'):
                return False, f'当前状态 {current} 不可审核'

            if action == 'approve':
                p['status'] = 'approved'
            elif action == 'reject':
                p['status'] = 'rejected'
            else:
                return False, f'未知操作: {action}'

            p['reviewed_by'] = reviewed_by
            p['reviewed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            p['review_note'] = review_note or ''
            _save_pool(pool)
            return True, f'{reg_code} 已{"通过" if action == "approve" else "拒绝"}'

    return False, f'未找到 {reg_code}'


def remove_product(reg_code, removed_by):
    """管理员下架产品（种子产品不可下架）"""
    reg_code = reg_code.strip().upper()
    pool = _load_pool()
    for p in pool.get('products', []):
        if p.get('code') == reg_code:
            if p.get('seed'):
                return False, '种子产品不可下架'
            p['status'] = 'removed'
            p['reviewed_by'] = removed_by
            p['reviewed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            _save_pool(pool)
            return True, f'{reg_code} 已下架'
    return False, f'未找到 {reg_code}'


def restore_product(reg_code, restored_by):
    """管理员恢复已下架/已拒绝的产品到 approved"""
    reg_code = reg_code.strip().upper()
    pool = _load_pool()
    for p in pool.get('products', []):
        if p.get('code') == reg_code:
            if p.get('status') not in ('removed', 'rejected'):
                return False, f'当前状态 {p.get("status")} 不需要恢复'
            p['status'] = 'approved'
            p['reviewed_by'] = restored_by
            p['reviewed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            _save_pool(pool)
            return True, f'{reg_code} 已恢复上架'
    return False, f'未找到 {reg_code}'


def retry_verify(reg_code):
    """重新验证失败的产品"""
    reg_code = reg_code.strip().upper()
    pool = _load_pool()
    for p in pool.get('products', []):
        if p.get('code') == reg_code and p.get('status') == 'failed':
            p['status'] = 'pending'
            p['verified'] = False
            p['verify_info'] = None
            _save_pool(pool)
            _async_verify(reg_code)
            return True, f'{reg_code} 正在重新验证...'
    return False, f'未找到或状态不是 failed'


def get_pool_stats():
    """获取产品池统计"""
    pool = _load_pool()
    products = pool.get('products', [])
    stats = {
        'total': len(products),
        'approved': sum(1 for p in products if p.get('status') == 'approved'),
        'pending': sum(1 for p in products if p.get('status') in ('pending', 'verified')),
        'rejected': sum(1 for p in products if p.get('status') == 'rejected'),
        'failed': sum(1 for p in products if p.get('status') == 'failed'),
        'removed': sum(1 for p in products if p.get('status') == 'removed'),
        'seed': sum(1 for p in products if p.get('seed')),
    }
    return stats
