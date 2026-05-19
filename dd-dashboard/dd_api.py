#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
尽调库 API - Due Diligence Fund Management
============================================
提供尽调基金的 CRUD / 阶段流转 / 评分 / 附件上传接口。
供 refresh_server.py 调用。

数据存储：dd-dashboard/data/funds.json
附件存储：dd-dashboard/uploads/
"""

import json, os, time, uuid, shutil
from datetime import datetime

# ═══ 路径 ═══
DD_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(DD_DIR, 'data')
UPLOADS_DIR = os.path.join(DD_DIR, 'uploads')
FUNDS_PATH = os.path.join(DATA_DIR, 'funds.json')
SEED_PATH = os.path.join(DATA_DIR, 'funds_seed.json')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# ═══ 阶段定义 ═══
STAGES = {
    'initial': {'label': '初步接触', 'order': 0},
    'communicating': {'label': '沟通中', 'order': 1},
    'diligenced': {'label': '已尽调', 'order': 2},
    'approved': {'label': '已入库', 'order': 3},
    'invested': {'label': '已投资', 'order': 4},
    'rejected': {'label': '已否决', 'order': 5},
}

# ═══ 数据加载/保存 ═══
_lock = __import__('threading').Lock()


def _load_funds():
    """加载基金数据。如果 funds.json 不存在，从 seed 初始化。"""
    if not os.path.exists(FUNDS_PATH):
        if os.path.exists(SEED_PATH):
            with open(SEED_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            funds = data.get('funds', data) if isinstance(data, dict) else data
            _save_funds(funds)
            return funds
        return []
    with open(FUNDS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('funds', data) if isinstance(data, dict) else data


def _save_funds(funds):
    """保存基金数据。"""
    with open(FUNDS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'funds': funds}, f, ensure_ascii=False, indent=2)


def _find_fund(funds, fund_id):
    """按 ID 查找基金，返回 (index, fund) 或 (-1, None)。"""
    for i, f in enumerate(funds):
        if f.get('id') == fund_id:
            return i, f
    return -1, None


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ═══ 查询 API ═══

def get_all():
    """获取全部基金列表。"""
    with _lock:
        return _load_funds()


def get_by_id(fund_id):
    """获取单个基金详情。"""
    with _lock:
        funds = _load_funds()
        _, fund = _find_fund(funds, fund_id)
        return fund


def get_stats():
    """获取统计信息。"""
    with _lock:
        funds = _load_funds()
        by_stage = {}
        for key, info in STAGES.items():
            count = sum(1 for f in funds if f.get('stage') == key)
            by_stage[key] = {'label': info['label'], 'count': count}
        return {
            'total': len(funds),
            'byStage': by_stage,
        }


# ═══ 创建/编辑 API ═══

def create_fund(data, created_by='system'):
    """创建新基金记录。"""
    with _lock:
        funds = _load_funds()
        fund_id = data.get('id') or f"fund-{uuid.uuid4().hex[:8]}"
        # 检查重复
        if _find_fund(funds, fund_id)[0] >= 0:
            return False, '基金ID已存在'

        fund = {
            'id': fund_id,
            'company': data.get('company', {}),
            'dueDiligence': data.get('dueDiligence', {}),
            'keyPersonnel': data.get('keyPersonnel', []),
            'strategies': data.get('strategies', []),
            'highlights': data.get('highlights', []),
            'risks': data.get('risks', []),
            'fees': data.get('fees', {}),
            'tags': data.get('tags', []),
            'attachments': data.get('attachments', []),
            'communications': data.get('communications', []),
            'benchmarkProducts': data.get('benchmarkProducts', []),
            'reviewChecklist': data.get('reviewChecklist', {}),
            'reminders': data.get('reminders', []),
            'stage': data.get('stage', 'initial'),
            'ddTimeline': data.get('ddTimeline', []),
            'rating': data.get('rating', {}),
            'stageHistory': [{
                'from': None,
                'to': data.get('stage', 'initial'),
                'by': created_by,
                'at': _now(),
                'note': '创建记录',
            }],
            'auditLog': [{
                'action': 'create',
                'by': created_by,
                'at': _now(),
            }],
            'createdAt': _now(),
            'updatedAt': _now(),
        }
        funds.append(fund)
        _save_funds(funds)
        return True, fund


def update_fund(fund_id, data, updated_by='system'):
    """更新基金信息（部分更新）。"""
    with _lock:
        funds = _load_funds()
        idx, fund = _find_fund(funds, fund_id)
        if idx < 0:
            return False, '基金不存在'

        # 可更新的字段
        updatable = [
            'company', 'dueDiligence', 'keyPersonnel', 'strategies',
            'highlights', 'risks', 'fees', 'tags', 'attachments',
            'communications', 'benchmarkProducts', 'reviewChecklist',
            'reminders', 'ddTimeline',
        ]
        for key in updatable:
            if key in data:
                fund[key] = data[key]

        fund['updatedAt'] = _now()
        fund.setdefault('auditLog', []).append({
            'action': 'update',
            'by': updated_by,
            'at': _now(),
            'fields': [k for k in data if k in updatable],
        })
        funds[idx] = fund
        _save_funds(funds)
        return True, fund


def delete_fund(fund_id, deleted_by='system'):
    """删除基金记录。"""
    with _lock:
        funds = _load_funds()
        idx, fund = _find_fund(funds, fund_id)
        if idx < 0:
            return False, '基金不存在'
        funds.pop(idx)
        _save_funds(funds)
        return True, f'已删除: {fund.get("company", {}).get("shortName", fund_id)}'


# ═══ 阶段流转 API ═══

def change_stage(fund_id, new_stage, changed_by='system', note=''):
    """变更基金阶段。"""
    if new_stage not in STAGES:
        return False, f'无效阶段: {new_stage}'
    with _lock:
        funds = _load_funds()
        idx, fund = _find_fund(funds, fund_id)
        if idx < 0:
            return False, '基金不存在'

        old_stage = fund.get('stage', 'initial')
        if old_stage == new_stage:
            return False, '阶段未变化'

        fund['stage'] = new_stage
        fund['updatedAt'] = _now()
        fund.setdefault('stageHistory', []).append({
            'from': old_stage,
            'to': new_stage,
            'by': changed_by,
            'at': _now(),
            'note': note,
        })
        fund.setdefault('auditLog', []).append({
            'action': 'stage_change',
            'by': changed_by,
            'at': _now(),
            'detail': f'{STAGES[old_stage]["label"]} → {STAGES[new_stage]["label"]}',
        })
        funds[idx] = fund
        _save_funds(funds)
        return True, fund


# ═══ 评分 API ═══

def rate_fund(fund_id, rating_data, rated_by='system'):
    """给基金评分。"""
    with _lock:
        funds = _load_funds()
        idx, fund = _find_fund(funds, fund_id)
        if idx < 0:
            return False, '基金不存在'

        rating = fund.get('rating', {})
        dims = ['strategyClarity', 'performanceStability', 'teamStability',
                'riskControl', 'scaleCapacityFit']
        scores = []
        for dim in dims:
            if dim in rating_data:
                rating[dim] = rating_data[dim]
            if rating.get(dim) is not None:
                scores.append(rating[dim])

        if scores:
            avg = sum(scores) / len(scores)
            rating['overall'] = round(avg, 1)
            if avg >= 4.0:
                rating['grade'] = 'A'
            elif avg >= 3.0:
                rating['grade'] = 'B'
            elif avg >= 2.0:
                rating['grade'] = 'C'
            else:
                rating['grade'] = 'D'

        rating['ratedBy'] = rated_by
        rating['ratedAt'] = _now()
        fund['rating'] = rating
        fund['updatedAt'] = _now()
        fund.setdefault('auditLog', []).append({
            'action': 'rate',
            'by': rated_by,
            'at': _now(),
        })
        funds[idx] = fund
        _save_funds(funds)
        return True, fund


# ═══ 附件 API ═══

def save_upload(filename, file_data):
    """保存上传文件，返回相对路径。"""
    # 安全文件名
    safe_name = f"{int(time.time())}_{filename.replace('/', '_').replace('..', '')}"
    filepath = os.path.join(UPLOADS_DIR, safe_name)
    with open(filepath, 'wb') as f:
        f.write(file_data)
    return f"uploads/{safe_name}"


def add_attachment(fund_id, filename, filepath, uploaded_by='system'):
    """给基金添加附件记录。"""
    with _lock:
        funds = _load_funds()
        idx, fund = _find_fund(funds, fund_id)
        if idx < 0:
            return False, '基金不存在'

        attachment = {
            'name': filename,
            'path': filepath,
            'uploadedBy': uploaded_by,
            'uploadedAt': _now(),
        }
        fund.setdefault('attachments', []).append(attachment)
        fund['updatedAt'] = _now()
        funds[idx] = fund
        _save_funds(funds)
        return True, attachment
