#!/usr/bin/env python3
"""
模块二：品种趋势扫描（CSV增量模式）
从 fut_daily.csv 读取数据，计算每品种趋势评分和信号
输出：mod2_trend_scan.json + mod2_trend_scan.csv（含公式列）
"""

import json, os, csv, math
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'mod2_trend_scan.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod2_trend_scan.csv')

SECTORS = {
    '黑色系':['RB','HC','I','J','JM','SF','SM','SS'],
    '有色金属':['CU','AL','ZN','PB','NI','SN','BC','AO','SI'],
    '贵金属':['AU','AG'],
    '能源化工':['SC','FU','LU','BU','MA','EG','EB','TA','PP','L','V','PF','SA','FG','UR','PX','SP','RU','NR','BR','PG'],
    '农产品':['A','B','M','Y','P','OI','RM','CF','CY','SR','C','CS','JD','LH','AP','CJ','PK','WH','RI','RR'],
}
SYMBOL_SECTOR = {}
for sec, syms in SECTORS.items():
    for s in syms:
        SYMBOL_SECTOR[s] = sec

INDUSTRY_DRIVERS = {
    'RB':'地产开工·基建投资·钢厂利润','HC':'制造业需求·汽车家电·钢厂利润',
    'I':'铁水产量·港口库存·澳巴发运','J':'焦化利润·环保限产·钢厂补库',
    'JM':'煤矿安检·进口蒙煤·焦化需求','CU':'全球制造业PMI·铜矿供给·新能源需求',
    'AL':'电解铝产能·电力成本·地产竣工','ZN':'矿端供给·镀锌需求·冶炼利润',
    'NI':'不锈钢需求·印尼镍矿·新能源电池','AU':'美元/实际利率·央行购金·避险情绪',
    'AG':'光伏需求·工业属性·金银比','SC':'OPEC+产量·地缘政治·全球需求',
    'MA':'煤制甲醇成本·MTO开工·进口到港','EG':'聚酯开工·煤化工投产·库存周期',
    'TA':'聚酯需求·PX成本·加工费','PP':'石化投产·塑编需求·PDH利润',
    'L':'石化检修·农膜需求·进口到港','SA':'光伏玻璃需求·纯碱产能·库存',
    'FG':'地产竣工·光伏组件·产线冷修','UR':'农业需求季节性·出口政策·煤头成本',
    'M':'美豆种植/天气·生猪存栏·压榨利润','Y':'棕榈油替代·食用需求·进口大豆到港',
    'P':'东南亚产量·生柴政策·库存','OI':'菜籽进口·食用需求·豆棕价差',
    'CF':'新疆产量·纺织需求·抛储政策','SR':'甘蔗产量·进口配额·替代糖浆',
    'C':'饲料需求·深加工·临储拍卖','LH':'能繁母猪存栏·出栏节奏·冻品库存',
    'SP':'海外浆厂检修·造纸需求·港口库存','RU':'泰国割胶季·轮胎开工·合成胶价差',
    'FU':'炼厂检修·船燃需求·裂解价差','BU':'道路施工季节性·炼厂排产·库存',
    'SI':'光伏多晶硅·有机硅需求·产能投放','AO':'电解铝产能·铝土矿进口·氧化铝产能',
}

def log(msg):
    print(msg, flush=True)


def load_fut_csv():
    if not os.path.exists(FUT_CSV):
        log(f"ERROR: {FUT_CSV} 不存在，先跑 commodity_data.py")
        return None
    series = defaultdict(list)
    with open(FUT_CSV, 'r', newline='', encoding='gb18030') as f:
        for row in csv.DictReader(f):
            sym = row.get('symbol', '')
            close = row.get('close', '')
            if not sym or not close:
                continue
            series[sym].append({
                'date': row['trade_date'],
                'close': float(close),
                'pre_close': float(row['pre_close']) if row.get('pre_close') else None,
                'vol': float(row['vol']) if row.get('vol') else 0,
                'amount': float(row['amount']) if row.get('amount') else 0,
            })
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


