#!/usr/bin/env python3
"""强势股环境日报生成器 v1.5 — 飞书纯文字版（+边际变化+ETF行情）"""
import requests, json, os, sys, shutil
from collections import Counter

TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
URL = 'https://api.tushare.pro'
BASE = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    with open(os.path.join(BASE, path)) as f:
        return json.load(f)


# ===== 辅助：3日趋势标注 =====
def trend3(daily, field, n=3):
    """取最近 n 日某字段，返回 (values, arrow, desc)"""
    vals = [d[field] for d in daily[-n:] if field in d]
    if len(vals) < 2:
        return vals, '', ''
    if all(vals[i] < vals[i+1] for i in range(len(vals)-1)):
        arrow, desc = '↑', f'连升{len(vals)}日'
    elif all(vals[i] > vals[i+1] for i in range(len(vals)-1)):
        arrow, desc = '↓', f'连降{len(vals)}日'
    else:
        arrow, desc = '━', '震荡'
    return vals, arrow, desc


# ===== 辅助：crowding 数据读取 =====
def load_crowding():
    """读 crowding.json，失败返回 None"""
    try:
        path = os.path.join(BASE, '..', '..', 'micro_flow', 'crowding', 'crowding.json')
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ===== 辅助：最强链连续性 =====
def chain_streak(dt, daily_dates, current_top):
    """统计最强链连续天数（读 chain_rank_history）"""
    if not os.path.exists(CHAIN_HIST_DIR):
        return 1
    streak = 1
    for d in reversed(daily_dates[:-1][-5:]):  # 往前最多查5天
        path = os.path.join(CHAIN_HIST_DIR, f'{d}.json')
        if not os.path.exists(path):
            break
        with open(path) as f:
            snap = json.load(f)
        top = snap.get('ranking', [[None]])[0][0] if snap.get('ranking') else None
        if top == current_top:
            streak += 1
        else:
            break
    return streak


# ===== 龙头池历史快照（用于 delta 对比）=====
LEADER_HIST_DIR = os.path.join(BASE, 'leader_pool_history')


