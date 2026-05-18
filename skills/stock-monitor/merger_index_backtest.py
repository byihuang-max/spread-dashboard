#!/usr/bin/env python3
"""
并购等权指数回测

逻辑：
- 入池：公告发布日（publishDate）进入"进行中"状态（方案公布/审核中/已过会/已注册）
- 出池：阶段变为"已完成"或"已终止"
- 等权持有，事件触发调仓
- 对标沪深300

同时计算：入池后 1/3/5 天涨幅，用于异动排名

数据源：
- 通联全量 /tmp/uqer_restructuring_full.json（阶段时间线）
- merger_pool.json（清洗后的池子，确定哪些票是真并购）
- Tushare 日线行情

输出：
- 净值曲线 CSV
- 异动排名 JSON（1/3/5天涨幅 Top）
"""
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Tushare
sys.path.insert(0, os.path.expanduser('~/Desktop/gamt-dashboard/server'))
try:
    from tushare_client import get_daily_data, get_index_daily
except ImportError:
    import tushare as ts
    ts.set_token('8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae')
    pro = ts.pro_api()

    def get_daily_data(ts_code, start_date, end_date):
        return pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

    def get_index_daily(ts_code, start_date, end_date):
        return pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

SCRIPT_DIR = Path(__file__).parent.resolve()
POOL_PATH = SCRIPT_DIR / 'merger_pool.json'
UQER_FULL_PATH = Path('/tmp/uqer_restructuring_full.json')
OUTPUT_DIR = SCRIPT_DIR / 'backtest_output'
OUTPUT_DIR.mkdir(exist_ok=True)

# ── 清洗规则（与 merger_pool.py 一致）──
CLEAN_KEEP_TYPES = {5, 4, 7, 3}
CLEAN_EXCLUDE_TYPES = {8}
MERGER_KEYWORDS = ['收购', '并购', '重组', '控制权', '实控人', '股权转让',
                   '要约', '借壳', '注入', '吸收合并', '战略投资']

# 阶段判断
STAGE_RULES = [
    ('已终止', ['终止', '撤回', '取消']),
    ('已完成', ['过户完成', '实施完毕', '新增股份上市', '交割完成']),
    ('已注册', ['注册生效', '证监会同意注册', '同意注册的批复']),
    ('已过会', ['过会', '审核通过', '审议通过', '获通过']),
    ('审核中', ['已问询', '已回复', '受理', '提交注册']),
    ('方案公布', ['重组报告书', '预案', '草案', '交易报告书']),
    ('筹划中', ['筹划', '停牌', '重大事项']),
]

# "进行中"阶段
ACTIVE_STAGES = {'方案公布', '审核中', '已过会', '已注册'}
EXIT_STAGES = {'已完成', '已终止'}


def determine_stage(text):
    """从文本判断阶段"""
    for stage, keywords in STAGE_RULES:
        if any(kw in text for kw in keywords):
            return stage
    return '筹划中'


def load_and_clean_uqer():
    """加载通联全量数据，清洗，按 ticker 聚合时间线"""
    with open(UQER_FULL_PATH) as f:
        records = json.load(f)

    # 也加载 merger_pool.json 获取已清洗的票列表
    with open(POOL_PATH) as f:
        pool = json.load(f)
    pool_codes = {v.get('code') for v in pool['stocks'].values() if v.get('code')}

    # 按 ticker 聚合
    ticker_events = defaultdict(list)

    for r in records:
        try:
            rtype = int(r.get('restructuringType', 0))
        except (ValueError, TypeError):
            rtype = 0

        # 排除 type=8
        if rtype in CLEAN_EXCLUDE_TYPES:
            continue

        is_major = int(r.get('isMajorRes', 0)) == 1
        ticker = str(r.get('ticker', '') or '')
        name = str(r.get('secShortName', '') or '')
        publish_date = str(r.get('publishDate', '') or '')
        outline = str(r.get('outLine', '') or '') if r.get('outLine') == r.get('outLine') else ''
        is_succeed = r.get('isSucceed')

        if not ticker or not publish_date:
            continue

        # 清洗
        keep = False
        if is_major:
            keep = True
        elif rtype in CLEAN_KEEP_TYPES:
            keep = True
        elif rtype == 1:
            if any(kw in outline for kw in MERGER_KEYWORDS):
                keep = True
        elif rtype == 2:
            keep = True

        if not keep:
            continue

        # 构建 code
        if ticker.startswith(('6', '9')):
            code = f"{ticker}.SH"
        else:
            code = f"{ticker}.SZ"

        # 判断阶段
        stage = '筹划中'
        if is_succeed == 1 or is_succeed == 1.0 or str(is_succeed) == '1' or str(is_succeed) == '1.0':
            stage = '已完成'
        elif is_succeed == 0 or is_succeed == 0.0 or str(is_succeed) == '0' or str(is_succeed) == '0.0':
            stage = '已终止'
        else:
            stage = determine_stage(outline)

        ticker_events[code].append({
            'date': publish_date.replace('-', ''),  # YYYYMMDD
            'stage': stage,
            'name': name,
            'outline': outline[:100],
        })

    # 按日期排序
    for code in ticker_events:
        ticker_events[code].sort(key=lambda x: x['date'])

    print(f"清洗后 {len(ticker_events)} 只票有事件记录")
    return ticker_events


