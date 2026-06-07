#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子库存储层
============
factors.json 是单一数据源。行业→个股索引靠 linked_industry + linked_tickers。
所有读写走这里，前端和 CLI 共用。
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path

BASE = Path("/Users/apple/Desktop/gamt-dashboard/factor-forge")
STORE = BASE / "data" / "factors.json"


def _load() -> list:
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save(factors: list):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(factors, ensure_ascii=False, indent=2), encoding="utf-8")


def add_factors(new_factors: list) -> dict:
    """追加因子，按 factor_id 去重。返回 {added, skipped}。"""
    existing = _load()
    seen = {f.get("factor_id") for f in existing}
    added = 0
    for f in new_factors:
        if f.get("factor_id") in seen:
            continue
        existing.append(f)
        seen.add(f.get("factor_id"))
        added += 1
    _save(existing)
    return {"added": added, "skipped": len(new_factors) - added, "total": len(existing)}


def update_factor(factor_id: str, patch: dict) -> bool:
    factors = _load()
    for f in factors:
        if f.get("factor_id") == factor_id:
            f.update(patch)
            f["updated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            _save(factors)
            return True
    return False


def delete_factor(factor_id: str) -> bool:
    factors = _load()
    n = len(factors)
    factors = [f for f in factors if f.get("factor_id") != factor_id]
    if len(factors) < n:
        _save(factors)
        return True
    return False


def all_factors() -> list:
    return _load()


def by_industry() -> dict:
    """按行业聚合，行业→因子列表（含其个股）。"""
    idx = {}
    for f in _load():
        ind = f.get("linked_industry") or "未分类"
        idx.setdefault(ind, []).append(f)
    return idx


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        fs = _load()
        print(f"因子总数: {len(fs)}")
        for ind, items in by_industry().items():
            print(f"  {ind}: {len(items)} 条")
