#!/usr/bin/env python3
"""
生成 leader_pool_latest.json — 龙头观察池每日更新
从 GAMT 强势股缓存自动找最新交易日，跑 builder + confirm，输出 JSON 供前端读取。
"""
import json, os, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# 用真实用户目录（兼容 HOME 被代理工具重定向的场景）
_REAL_HOME = Path('/Users/apple') if Path('/Users/apple').exists() else Path('/home/ubuntu')
CACHE_DIR = next(
    (p for p in [
        _REAL_HOME / 'Desktop/gamt-dashboard/env_fit/momentum_stock/_cache',
        Path('/home/ubuntu/gamt-dashboard/env_fit/momentum_stock/_cache'),
    ] if p.exists()),
    Path('/home/ubuntu/gamt-dashboard/env_fit/momentum_stock/_cache')
)
QUANT_DIR = next(
    (p for p in [
        _REAL_HOME / 'Desktop/quant-backtest/timing_model',
        Path('/home/ubuntu/quant-backtest/timing_model'),
    ] if p.exists()),
    Path('/home/ubuntu/quant-backtest/timing_model')
)
OUTPUT = BASE_DIR / 'leader_pool_latest.json'

sys.path.insert(0, str(QUANT_DIR))
from leader_pool_builder import LeaderPoolBuilder
from leader_confirm_engine import LeaderConfirmEngine

# momentum_stock 目录（含 momentum_data.py：交易日历 + 缓存拉取）
MOMENTUM_DIR = CACHE_DIR.parent
sys.path.insert(0, str(MOMENTUM_DIR))


def _latest_cache_date():
    dates = sorted([f.stem for f in CACHE_DIR.glob('*.json') if f.stem.isdigit() and len(f.stem) == 8], reverse=True)
    return dates[0] if dates else None


def resolve_trade_date():
    """确定龙头池应使用的交易日，并保证当天缓存就绪。

    方案2（治本）：不再静默取"最新缓存文件"。先问交易日历今天该是哪个交易日，
    若当天缓存缺失则强制拉一次；拉不到（数据未就绪）直接报错退出，
    绝不静默回退到昨天的缓存。
    """
    try:
        import momentum_data as md
    except Exception as e:
        # 拿不到数据模块时，退回旧行为但明确告警
        print(f'WARN: cannot import momentum_data ({e}); fallback to latest cache')
        return _latest_cache_date()

    # 交易日历里最近的交易日（节假日/周末会是上一个交易日，属正常）
    try:
        expected = md.get_trade_dates(n_days=1)[-1]
    except Exception as e:
        print(f'WARN: trade_cal failed ({e}); fallback to latest cache')
        return _latest_cache_date()

    cache_file = CACHE_DIR / f'{expected}.json'
    if not cache_file.exists():
        # 当天缓存还没生成 → 主动拉一次。allow_empty=False：空结果抛异常，不落空缓存
        print(f'cache for {expected} missing, fetching...')
        md.fetch_day_cached(expected, allow_empty=False)  # 失败则抛 ValueError，main 捕获后非零退出

    return expected


def main():
    trade_date = resolve_trade_date()
    if not trade_date:
        print('ERR: no cache files found')
        sys.exit(1)

    latest = _latest_cache_date()
    if latest and trade_date != latest:
        print(f'WARN: expected trade_date {trade_date} but latest cache is {latest}')

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