def build_entry_exit(ticker_events):
    """
    为每只票确定入池日和出池日。
    入池：首次进入 ACTIVE_STAGES 的 publishDate
    出池：进入 EXIT_STAGES 的 publishDate（如果有）
    """
    signals = []  # list of {code, name, entry_date, exit_date, exit_reason}

    for code, events in ticker_events.items():
        entry_date = None
        name = events[0]['name'] if events else ''

        for ev in events:
            if ev['stage'] in ACTIVE_STAGES and entry_date is None:
                entry_date = ev['date']
            elif ev['stage'] in EXIT_STAGES and entry_date is not None:
                signals.append({
                    'code': code,
                    'name': name,
                    'entry_date': entry_date,
                    'exit_date': ev['date'],
                    'exit_reason': ev['stage'],
                })
                entry_date = None  # 可能有多轮

        # 还在池中的（未出池）
        if entry_date is not None:
            signals.append({
                'code': code,
                'name': name,
                'entry_date': entry_date,
                'exit_date': None,  # 持有至今
                'exit_reason': 'holding',
            })

    print(f"共 {len(signals)} 个入池信号（{sum(1 for s in signals if s['exit_date'])} 已出池，"
          f"{sum(1 for s in signals if not s['exit_date'])} 仍持有）")
    return signals


def fetch_prices(codes, start_date='20240924', end_date='20260518'):
    """批量拉取日线行情"""
    import tushare as ts
    ts.set_token('8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae')
    pro = ts.pro_api()

    print(f"拉取 {len(codes)} 只票的日线行情...")
    all_prices = {}

    for i, code in enumerate(codes):
        if i % 50 == 0 and i > 0:
            print(f"  进度: {i}/{len(codes)}")
            import time
            time.sleep(0.5)  # 避免频率限制

        try:
            df = pro.daily(ts_code=code, start_date=start_date, end_date=end_date,
                           fields='trade_date,close,pct_chg')
            if df is not None and len(df) > 0:
                # 按日期升序
                df = df.sort_values('trade_date').reset_index(drop=True)
                all_prices[code] = df
        except Exception as e:
            pass  # 跳过拉取失败的

    # 拉沪深300
    print("  拉取沪深300...")
    idx = pro.index_daily(ts_code='000300.SH', start_date=start_date, end_date=end_date,
                          fields='trade_date,close,pct_chg')
    if idx is not None:
        idx = idx.sort_values('trade_date').reset_index(drop=True)
        all_prices['000300.SH'] = idx

    print(f"  成功拉取 {len(all_prices)} 只")
    return all_prices


def run_backtest(signals, prices, start_date='20241001', end_date='20260516'):
    """
    跑等权回测。
    每天确定当天持仓（entry_date <= today < exit_date 的票），等权计算组合收益。
    """
    # 获取交易日历
    if '000300.SH' not in prices:
        print("ERROR: 没有沪深300数据")
        return None, None

    trade_dates = prices['000300.SH']['trade_date'].tolist()
    trade_dates = [d for d in trade_dates if start_date <= d <= end_date]
    trade_dates.sort()

    print(f"回测区间: {trade_dates[0]} ~ {trade_dates[-1]}，共 {len(trade_dates)} 个交易日")

    # 预处理：每只票的日收益率 dict
    price_map = {}  # code -> {trade_date: pct_chg}
    for code, df in prices.items():
        price_map[code] = dict(zip(df['trade_date'], df['pct_chg']))

    # 每天计算组合收益
    nav = 1.0
    nav_series = []
    hs300_nav = 1.0
    hs300_series = []

    daily_holdings = []  # 记录每天持仓数

    for date in trade_dates:
        # 当天持仓：entry_date <= date，且 (exit_date is None 或 exit_date > date)
        holdings = []
        for sig in signals:
            if sig['entry_date'] <= date:
                if sig['exit_date'] is None or sig['exit_date'] > date:
                    holdings.append(sig['code'])

        # 等权日收益
        if holdings:
            returns = []
            for code in holdings:
                pct = price_map.get(code, {}).get(date)
                if pct is not None:
                    returns.append(pct / 100.0)
            if returns:
                avg_ret = sum(returns) / len(returns)
                nav *= (1 + avg_ret)

        # 沪深300
        hs300_ret = price_map.get('000300.SH', {}).get(date)
        if hs300_ret is not None:
            hs300_nav *= (1 + hs300_ret / 100.0)

        nav_series.append({'date': date, 'nav': round(nav, 4), 'holdings': len(holdings)})
        hs300_series.append({'date': date, 'nav': round(hs300_nav, 4)})
        daily_holdings.append(len(holdings))

    print(f"回测完成:")
    print(f"  并购指数终值: {nav:.4f} ({(nav-1)*100:.1f}%)")
    print(f"  沪深300终值: {hs300_nav:.4f} ({(hs300_nav-1)*100:.1f}%)")
    print(f"  超额: {(nav-hs300_nav)*100:.1f}%")
    print(f"  平均持仓数: {sum(daily_holdings)/len(daily_holdings):.0f}")
    print(f"  最大持仓数: {max(daily_holdings)}")

    # 最大回撤
    peak = 0
    max_dd = 0
    for item in nav_series:
        if item['nav'] > peak:
            peak = item['nav']
        dd = (peak - item['nav']) / peak
        if dd > max_dd:
            max_dd = dd
    print(f"  最大回撤: {max_dd*100:.1f}%")

    return nav_series, hs300_series


