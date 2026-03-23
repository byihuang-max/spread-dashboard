#!/usr/bin/env python3
"""
生成 leader_pool_latest.json — 龙头观察池每日更新
从 GAMT 强势股缓存自动找最新交易日，跑 builder + confirm，输出 JSON 供前端读取。
"""
import json, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path.home() / 'Desktop/gamt-dashboard/env_fit/momentum_stock/_cache'
QUANT_DIR = Path.home() / 'Desktop/quant-backtest/timing_model'
OUTPUT = BASE_DIR / 'leader_pool_latest.json'

sys.path.insert(0, str(QUANT_DIR))
from leader_pool_builder import LeaderPoolBuilder
from leader_confirm_engine import LeaderConfirmEngine


def find_latest_date():
    dates = sorted([f.stem for f in CACHE_DIR.glob('*.json') if f.stem.isdigit() and len(f.stem) == 8], reverse=True)
    return dates[0] if dates else None


def main():
    trade_date = find_latest_date()
    if not trade_date:
        print('ERR: no cache files found')
        return

    builder = LeaderPoolBuilder(cache_dir=str(CACHE_DIR), max_pool_size=12)
    pool_obj = builder.build(trade_date)

    engine = LeaderConfirmEngine(cache_dir=str(CACHE_DIR))
    confirm_obj = engine.confirm(trade_date, pool_obj=pool_obj)

    result = {
        'trade_date': trade_date,
        'pool': pool_obj,
        'confirm': confirm_obj,
    }

    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'OK: {OUTPUT} ({trade_date})')


if __name__ == '__main__':
    main()
