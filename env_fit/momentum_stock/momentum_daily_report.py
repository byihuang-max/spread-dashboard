#!/usr/bin/env python3
"""强势股环境日报生成器 v1.2 — 飞书纯文字版"""
import requests, json, os, sys
from collections import Counter

TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
URL = 'https://api.tushare.pro'
BASE = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    with open(os.path.join(BASE, path)) as f:
        return json.load(f)


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

    name_to_code = {v['industry_l2']: v['industry_l2_code'] for v in stocks.values()}
    code_to_pct, code_to_amt = fetch_sw_daily(dt)
    if not code_to_pct:
        return f'ERROR: 无法拉取 {dt} 行业指数数据'

    chains = analyze_chains(chain_map, name_to_code, code_to_pct, code_to_amt)

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
    L.append(f'- 涨停 {today["up_count"]}家（分位{up_pct}%）')
    if up_ind:
        L.append(f'  方向: {up_ind}')
    if up_str or up_amt:
        picks = '  '.join(filter(None, [f'强度: {up_str}' if up_str else '', f'额度: {up_amt}' if up_amt else '']))
        L.append(f'  {picks}')
    L.append(f'- 跌停 {today["down_count"]}家（分位{down_pct}%）')
    if down_ind:
        L.append(f'  方向: {down_ind}')
    if down_str or down_amt:
        picks = '  '.join(filter(None, [f'强度: {down_str}' if down_str else '', f'额度: {down_amt}' if down_amt else '']))
        L.append(f'  {picks}')
    L.append(f'- 晋级率 {today["promotion_rate"]:.1f}%（分位{promo_pct}%）')
    L.append(f'- 炸板率 {today["zha_rate"]:.0f}%')
    if zha_ind:
        L.append(f'  方向: {zha_ind}')
    L.append(f'- 封单轧差 {ss_today["seal_spread"]:+.1f}亿（1Y分位{ss_today["spread_pct_1y"]*100:.0f}%）')
    L.append(f'- 断板 {today["duanban_count"]}/{today["lianban_count"]+today["duanban_count"]}')
    L.append('')

    # 二、百亿涨停
    names = today.get('mega_cap_names', '')
    if names:
        L.append('二、百亿涨停')
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
        narrative = warn_latest['narrative'].replace('🟡', '⚠').replace('🔴', '🚨').replace('🟢', '✓')
        L.append(f'{CN_NUMS[sec_idx]}、异常信号')
        sec_idx += 1
        tail = narrative.split('：')[-1] if '：' in narrative else narrative
        L.append(f'- {tail}')
        L.append('')

    # 四、产业链共振
    L.append(f'{CN_NUMS[sec_idx]}、产业链共振')
    sec_idx += 1
    L.append('')
    nums = ['①', '②', '③']
    for i, (cn, strength, res, lavg, ldata, best) in enumerate(chains[:3]):
        L.append(f'{nums[i]} {cn} {strength:+.2f}% {res}')
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

    # 五、结论
    chg_up = today['up_count'] - yesterday['up_count']
    chg_down = today['down_count'] - yesterday['down_count']
    L.append(f'{CN_NUMS[sec_idx]}、结论')
    L.append(f'- 涨停{chg_up:+d} 跌停{chg_down:+d}')
    if top_chain:
        L.append(f'- 最强链: {top_chain[0]}（{top_chain[2]}）')
    L.append(f'- 状态: {yesterday["cycle_label"]} → {today["cycle_label"]}')

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