def save_leader_snapshot(dt, pool_items, rec_leader, amt_leader):
    """保存当日龙头池快照，供下一交易日做 delta 对比"""
    os.makedirs(LEADER_HIST_DIR, exist_ok=True)
    snapshot = {
        'trade_date': dt,
        'pool': [p.get('name', '') for p in pool_items if isinstance(p, dict)],
        'pool_detail': pool_items,
        'rec_leader': rec_leader.get('name', '') if rec_leader else '',
        'amt_leader': amt_leader.get('name', '') if amt_leader else '',
    }
    with open(os.path.join(LEADER_HIST_DIR, f'{dt}.json'), 'w') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def read_timing_exposure(dt):
    """读取择时模块的收益优先线敞口（base_exposure，α=1.75，均仓~30%）。
    返回 dict 或 None。数据源 timing-research/data/live_exposure_nav.json。
    """
    candidates = [
        os.path.join(BASE, '..', '..', 'timing-research', 'data', 'live_exposure_nav.json'),
        '/home/ubuntu/gamt-dashboard/timing-research/data/live_exposure_nav.json',
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        return None
    try:
        with open(path) as f:
            d = json.load(f)
        summary = d.get('summary', {})
        # 收益优先线 = base
        line = next((L for L in summary.get('lines', []) if L.get('key') == 'base'), None)
        if not line:
            return None
        return {
            'signal_date': summary.get('latest_signal_date'),
            'execute_date': summary.get('latest_execute_date'),
            'regime': summary.get('latest_regime'),
            'exposure': line.get('latest_exposure'),      # 今日目标敞口(0~1)
            'total_return': line.get('total_return'),
            'max_drawdown': line.get('max_drawdown'),
            'avg_exposure': line.get('avg_exposure'),
        }
    except Exception:
        return None


def load_prev_leader_snapshot(dt, daily_dates):
    """加载前一交易日的龙头池快照，返回 dict 或 None"""
    if not os.path.exists(LEADER_HIST_DIR):
        return None
    # 找 dt 的前一个交易日
    prev_dt = None
    for i, d in enumerate(daily_dates):
        if d == dt and i > 0:
            prev_dt = daily_dates[i - 1]
            break
    if not prev_dt:
        return None
    path = os.path.join(LEADER_HIST_DIR, f'{prev_dt}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


# ===== 产业链排名历史（用于 delta 对比）=====
CHAIN_HIST_DIR = os.path.join(BASE, 'chain_rank_history')


def save_chain_snapshot(dt, chains):
    """保存当日产业链排名快照"""
    os.makedirs(CHAIN_HIST_DIR, exist_ok=True)
    snapshot = {
        'trade_date': dt,
        'ranking': [(cn, strength, res) for cn, strength, res, *_ in chains],
    }
    with open(os.path.join(CHAIN_HIST_DIR, f'{dt}.json'), 'w') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def load_prev_chain_snapshot(dt, daily_dates):
    """加载前一交易日的产业链排名快照"""
    if not os.path.exists(CHAIN_HIST_DIR):
        return None
    prev_dt = None
    for i, d in enumerate(daily_dates):
        if d == dt and i > 0:
            prev_dt = daily_dates[i - 1]
            break
    if not prev_dt:
        return None
    path = os.path.join(CHAIN_HIST_DIR, f'{prev_dt}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def promotion_direction(dt, dt_yesterday, top_n=4):
    """提取晋级方向、1进2方向、首板方向"""
    cache_file = os.path.join(BASE, '_cache', f'{dt}.json')
    cache_y_file = os.path.join(BASE, '_cache', f'{dt_yesterday}.json')
    promo_dir = ''
    one_to_two_dir = ''
    shouban_dir = ''
    shouban_focus = ''  # 集中/分散

    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
        ups = [u for u in cache.get('U', []) if u.get('close', 0) > 0 and abs(u.get('pct_chg', 0)) < 50]

        # 晋级方向：今天连板票（limit_times > 1）的行业分布
        lianban = [u for u in ups if u.get('limit_times', 1) > 1]
        if lianban:
            cnt = Counter(u.get('industry', '未知') for u in lianban)
            top = cnt.most_common(top_n)
            promo_dir = '  '.join(f'{ind}{n}' for ind, n in top)

        # 首板方向
        shouban = [u for u in ups if u.get('limit_times', 1) == 1]
        if shouban:
            cnt_sb = Counter(u.get('industry', '未知') for u in shouban)
            top_sb = cnt_sb.most_common(top_n)
            shouban_dir = '  '.join(f'{ind}{n}' for ind, n in top_sb)
            # 集中度判断：Top3 占比
            top3_pct = sum(x[1] for x in top_sb[:3]) / len(shouban) * 100
            if top3_pct >= 40:
                shouban_focus = '集中'
            elif top3_pct >= 25:
                shouban_focus = '偏集中'
            else:
                shouban_focus = '分散'

        # 1进2方向
        if os.path.exists(cache_y_file):
            with open(cache_y_file) as f:
                cache_y = json.load(f)
            shouban_y = set(u['ts_code'] for u in cache_y.get('U', [])
                           if u.get('limit_times', 1) == 1 and u.get('close', 0) > 0)
            success = [u for u in ups if u['ts_code'] in shouban_y and u.get('limit_times', 1) == 2]
            if success:
                cnt2 = Counter(u.get('industry', '未知') for u in success)
                top2 = cnt2.most_common(top_n)
                one_to_two_dir = '  '.join(f'{ind}{n}' for ind, n in top2)

    return promo_dir, one_to_two_dir, shouban_dir, shouban_focus


def limit_industry_summary(dt, limit_type, top_n=4):
    """从缓存读涨/跌停明细，返回行业分布摘要字符串，如 '电力5 电子4 化工3'"""
    cache_file = os.path.join(BASE, '_cache', f'{dt}.json')
    if not os.path.exists(cache_file):
        # 缓存不存在，尝试从 momentum_data 拉取并缓存
        try:
            from momentum_data import fetch_day_cached
            fetch_day_cached(dt, allow_empty=True)
        except Exception:
            pass
    if not os.path.exists(cache_file):
        return ''
    with open(cache_file) as f:
        data = json.load(f)
    items = data.get(limit_type, [])
    if not items:
        return ''
    cnt = Counter(item.get('industry', '未知') for item in items)
    top = cnt.most_common(top_n)
    return '  '.join(f'{ind}{n}' for ind, n in top)


def limit_highlight_picks(dt, limit_type):
    """从缓存提取辨识度最强（最高板/跌幅最深）和成交额最强的票，返回 (strength_pick, amount_pick) 字符串"""
    cache_file = os.path.join(BASE, '_cache', f'{dt}.json')
    if not os.path.exists(cache_file):
        return '', ''
    with open(cache_file) as f:
        data = json.load(f)
    items = data.get(limit_type, [])
    # 过滤脏数据（close=0 或 pct_chg 异常的 Tushare 脏记录）
    items = [x for x in items if x.get('close', 0) > 0 and abs(x.get('pct_chg', 0)) < 50]
    if not items:
        return '', ''

    # 辨识度最强：涨停看最高连板，跌停看跌幅最深
    if limit_type == 'U':
        strength = max(items, key=lambda x: (x.get('limit_times') or 1, x.get('amount') or 0))
        ht = strength.get('limit_times') or 1
        s_tag = f"{strength['name']}({strength.get('industry','')}) {ht}板"
    else:
        strength = min(items, key=lambda x: x.get('pct_chg') or 0)
        s_tag = f"{strength['name']}({strength.get('industry','')}) {strength.get('pct_chg',0):+.1f}%"

    # 成交额最强
    amount_top = max(items, key=lambda x: x.get('amount') or 0)
    amt_yi = (amount_top.get('amount') or 0) / 1e8
    a_tag = f"{amount_top['name']}({amount_top.get('industry','')}) {amt_yi:.1f}亿"

    # 如果是同一只票就合并
    if strength.get('ts_code') == amount_top.get('ts_code'):
        if limit_type == 'U':
            return f"{strength['name']}({strength.get('industry','')}) {ht}板/{amt_yi:.1f}亿", ''
        else:
            return f"{strength['name']}({strength.get('industry','')}) {strength.get('pct_chg',0):+.1f}%/{amt_yi:.1f}亿", ''

    return s_tag, a_tag


def pct_rank(daily, field, val):
    vals = sorted([d.get(field, 0) for d in daily if d.get(field) is not None])
    if not vals:
        return 0
    return round(sum(1 for v in vals if v <= val) / len(vals) * 100)


def fetch_sw_daily(trade_date):
    resp = requests.post(URL, json={
        'api_name': 'sw_daily', 'token': TOKEN,
        'params': {'start_date': trade_date, 'end_date': trade_date},
        'fields': 'ts_code,trade_date,close,pct_change,vol,amount'
    }, timeout=20, proxies={'http': None, 'https': None})
    data = resp.json()
    if data.get('code') != 0:
        return {}, {}
    cols = data['data']['fields']
    pct_map, amt_map = {}, {}
    for row in data['data']['items']:
        d = dict(zip(cols, row))
        pct_map[d['ts_code']] = d['pct_change'] or 0
        amt_map[d['ts_code']] = d['amount'] or 0
    return pct_map, amt_map


def fetch_etf_daily(trade_date):
    """拉取 ETF 日行情 + 名字，返回 [{code6, name, pct_chg, amount_yi}] """
    import time as _time
    # 拉行情
    resp = requests.post(URL, json={
        'api_name': 'fund_daily', 'token': TOKEN,
        'params': {'trade_date': trade_date},
        'fields': 'ts_code,trade_date,close,pct_chg,amount'
    }, timeout=20, proxies={'http': None, 'https': None})
    data = resp.json()
    if data.get('code') != 0:
        return []
    cols = data['data']['fields']
    daily_map = {}
    for row in data['data']['items']:
        d = dict(zip(cols, row))
        daily_map[d['ts_code'][:6]] = {
            'pct_chg': d.get('pct_chg') or 0,
            'amount_yi': (d.get('amount') or 0) / 10000,
        }

    _time.sleep(0.3)

    # 拉名字
    resp2 = requests.post(URL, json={
        'api_name': 'fund_basic', 'token': TOKEN,
        'params': {'market': 'E', 'status': 'L'},
        'fields': 'ts_code,name'
    }, timeout=20, proxies={'http': None, 'https': None})
    data2 = resp2.json()
    name_map = {}
    if data2.get('code') == 0:
        for row in data2['data']['items']:
            d = dict(zip(data2['data']['fields'], row))
            name_map[d['ts_code'][:6]] = d.get('name', '')

    # 合并
    result = []
    for code6, info in daily_map.items():
        name = name_map.get(code6, '')
        if 'ETF' not in name:
            continue
        result.append({
            'code': code6,
            'name': name,
            'pct_chg': info['pct_chg'],
            'amount_yi': info['amount_yi'],
        })
    return result


def analyze_chains(chain_map, name_to_code, code_to_pct, code_to_amt):
    results = []
    for cn, cd in chain_map['chains'].items():
        layer_data = {}
        for pos in ['上游', '中游', '下游']:
            inds = cd.get(pos, [])
            vals = []
            for ind in inds:
                code = name_to_code.get(ind)
                if code and code in code_to_pct:
                    vals.append((ind, code_to_pct[code], code_to_amt.get(code, 0)))
            layer_data[pos] = vals

        all_v = [v for vs in layer_data.values() for v in vs]
        if not all_v:
            continue
        tot = sum(v[2] for v in all_v) or 1
        strength = sum(v[1] * v[2] / tot for v in all_v)

        layer_avg = {}
        for pos in ['上游', '中游', '下游']:
            vs = layer_data[pos]
            layer_avg[pos] = sum(v[1] for v in vs) / len(vs) if vs else None

        active = {k: v for k, v in layer_avg.items() if v is not None}
        pos_cnt = sum(1 for v in active.values() if v > 0.3)
        neg_cnt = sum(1 for v in active.values() if v < -0.3)
        n = len(active)

        if pos_cnt == n and n >= 2:       res = '全链共振'
        elif neg_cnt == n and n >= 2:     res = '全链下跌'
        elif pos_cnt > 0 and neg_cnt > 0: res = '链内分化'
        elif pos_cnt > 0:                res = '偏强'
        elif neg_cnt > 0:                res = '偏弱'
        else:                            res = '震荡'

        best = None
        for src, dst in cd.get('edges', []):
            sc, dc = name_to_code.get(src), name_to_code.get(dst)
            if sc and dc and sc in code_to_pct and dc in code_to_pct:
                s = code_to_pct[sc] + code_to_pct[dc]
                if best is None or s > best[4]:
                    best = (src, code_to_pct[sc], dst, code_to_pct[dc], s)

        results.append((cn, strength, res, layer_avg, layer_data, best))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def generate_report(trade_date=None):
    sent = load_json('momentum_sentiment.json')
    ss = load_json('limit_index/seal_spread/seal_spread.json')
    warn = load_json('momentum_warning.json')
    chain_map = load_json('sector_chain_map_l2.json')
    stocks = load_json('_cache/stock_industry_l2.json')

    today = sent['daily'][-1]
    yesterday = sent['daily'][-2]
    ss_today = ss['daily'][-1]
    warn_latest = warn['latest']
    dt = today['date']
    daily = sent['daily']
    crowding = load_crowding()  # crowding 共振数据（可能为 None）

    name_to_code = {v['industry_l2']: v['industry_l2_code'] for v in stocks.values()}
    code_to_pct, code_to_amt = fetch_sw_daily(dt)
    if not code_to_pct:
        return f'ERROR: 无法拉取 {dt} 行业指数数据'

    chains = analyze_chains(chain_map, name_to_code, code_to_pct, code_to_amt)

    # ===== 昨日数据（用于 delta）=====
    daily_dates = [d['date'] for d in daily]
    ss_yesterday = ss['daily'][-2] if len(ss['daily']) >= 2 else None
    prev_chain = load_prev_chain_snapshot(dt, daily_dates)
    prev_leader = load_prev_leader_snapshot(dt, daily_dates)

    # 保存今日快照（供明天 delta 用）
    save_chain_snapshot(dt, chains)

    up_pct = pct_rank(daily, 'up_count', today['up_count'])
    down_pct = pct_rank(daily, 'down_count', today['down_count'])
    promo_pct = pct_rank(daily, 'promotion_rate', today['promotion_rate'])

    L = []

    # 标题 + 摘要
    L.append(f'强势股环境日报 | {dt[:4]}-{dt[4:6]}-{dt[6:8]}')
    L.append('')
    # 一句话摘要
    top_chain = chains[0] if chains else None
    summary = f'{today["cycle_label"]}期，高度{yesterday["max_height"]}→{today["max_height"]}板'
    if top_chain:
        summary += f'，{top_chain[0]}{top_chain[2]}'
    L.append(summary)
    L.append('')

    # 一、核心指标
    up_ind = limit_industry_summary(dt, 'U')
    down_ind = limit_industry_summary(dt, 'D')
    zha_ind = limit_industry_summary(dt, 'Z')
    up_str, up_amt = limit_highlight_picks(dt, 'U')
    down_str, down_amt = limit_highlight_picks(dt, 'D')
    L.append('一、核心指标')
    L.append('整体市场强势方向与温度')
    # 晋级/1进2/首板 方向
    promo_dir, one2two_dir, shouban_dir, shouban_focus = promotion_direction(dt, yesterday['date'])
    # 涨停
    up_vals, up_arrow, up_desc = trend3(daily, 'up_count')
    up_trend = f' {up_arrow}{up_desc}({"→".join(str(int(v)) for v in up_vals)})' if up_desc else ''
    L.append(f'- 涨停 {today["up_count"]}家（分位{up_pct}%）{up_trend}')
    if up_ind:
        L.append(f'  方向: {up_ind}')
    if up_str or up_amt:
        picks = '  '.join(filter(None, [f'强度: {up_str}' if up_str else '', f'额度: {up_amt}' if up_amt else '']))
        L.append(f'  {picks}')
    # 首板（次级）
    L.append(f'  >> 首板 {today["shouban_count"]}家（{shouban_focus}）')
    if shouban_dir:
        L.append(f'     首板方向: {shouban_dir}')
    # 晋级率（次级）
    pr_vals, pr_arrow, pr_desc = trend3(daily, 'promotion_rate')
    pr_trend = f' {pr_arrow}{pr_desc}({"→".join(f"{v:.0f}" for v in pr_vals)})' if pr_desc else ''
    L.append(f'  >> 晋级率 {today["promotion_rate"]:.1f}%（分位{promo_pct}%）{pr_trend}| 断板 {today["duanban_count"]}/{today["lianban_count"]+today["duanban_count"]}')
    if promo_dir:
        L.append(f'     晋级方向: {promo_dir}')
    # 1进2（次级）
    L.append(f'  >> 1进2 {today.get("rate_1to2", 0):.0f}%')
    if one2two_dir:
        L.append(f'     1进2方向: {one2two_dir}')
    # 炸板率（次级）
    L.append(f'  >> 炸板率 {today["zha_rate"]:.0f}%')
    if zha_ind:
        L.append(f'     炸板方向: {zha_ind}')
    # 跌停（下挂：方向、强度/额度）
    L.append(f'- 跌停 {today["down_count"]}家（分位{down_pct}%）')
    if down_ind:
        L.append(f'  方向: {down_ind}')
    if down_str or down_amt:
        picks = '  '.join(filter(None, [f'强度: {down_str}' if down_str else '', f'额度: {down_amt}' if down_amt else '']))
        L.append(f'  {picks}')
    # 封单轧差（独立指标）
    L.append(f'- 封单轧差 {ss_today["seal_spread"]:+.1f}亿（1Y分位{ss_today["spread_pct_1y"]*100:.0f}%）')
    L.append('')

    # 二、百亿涨停
    names = today.get('mega_cap_names', '')
    if names:
        L.append('二、百亿涨停')
        L.append('市场核心聚焦方向')
        name_list = [n.replace('[', '(').replace(']', ')') for n in names.split('|')]
        for j in range(0, len(name_list), 3):
            chunk = name_list[j:j+3]
            L.append('- ' + ' · '.join(chunk))
        L.append('')

    # 动态编号
    CN_NUMS = ['一', '二', '三', '四', '五', '六', '七']
    sec_idx = 2  # 下一个是"三"

    # 三、异常信号
    if warn_latest.get('signal_triggered'):
        narrative = warn_latest['narrative'].replace('🟡', '⚠').replace('🔴', '').replace('🟢', '')
        L.append(f'{CN_NUMS[sec_idx]}、异常信号')
        sec_idx += 1
        tail = narrative.split('：')[-1] if '：' in narrative else narrative
        L.append(f'- {tail}')
        L.append('')

    # 四、产业链共振
    L.append(f'{CN_NUMS[sec_idx]}、产业链共振')
    L.append('成交额加权强度 + 上下游传导验证')
    sec_idx += 1

    # 排名变化提示 + 最强链连续性
    if prev_chain:
        prev_ranking = [r[0] for r in prev_chain.get('ranking', [])]
        today_ranking = [cn for cn, *_ in chains]
        prev_top = prev_ranking[0] if prev_ranking else ''
        today_top = today_ranking[0] if today_ranking else ''
        if prev_top and today_top and prev_top != today_top:
            L.append(f'- 最强链切换: {prev_top} → {today_top}')
        elif prev_top and today_top and prev_top == today_top:
            streak = chain_streak(dt, daily_dates, today_top)
            streak_str = f'连续{streak}日' if streak > 1 else '今日'
            L.append(f'- 最强链{streak_str}: {today_top}')

    # crowding 三维交叉验证（全市场量价最强方向 + 资金加速方向）
    if crowding:
        vp_list = crowding.get('vp_matrix', [])
        accel = crowding.get('accel_rank', {})
        # 全市场量价最强的1-2个一级行业（vp_matrix 已按 rank 排序）
        vp_top = [r for r in vp_list if r.get('state') == '量价齐升'][:2]
        if vp_top:
            vp_str = ' / '.join(f"{r['name']}({r['state']}{',' + r['risk'] if r.get('risk') else ''})" for r in vp_top)
            L.append(f'- 全市场量价: {vp_str}')
        # 资金5日加速涌入方向（week_up 前2）
        week_up = accel.get('week_up', [])[:2]
        if week_up:
            au_str = ' / '.join(f"{r['name']}(+{r['chg_5d']*100:.1f}pct)" for r in week_up)
            L.append(f'- 资金5日加速: {au_str}')

    L.append('')
    nums = ['', '', '']
    # 构建昨日排名 lookup
    prev_rank_map = {}
    if prev_chain:
        for idx, r in enumerate(prev_chain.get('ranking', [])):
            prev_rank_map[r[0]] = idx + 1

    for i, (cn, strength, res, lavg, ldata, best) in enumerate(chains[:3]):
        # 排名变化标注
        rank_delta = ''
        if cn in prev_rank_map:
            prev_pos = prev_rank_map[cn]
            cur_pos = i + 1
            if prev_pos > cur_pos:
                rank_delta = f' ▲{prev_pos - cur_pos}'
            elif prev_pos < cur_pos:
                rank_delta = f' ▼{cur_pos - prev_pos}'
        elif prev_chain:
            rank_delta = ' NEW'
        L.append(f'{nums[i]} {cn} {strength:+.2f}% {res}{rank_delta}')
        cols_order = ['上游', '中游', '下游']
        active = [c for c in cols_order if ldata.get(c)]
        layer_parts = []
        for pos in active:
            vs = sorted(ldata[pos], key=lambda x: abs(x[1]), reverse=True)[:2]
            avg = lavg[pos]
            tag = '▲' if avg > 0.3 else ('▼' if avg < -0.3 else '━')
            ns = ' '.join(f'{v[0].replace("Ⅱ","")}{v[1]:+.1f}%' for v in vs)
            layer_parts.append(f'{pos}{tag} {ns}')
        L.append('- ' + ' → '.join(layer_parts))
        if best:
            src_n = best[0].replace('Ⅱ', '')
            dst_n = best[2].replace('Ⅱ', '')
            L.append(f'- 传导: {src_n}{best[1]:+.1f}% → {dst_n}{best[3]:+.1f}%')
        L.append('')

    rest = [f'{cn}{res}' for cn, _, res, _, _, _ in chains[3:]]
    L.append(f'其余: {" | ".join(rest)}')
    L.append('')

    # ===== 构建行业→链映射 =====
    industry_to_chain = {}
    for cn, cdata in chain_map.get('chains', chain_map).items():
        if not isinstance(cdata, dict):
            continue
        for pos in ['上游', '中游', '下游']:
            for ind in cdata.get(pos, []):
                # 去掉Ⅱ后缀做模糊匹配
                industry_to_chain[ind] = cn
                industry_to_chain[ind.replace('Ⅱ', '')] = cn

    def _ind_to_chain(industry):
        """行业名 → 所属链名，模糊匹配"""
        if not industry:
            return ''
        if industry in industry_to_chain:
            return industry_to_chain[industry]
        # 模糊：去掉Ⅱ、去掉"Ⅱ"
        clean = industry.replace('Ⅱ', '')
        if clean in industry_to_chain:
            return industry_to_chain[clean]
        # 部分匹配
        for k, v in industry_to_chain.items():
            if k in industry or industry in k:
                return v
        return ''

    # ===== 百亿涨停行业统计 =====
    mega_industries = []
    if names:
        import re as _re
        for entry in names.split('|'):
            m = _re.search(r'[\[（(]([^）)\]]+)[\]）)]', entry)
            if m:
                mega_industries.append(m.group(1))
    mega_chain_count = Counter(_ind_to_chain(ind) for ind in mega_industries if _ind_to_chain(ind))

    # ===== 龙头观察池 =====
    leader_path = os.path.join(BASE, '..', '..', 'timing-research', 'leader_pool_latest.json')
    if not os.path.exists(leader_path):
        for alt in ['/home/ubuntu/gamt-dashboard/timing-research/leader_pool_latest.json']:
            if os.path.exists(alt):
                leader_path = alt
                break

    pool_items = []
    rec_leader = {}
    amt_leader = {}
    pool_chain_count = Counter()

    if os.path.exists(leader_path):
        try:
            with open(leader_path) as f:
                lp = json.load(f)
            if lp.get('trade_date') == dt:
                confirm = lp.get('confirm', {})
                rec_leader = confirm.get('recognition_leader', {})
                amt_leader = confirm.get('amount_leader', {})
                pool_data = lp.get('pool', {})
                if isinstance(pool_data, dict):
                    pool_list = [v for v in pool_data.values() if isinstance(v, list)]
                    pool_items = pool_list[0] if pool_list else []
                else:
                    pool_items = pool_data
                # 龙头池行业→链统计
                for p in pool_items:
                    if isinstance(p, dict):
                        ch = _ind_to_chain(p.get('industry', ''))
                        if ch:
                            pool_chain_count[ch] += 1
        except Exception:
            pass

    if pool_items:
        # 保存今日龙头池快照（供明天 delta 用）
        save_leader_snapshot(dt, pool_items, rec_leader, amt_leader)

        L.append(f'{CN_NUMS[sec_idx]}、龙头观察池')
        L.append('高度 + 成交聚焦的核心票筛选')
        sec_idx += 1
        # 辨识度龙头（+换人提示）
        if rec_leader:
            rec_chain = _ind_to_chain(rec_leader.get('industry', ''))
            chain_tag = f' [{rec_chain}]' if rec_chain else ''
            rec_delta = ''
            if prev_leader and prev_leader.get('rec_leader'):
                prev_rec = prev_leader['rec_leader']
                if prev_rec != rec_leader.get('name', ''):
                    rec_delta = f'（昨{prev_rec}）'
            ht = rec_leader.get('limit_times', '')
            L.append(f'- 辨识度龙头: {rec_leader.get("name","")}({rec_leader.get("industry","")}) <<{ht}板>>{chain_tag}{rec_delta}')
        # 成交额龙头（+成交额+板数+换人提示）
        if amt_leader and amt_leader.get('ts_code') != rec_leader.get('ts_code'):
            amt_chain = _ind_to_chain(amt_leader.get('industry', ''))
            chain_tag = f' [{amt_chain}]' if amt_chain else ''
            amt_delta = ''
            if prev_leader and prev_leader.get('amt_leader'):
                prev_amt = prev_leader['amt_leader']
                if prev_amt != amt_leader.get('name', ''):
                    amt_delta = f'（昨{prev_amt}）'
            amt_yi = (amt_leader.get('amount') or 0) / 1e8
            amt_ht = amt_leader.get('limit_times', '')
            L.append(f'- 成交额龙头: {amt_leader.get("name","")}({amt_leader.get("industry","")}) {amt_yi:.1f}亿 {amt_ht}板{chain_tag}{amt_delta}')

        # 池内变动
        today_pool_names = set(p.get('name', '') for p in pool_items if isinstance(p, dict))
        if prev_leader:
            prev_pool_names = set(prev_leader.get('pool', []))
            new_in = today_pool_names - prev_pool_names
            dropped = prev_pool_names - today_pool_names
            if new_in or dropped:
                parts = []
                if new_in:
                    parts.append(f'新进{len(new_in)}只: {" ".join(sorted(new_in))}')
                if dropped:
                    parts.append(f'退出{len(dropped)}只: {" ".join(sorted(dropped))}')
                L.append(f'- 变动: {" / ".join(parts)}')

        # 池内列表（带行业后缀）
        pool_names = [f'{p["name"]}({p.get("industry","")})' for p in pool_items[:10] if isinstance(p, dict)]
        L.append(f'- 池内{len(pool_items)}只: {" / ".join(pool_names)}{"..." if len(pool_items) > 10 else ""}')
        L.append('')

    # ===== ETF 关注建议（第五）=====
    # 逻辑：确定主攻方向 → 从全市场 ETF 中按当天实际涨幅动态筛选最相关的
    all_etf_daily = fetch_etf_daily(dt)

    if all_etf_daily:
        # 确定推荐方向：主攻链 + 龙头池主方向
        rec_chain_names = []
        if top_chain and top_chain[1] > 0:
            rec_chain_names.append(top_chain[0])
        if len(chains) > 1 and chains[1][1] > 0:
            rec_chain_names.append(chains[1][0])
        if pool_chain_count:
            pool_top = pool_chain_count.most_common(1)[0][0]
            if pool_top not in rec_chain_names:
                rec_chain_names.append(pool_top)

        # 从推荐链中提取最强二级行业
        rec_industries = []
        for cn, strength, res, lavg, ldata, best in chains:
            if cn not in rec_chain_names:
                continue
            for pos in ['上游', '中游', '下游']:
                for ind, pct, amt in ldata.get(pos, []):
                    if pct > 0.3:
                        rec_industries.append((ind, pct, cn))
        rec_industries.sort(key=lambda x: x[1], reverse=True)

        # 为每个方向构建搜索关键词
        _ind_keywords = {
            '半导体': ['半导体', '芯片', '人工智能', 'AI', '集成电路', '科创'],
            '元件': ['电子', '元件'],
            '电子化学品': ['电子', '化工', '材料'],
            '计算机设备': ['计算机', '信息', '科技', '人工智能', 'AI'],
            '软件开发': ['软件', '计算机', '信息', '云计算', '大数据'],
            '通信设备': ['通信', '5G'],
            '消费电子': ['消费电子', '电子'],
            '航天装备': ['军工', '国防', '航天'],
            '军工电子': ['军工', '国防'],
            '自动化设备': ['机器人', '自动化', '智能制造', '工业母机'],
            '专用设备': ['机器人', '工业母机', '高端装备', '智能制造'],
            '通用设备': ['机械', '装备', '制造'],
            '金属新材料': ['有色', '稀土', '新材料'],
            '能源金属': ['锂电', '新能源', '有色', '稀土'],
            '光伏设备': ['光伏', '新能源', '太阳能'],
            '电池': ['电池', '锂电', '新能源', '储能'],
            '风电设备': ['风电', '新能源'],
            '房地产开发': ['房地产', '地产'],
            '汽车零部件': ['汽车', '智能驾驶', '新能源车'],
            '乘用车': ['汽车', '智能驾驶', '新能源车'],
        }

        # 按方向动态匹配 ETF
        chain_pick_count = Counter()
        seen_codes = set()
        etf_lines = []

        for ind, pct, cn in rec_industries:
            if chain_pick_count[cn] >= 2:
                continue
            # 获取搜索关键词
            clean_ind = ind.replace('Ⅱ', '')
            keywords = _ind_keywords.get(clean_ind, [clean_ind])

            # 从全市场 ETF 中搜索匹配的，按涨幅排序
            matched = []
            for etf in all_etf_daily:
                if etf['code'] in seen_codes:
                    continue
                if etf['pct_chg'] <= 0:
                    continue
                if etf['amount_yi'] < 1:
                    continue  # 过滤成交额太小的
                name = etf['name']
                if any(kw in name for kw in keywords):
                    matched.append(etf)

            matched.sort(key=lambda x: x['pct_chg'], reverse=True)

            if matched:
                # 取涨幅最高的 2 只
                picks = matched[:2]
                for p in picks:
                    seen_codes.add(p['code'])
                etf_strs = [f'{p["name"][:10]}({p["code"]}) {p["pct_chg"]:+.1f}% {p["amount_yi"]:.1f}亿' for p in picks]
                etf_lines.append(f'- [{cn}] {clean_ind} {pct:+.1f}%')
                etf_lines.append(f'  etf: {" / ".join(etf_strs)}')
                chain_pick_count[cn] += 1

        if etf_lines:
            L.append(f'{CN_NUMS[sec_idx]}、ETF 关注')
            L.append('综合产业链强度、百亿涨停与龙头方向')
            sec_idx += 1
            for line in etf_lines:
                L.append(line)
            L.append('')

    # ===== 结论（第六）=====
    L.append(f'{CN_NUMS[sec_idx]}、结论')

    # 状态变化 + 解释（解释用 (()) 标记，渲染为灰色小字）
    y_label = yesterday['cycle_label']
    t_label = today['cycle_label']
    state_reason = ''
    if t_label == '加速' and y_label != '加速':
        state_reason = f'高度{yesterday["max_height"]}→{today["max_height"]}板，涨停{today["up_count"]}家分位{up_pct}%'
    elif t_label == '退潮':
        state_reason = f'高度{yesterday["max_height"]}→{today["max_height"]}板回落，断板{today["duanban_count"]}家'
    elif t_label == '冰点':
        state_reason = f'涨停{today["up_count"]}家分位{up_pct}%，晋级率{today["promotion_rate"]:.0f}%'
    elif t_label == '震荡':
        state_reason = f'高度{today["max_height"]}板，方向分散'
    elif t_label == '修复':
        state_reason = f'涨停回升至{today["up_count"]}家，晋级率{today["promotion_rate"]:.0f}%'
    if state_reason:
        L.append(f'- 状态: {y_label} → {t_label} (({state_reason}))')
    else:
        L.append(f'- 状态: {y_label} → {t_label}')

    # 主攻方向（整行标红，括号内解释用灰色小字）
    if top_chain:
        top_chain_name = top_chain[0]
        mega_in_top = mega_chain_count.get(top_chain_name, 0)
        pool_in_top = pool_chain_count.get(top_chain_name, 0)

        signals = []
        signals.append(f'链强度: {top_chain_name}({top_chain[2]})')
        if mega_in_top > 0:
            signals.append(f'百亿涨停{mega_in_top}只落在{top_chain_name}')
        if pool_in_top > 0:
            signals.append(f'龙头池{pool_in_top}只指向{top_chain_name}')

        if mega_in_top > 0 or pool_in_top > 0:
            confirm_count = (1 if mega_in_top > 0 else 0) + (1 if pool_in_top > 0 else 0) + 1
            if confirm_count >= 3:
                L.append(f'- <<主攻: {top_chain_name}（三重共振）>> (({" + ".join(signals)}))')
            elif confirm_count == 2:
                L.append(f'- <<主攻: {top_chain_name}>> (({" + ".join(signals)}))')
        else:
            L.append(f'- 最强链: {top_chain_name}（{top_chain[2]}），龙头池/百亿未集中验证')

        if pool_chain_count:
            pool_top_chain = pool_chain_count.most_common(1)[0]
            if pool_top_chain[0] != top_chain_name and pool_top_chain[1] >= 2:
                L.append(f'- <<注意: 龙头池偏向{pool_top_chain[0]}({pool_top_chain[1]}只)，与最强链{top_chain_name}分化>>')

    # crowding 资金共识 + 情绪
    if crowding:
        tf = crowding.get('three_flows', {})
        tf_consensus = tf.get('consensus', '')
        if tf_consensus:
            flows = tf.get('details', {})
            flow_parts = []
            for k, v in flows.items():
                dir_cn = '流入' if v.get('direction') == 'inflow' else '流出'
                flow_parts.append(f"{v.get('name','')}{dir_cn}")
            L.append(f'- 资金共识: {tf_consensus} (({" / ".join(flow_parts)}))')

        breadth = crowding.get('breadth_signals', [])
        if breadth:
            # 取最相关的1-2条（优先含"拥挤"或"情绪"的）
            priority = [s for s in breadth if '情绪' in s or '拥挤顶' in s or '加速' in s]
            show = priority[:2] if priority else breadth[:2]
            for s in show:
                L.append(f'- 市场: {s}')

    # 状态画像（cycle_label → 该状态的客观特征，描述而非指令）
    STATE_PROFILE = {
        '加速': '高度抬升、晋级率走高，资金向高标扩散，赚钱效应强',
        '震荡': '方向分散无主线，高低切频繁，连板梯队不稳',
        '退潮': '高度回落、断板增多，赚钱效应收缩，资金离场',
        '修复': '涨停回升、晋级率企稳，但梯队持续性尚未验证',
        '冰点': '涨停极少、情绪低迷，无明显赚钱效应',
    }
    profile = STATE_PROFILE.get(t_label, '')
    if profile:
        L.append(f'- {t_label}期特征: {profile}')

    # 择时敞口（收益优先线 α=1.75，均仓~30%，给满仓散户的减仓提示）
    timing = read_timing_exposure(dt)
    if timing and timing.get('exposure') is not None:
        exp_pct = timing['exposure'] * 100
        avg = timing.get('avg_exposure')
        avg_txt = f'，长期均仓约{avg*100:.0f}%' if avg else ''
        L.append(f'- <<强势股建议仓位: {exp_pct:.0f}%>>{avg_txt} ((此为强势股这一篮子的持仓，非全仓；中证2000择时·收益优先线))')

    return '\n'.join(L)


def main():
    trade_date = sys.argv[1] if len(sys.argv) > 1 else None
    report = generate_report(trade_date)
    print(report)
    out_path = os.path.join(BASE, 'daily_report_latest.txt')
    with open(out_path, 'w') as f:
        f.write(report)
    print(f'\n已保存到 {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