def compute_scan(series):
    results = []

    for sym, data in series.items():
        if len(data) < 3:
            continue

        closes = [d['close'] for d in data]
        amounts = [d['amount'] for d in data]

        # 涨跌幅序列
        pcts = []
        for i in range(1, len(closes)):
            pcts.append((closes[i] / closes[i-1] - 1) * 100 if closes[i-1] > 0 else 0)

        # 日均成交额（MA20）
        n20 = min(len(amounts), 20)
        avg_daily_amt = sum(amounts[-n20:]) / n20 if n20 else 0
        if avg_daily_amt <= 500:
            continue

        # chg_20d
        n_avail = min(len(closes), 21)
        chg_20d = (closes[-1] / closes[-n_avail] - 1) * 100 if closes[-n_avail] > 0 else 0

        # MA20 斜率 → trend_dir
        n_ma = min(len(closes), 20)
        ma_now = sum(closes[-n_ma:]) / n_ma
        ma_prev = sum(closes[-n_ma-1:-1]) / n_ma if len(closes) > n_ma else ma_now
        ma_slope = (ma_now - ma_prev) / ma_prev * 100 if ma_prev else 0

        if ma_slope > 0.5:
            trend_dir = '多头'
        elif ma_slope < -0.5:
            trend_dir = '空头'
        else:
            trend_dir = '震荡'

        # vol_20d
        recent_pcts = pcts[-20:]
        if len(recent_pcts) >= 3:
            mean_r = sum(recent_pcts) / len(recent_pcts)
            var = sum((r - mean_r)**2 for r in recent_pcts) / len(recent_pcts)
            vol_20d = math.sqrt(var) * math.sqrt(252) / 100
        else:
            vol_20d = 0

        # vol_pctile_60d
        vol_history = []
        for i in range(3, len(pcts) + 1):
            window = pcts[max(0, i-20):i]
            if len(window) >= 3:
                m = sum(window) / len(window)
                v = sum((x - m)**2 for x in window) / len(window)
                vol_history.append(math.sqrt(v) * math.sqrt(252) / 100)
        if vol_history:
            hist_window = vol_history[-60:]
            below = sum(1 for v in hist_window if v <= vol_20d)
            vol_pctile_60d = below / len(hist_window)
        else:
            vol_pctile_60d = 0.5

        # vol_trend
        if len(vol_history) >= 6:
            vol_trend = vol_20d > vol_history[-6]
        else:
            vol_trend = False

        # volume_ratio
        n60 = min(len(amounts), 60)
        ma60_amt = sum(amounts[-n60:]) / n60 if n60 else 0
        volume_ratio = avg_daily_amt / ma60_amt if ma60_amt > 0 else 1.0
        volume_signal = volume_ratio > 1.2

        # signal_count
        drivers = []
        if trend_dir in ('多头', '空头'):
            drivers.append(f'趋势{trend_dir}')
        if vol_trend:
            drivers.append('波动放大')
        if volume_signal:
            drivers.append('放量')
        signal_count = len(drivers)

        results.append({
            'symbol': sym,
            'sector': SYMBOL_SECTOR.get(sym, '其他'),
            'close': round(closes[-1], 2),
            'chg_20d': round(chg_20d, 2),
            'trend_dir': trend_dir,
            'vol_20d': round(vol_20d, 4),
            'vol_pctile_60d': round(vol_pctile_60d, 4),
            'vol_trend': vol_trend,
            'volume_ratio': round(volume_ratio, 4),
            'volume_signal': volume_signal,
            'avg_daily_amt': round(avg_daily_amt, 2),
            'signal_count': signal_count,
            'drivers': drivers,
            'industry_drivers': INDUSTRY_DRIVERS.get(sym, ''),
            '_abs_chg': abs(chg_20d),
            '_vr': volume_ratio,
        })

    if not results:
        return None

    # 标准化 trend_score
    abs_chgs = [r['_abs_chg'] for r in results]
    vrs = [r['_vr'] for r in results]
    max_c, min_c = max(abs_chgs), min(abs_chgs)
    max_v, min_v = max(vrs), min(vrs)

    for r in results:
        cn = (r['_abs_chg'] - min_c) / (max_c - min_c) if max_c > min_c else 0.5
        vn = (r['_vr'] - min_v) / (max_v - min_v) if max_v > min_v else 0.5
        r['trend_score'] = round(0.40 * cn + 0.30 * r['vol_pctile_60d'] + 0.30 * vn, 4)
        del r['_abs_chg']
        del r['_vr']

    results.sort(key=lambda x: x['trend_score'], reverse=True)

    latest_date = max(d['date'] for data in series.values() for d in data)
    return {'scan_date': latest_date, 'n_scanned': len(results), 'symbols': results}


def write_output(result):
    # JSON
    with open(OUT_JSON, 'w', encoding='gb18030') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # CSV
    csv_headers = [
        'symbol', 'sector', 'close', 'chg_20d', 'trend_dir', 'vol_20d',
        'vol_pctile_60d', 'vol_trend', 'volume_ratio', 'volume_signal',
        'avg_daily_amt', 'signal_count', 'drivers', 'industry_drivers', 'trend_score',
        'formula_chg_20d', 'formula_trend_dir', 'formula_vol_20d',
        'formula_vol_pctile_60d', 'formula_volume_ratio', 'formula_trend_score'
    ]
    rows = []
    for s in result['symbols']:
        rows.append({
            **{k: v for k, v in s.items() if k != 'drivers'},
            'drivers': '|'.join(s.get('drivers', [])),
            'formula_chg_20d': '(close_today / close_20d_ago - 1) × 100',
            'formula_trend_dir': '多头(MA20斜率>0.5%) | 空头(<-0.5%) | 震荡(其他)',
            'formula_vol_20d': 'std(近20日涨跌幅%) × sqrt(252) / 100 → 年化波动率',
            'formula_vol_pctile_60d': 'vol_20d在近60日滚动波动率序列中的分位数',
            'formula_volume_ratio': '成交额MA20 / 成交额MA60',
            'formula_trend_score': '0.40×|chg_20d|标准化 + 0.30×vol_pctile_60d + 0.30×volume_ratio标准化',
        })

    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    log("=" * 50)
    log("模块二：品种趋势扫描（从CSV读取）")
    log("=" * 50)

    series = load_fut_csv()
    if not series:
        return

    log(f"  {len(series)} 个品种")

    result = compute_scan(series)
    if not result:
        log("  无活跃品种")
        return

    write_output(result)

    log(f"\n✅ 模块二完成")
    log(f"  扫描日期: {result['scan_date']}")
    log(f"  活跃品种: {result['n_scanned']}")
    log(f"  Top 5:")
    for i, s in enumerate(result['symbols'][:5]):
        log(f"    {i+1}. {s['symbol']:>4s} ({s['sector']})  score={s['trend_score']:.3f}  chg={s['chg_20d']:+.1f}%  {s['trend_dir']}  signals={s['signal_count']}")
    log(f"  CSV: {OUT_CSV}")


if __name__ == '__main__':
    main()
