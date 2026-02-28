#!/usr/bin/env python3
"""
模块二：品种趋势扫描（CSV增量模式）v2
从 fut_daily.csv 读取数据，计算每品种趋势评分和信号
v2 改进：
  - 趋势判定：MA多头排列替代MA20单日斜率
  - 新增 Donchian 突破信号（20日/60日高低点）
  - 新增持仓量变化率（OI change）
  - 新增趋势线性度（R²）
  - 波动率 squeeze 检测（低位→高位跳变）
  - 评分公式重构
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
                'high': float(row['high']) if row.get('high') else float(close),
                'low': float(row['low']) if row.get('low') else float(close),
                'pre_close': float(row['pre_close']) if row.get('pre_close') else None,
                'vol': float(row['vol']) if row.get('vol') else 0,
                'amount': float(row['amount']) if row.get('amount') else 0,
                'oi': float(row['oi']) if row.get('oi') else 0,
            })
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


# ---------- 工具函数 ----------

def ma(values, n):
    """简单移动平均，数据不够则用全部"""
    n = min(len(values), n)
    return sum(values[-n:]) / n if n > 0 else 0


def linear_regression_r2(values):
    """对序列做线性回归，返回 R²（0~1）"""
    n = len(values)
    if n < 5:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    ss_xy = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    ss_xx = sum((i - x_mean) ** 2 for i in range(n))
    ss_yy = sum((v - y_mean) ** 2 for v in values)
    if ss_xx == 0 or ss_yy == 0:
        return 0.0
    r2 = (ss_xy ** 2) / (ss_xx * ss_yy)
    return min(r2, 1.0)


def rolling_vol(pcts, window=20):
    """滚动年化波动率"""
    if len(pcts) < 3:
        return 0.0
    w = pcts[-window:]
    m = sum(w) / len(w)
    var = sum((x - m) ** 2 for x in w) / len(w)
    return math.sqrt(var) * math.sqrt(252) / 100


def donchian(highs, lows, n):
    """Donchian 通道：近 n 日最高/最低（不含今天）"""
    h = highs[-(n+1):-1] if len(highs) > n else highs[:-1]
    l = lows[-(n+1):-1] if len(lows) > n else lows[:-1]
    if not h or not l:
        return None, None
    return max(h), min(l)


# ---------- MA 排列判定趋势 ----------

def classify_trend_ma(closes):
    """
    多均线排列判定趋势方向和强度
    返回 (trend_dir, ma_alignment_score)
    ma_alignment_score: -1.0(强空头) ~ +1.0(强多头)
    """
    n = len(closes)
    periods = [5, 10, 20, 60]
    mas = {}
    for p in periods:
        if n >= p:
            mas[p] = sum(closes[-p:]) / p
        else:
            mas[p] = sum(closes) / n

    # 排列得分：比较每对MA的大小关系
    # MA5>MA10, MA10>MA20, MA20>MA60 各贡献 1 分（满分3，归一化到0~1）
    pairs = [(5, 10), (10, 20), (20, 60)]
    score = 0
    for short, long in pairs:
        if mas[short] > mas[long]:
            score += 1
        elif mas[short] < mas[long]:
            score -= 1
        # 相等贡献 0

    alignment = score / 3.0  # -1.0 ~ +1.0

    # 额外看价格在MA之上/之下
    price = closes[-1]
    above_count = sum(1 for p in periods if price > mas[p])
    price_pos = (above_count / len(periods)) * 2 - 1  # -1.0 ~ +1.0

    # 综合（MA排列权重60%，价格位置40%）
    combined = 0.6 * alignment + 0.4 * price_pos

    if combined > 0.3:
        trend_dir = '多头'
    elif combined < -0.3:
        trend_dir = '空头'
    else:
        trend_dir = '震荡'

    return trend_dir, round(combined, 4)


# ---------- 主计算 ----------

def compute_scan(series):
    results = []

    for sym, data in series.items():
        if len(data) < 5:
            continue

        closes = [d['close'] for d in data]
        highs = [d['high'] for d in data]
        lows = [d['low'] for d in data]
        amounts = [d['amount'] for d in data]
        ois = [d['oi'] for d in data]

        # 涨跌幅序列
        pcts = []
        for i in range(1, len(closes)):
            pcts.append((closes[i] / closes[i-1] - 1) * 100 if closes[i-1] > 0 else 0)

        # 日均成交额（MA20）过滤
        avg_daily_amt = ma(amounts, 20)
        if avg_daily_amt <= 500:
            continue

        # ---- 核心指标 ----

        # 1. chg_20d
        n_avail = min(len(closes), 21)
        chg_20d = (closes[-1] / closes[-n_avail] - 1) * 100 if closes[-n_avail] > 0 else 0

        # 2. 趋势方向（MA多头排列）
        trend_dir, ma_alignment = classify_trend_ma(closes)

        # 3. 20日年化波动率
        vol_20d = rolling_vol(pcts, 20)

        # 4. 波动率60日分位数
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

        # 5. 波动率 squeeze：5日前的分位数 vs 现在
        squeeze = False
        if len(vol_history) >= 10:
            hist_5d_ago = vol_history[-60-5:-5] if len(vol_history) > 65 else vol_history[:-5]
            if hist_5d_ago:
                vol_5d_ago = vol_history[-6] if len(vol_history) >= 6 else vol_history[0]
                below_5d = sum(1 for v in hist_5d_ago if v <= vol_5d_ago)
                pctile_5d_ago = below_5d / len(hist_5d_ago)
                # 从低于30分位跳到高于50分位 = squeeze breakout
                if pctile_5d_ago < 0.30 and vol_pctile_60d > 0.50:
                    squeeze = True

        # 6. 量比
        ma60_amt = ma(amounts, 60)
        volume_ratio = avg_daily_amt / ma60_amt if ma60_amt > 0 else 1.0

        # 7. Donchian 突破
        dc20_high, dc20_low = donchian(highs, lows, 20)
        dc60_high, dc60_low = donchian(highs, lows, 60)
        price = closes[-1]

        donchian_20_break = ''
        donchian_60_break = ''
        if dc20_high is not None:
            if price >= dc20_high:
                donchian_20_break = '突破高点'
            elif price <= dc20_low:
                donchian_20_break = '突破低点'
        if dc60_high is not None:
            if price >= dc60_high:
                donchian_60_break = '突破高点'
            elif price <= dc60_low:
                donchian_60_break = '突破低点'

        # Donchian 距离（价格距20日高/低点的百分比，0% = 正在突破）
        if dc20_high and dc20_low and dc20_high > dc20_low:
            dc20_position = (price - dc20_low) / (dc20_high - dc20_low)  # 0~1+
        else:
            dc20_position = 0.5

        # 8. 持仓量变化
        oi_now = ois[-1] if ois[-1] > 0 else 0
        oi_5d_ago = ois[-6] if len(ois) >= 6 and ois[-6] > 0 else 0
        oi_20d_ago = ois[-21] if len(ois) >= 21 and ois[-21] > 0 else 0
        oi_chg_5d = ((oi_now / oi_5d_ago - 1) * 100) if oi_5d_ago > 0 else 0
        oi_chg_20d = ((oi_now / oi_20d_ago - 1) * 100) if oi_20d_ago > 0 else 0

        # 价+OI 共振判定
        if chg_20d > 0 and oi_chg_5d > 3:
            oi_confirm = '多头确认'   # 涨+增仓
        elif chg_20d < 0 and oi_chg_5d > 3:
            oi_confirm = '空头确认'   # 跌+增仓
        elif chg_20d > 0 and oi_chg_5d < -3:
            oi_confirm = '多头衰竭'   # 涨+减仓（空头平仓驱动）
        elif chg_20d < 0 and oi_chg_5d < -3:
            oi_confirm = '空头衰竭'   # 跌+减仓（多头平仓驱动）
        else:
            oi_confirm = ''

        # 9. R²（趋势线性度）
        r2_window = closes[-20:] if len(closes) >= 20 else closes
        r2 = linear_regression_r2(r2_window)

        # ---- 信号计数（最多5颗星） ----
        drivers = []
        if trend_dir in ('多头', '空头'):
            drivers.append(f'趋势{trend_dir}')
        if donchian_20_break:
            drivers.append(f'20日{donchian_20_break}')
        if donchian_60_break:
            drivers.append(f'60日{donchian_60_break}')
        if volume_ratio > 1.2:
            drivers.append('放量')
        if oi_confirm in ('多头确认', '空头确认'):
            drivers.append(oi_confirm)
        if squeeze:
            drivers.append('波动率squeeze')
        if r2 > 0.8:
            drivers.append('高线性度')

        signal_count = min(len(drivers), 5)

        results.append({
            'symbol': sym,
            'sector': SYMBOL_SECTOR.get(sym, '其他'),
            'close': round(closes[-1], 2),
            'chg_20d': round(chg_20d, 2),
            'trend_dir': trend_dir,
            'ma_alignment': ma_alignment,
            'vol_20d': round(vol_20d, 4),
            'vol_pctile_60d': round(vol_pctile_60d, 4),
            'squeeze': squeeze,
            'volume_ratio': round(volume_ratio, 4),
            'donchian_20': donchian_20_break,
            'donchian_60': donchian_60_break,
            'dc20_position': round(dc20_position, 4),
            'oi_chg_5d': round(oi_chg_5d, 2),
            'oi_chg_20d': round(oi_chg_20d, 2),
            'oi_confirm': oi_confirm,
            'r2': round(r2, 4),
            'avg_daily_amt': round(avg_daily_amt, 2),
            'signal_count': signal_count,
            'drivers': drivers,
            'industry_drivers': INDUSTRY_DRIVERS.get(sym, ''),
            # 用于标准化的临时字段
            '_abs_chg': abs(chg_20d),
            '_vr': volume_ratio,
            '_ma_abs': abs(ma_alignment),
            '_r2': r2,
        })

    if not results:
        return None

    # ---- 标准化 + 评分 ----
    def norm(vals):
        mn, mx = min(vals), max(vals)
        return [(v - mn) / (mx - mn) if mx > mn else 0.5 for v in vals]

    abs_chgs_n = norm([r['_abs_chg'] for r in results])
    vr_n = norm([r['_vr'] for r in results])
    ma_n = norm([r['_ma_abs'] for r in results])
    r2_n = norm([r['_r2'] for r in results])

    for i, r in enumerate(results):
        # 新评分：动量25% + MA排列20% + 波动率分位15% + 量比15% + R²15% + Donchian位置10%
        score = (
            0.25 * abs_chgs_n[i] +
            0.20 * ma_n[i] +
            0.15 * r['vol_pctile_60d'] +
            0.15 * vr_n[i] +
            0.15 * r2_n[i] +
            0.10 * min(r['dc20_position'], 1.0)
        )
        r['trend_score'] = round(score, 4)
        del r['_abs_chg'], r['_vr'], r['_ma_abs'], r['_r2']

    results.sort(key=lambda x: x['trend_score'], reverse=True)

    latest_date = max(d['date'] for data in series.values() for d in data)
    return {'scan_date': latest_date, 'n_scanned': len(results), 'symbols': results}


def write_output(result):
    # JSON
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # CSV
    csv_headers = [
        'symbol', 'sector', 'close', 'chg_20d', 'trend_dir', 'ma_alignment',
        'vol_20d', 'vol_pctile_60d', 'squeeze', 'volume_ratio',
        'donchian_20', 'donchian_60', 'dc20_position',
        'oi_chg_5d', 'oi_chg_20d', 'oi_confirm', 'r2',
        'avg_daily_amt', 'signal_count', 'drivers', 'industry_drivers', 'trend_score',
    ]
    rows = []
    for s in result['symbols']:
        row = {k: v for k, v in s.items() if k != 'drivers'}
        row['drivers'] = '|'.join(s.get('drivers', []))
        rows.append(row)

    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(rows)


def main():
    log("=" * 50)
    log("模块二 v2：品种趋势扫描（MA排列+Donchian+OI+R²）")
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

    log(f"\n✅ 模块二 v2 完成")
    log(f"  扫描日期: {result['scan_date']}")
    log(f"  活跃品种: {result['n_scanned']}")
    log(f"  Top 5:")
    for i, s in enumerate(result['symbols'][:5]):
        flags = []
        if s['donchian_20']: flags.append(f"DC20:{s['donchian_20']}")
        if s['oi_confirm']: flags.append(s['oi_confirm'])
        if s['r2'] > 0.8: flags.append(f"R²={s['r2']:.2f}")
        if s['squeeze']: flags.append("Squeeze")
        extra = '  '.join(flags)
        log(f"    {i+1}. {s['symbol']:>4s} ({s['sector']})  score={s['trend_score']:.3f}  "
            f"chg={s['chg_20d']:+.1f}%  {s['trend_dir']}(MA={s['ma_alignment']:+.2f})  "
            f"signals={s['signal_count']}  {extra}")
    log(f"  CSV: {OUT_CSV}")


if __name__ == '__main__':
    main()