def calc_reaction(signals, prices):
    """
    计算每只票入池后 1/3/5 天涨幅
    """
    results = []

    for sig in signals:
        code = sig['code']
        entry = sig['entry_date']

        if code not in prices:
            continue

        df = prices[code]
        dates = df['trade_date'].tolist()

        # 找到 entry_date 之后的交易日
        try:
            # entry_date 当天或之后第一个交易日
            start_idx = None
            for i, d in enumerate(dates):
                if d >= entry:
                    start_idx = i
                    break
            if start_idx is None:
                continue

            # 计算 1/3/5 天累计涨幅
            close_series = df['close'].tolist()
            base_close = close_series[start_idx]

            def calc_return(days):
                end_idx = min(start_idx + days, len(close_series) - 1)
                if end_idx <= start_idx:
                    return None
                return (close_series[end_idx] / base_close - 1) * 100

            ret_1d = calc_return(1)
            ret_3d = calc_return(3)
            ret_5d = calc_return(5)

            results.append({
                'code': code,
                'name': sig['name'],
                'entry_date': entry,
                'exit_date': sig['exit_date'],
                'exit_reason': sig['exit_reason'],
                'ret_1d': round(ret_1d, 2) if ret_1d is not None else None,
                'ret_3d': round(ret_3d, 2) if ret_3d is not None else None,
                'ret_5d': round(ret_5d, 2) if ret_5d is not None else None,
            })
        except Exception:
            continue

    # 排序
    results.sort(key=lambda x: x.get('ret_5d') or 0, reverse=True)

    print(f"\n异动排名（入池后涨幅 Top 20）:")
    print(f"{'名称':8s} {'代码':12s} {'入池日':10s} {'1天%':>6s} {'3天%':>6s} {'5天%':>6s}")
    print('-' * 60)
    for r in results[:20]:
        r1 = f"{r['ret_1d']:.1f}" if r['ret_1d'] is not None else '-'
        r3 = f"{r['ret_3d']:.1f}" if r['ret_3d'] is not None else '-'
        r5 = f"{r['ret_5d']:.1f}" if r['ret_5d'] is not None else '-'
        print(f"{r['name']:8s} {r['code']:12s} {r['entry_date']:10s} {r1:>6s} {r3:>6s} {r5:>6s}")

    return results


def main():
    print("=" * 60)
    print("  并购等权指数回测")
    print("=" * 60)

    # 1. 加载通联数据，清洗，建时间线
    print("\n[1] 加载通联全量数据...")
    ticker_events = load_and_clean_uqer()

    # 2. 确定入池/出池信号
    print("\n[2] 构建入池/出池信号...")
    signals = build_entry_exit(ticker_events)

    # 3. 拉取行情
    print("\n[3] 拉取行情数据...")
    all_codes = list(set(s['code'] for s in signals))
    prices = fetch_prices(all_codes)

    # 4. 跑回测
    print("\n[4] 跑回测...")
    nav_series, hs300_series = run_backtest(signals, prices)

    # 5. 计算异动
    print("\n[5] 计算入池后 1/3/5 天涨幅...")
    reactions = calc_reaction(signals, prices)

    # 6. 保存结果
    print("\n[6] 保存结果...")
    if nav_series:
        with open(OUTPUT_DIR / 'merger_index_nav.json', 'w') as f:
            json.dump({'merger': nav_series, 'hs300': hs300_series}, f, ensure_ascii=False)
        print(f"  净值曲线: {OUTPUT_DIR / 'merger_index_nav.json'}")

    with open(OUTPUT_DIR / 'merger_reactions.json', 'w') as f:
        json.dump(reactions, f, ensure_ascii=False, indent=2)
    print(f"  异动排名: {OUTPUT_DIR / 'merger_reactions.json'}")

    # 保存信号列表
    with open(OUTPUT_DIR / 'merger_signals.json', 'w') as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)
    print(f"  信号列表: {OUTPUT_DIR / 'merger_signals.json'}")

    print("\n" + "=" * 60)
    print("  完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
