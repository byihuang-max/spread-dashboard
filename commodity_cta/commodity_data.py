#!/usr/bin/env python3
"""
商品CTA策略环境数据脚本（带缓存版）
从 Tushare fut_daily 拉取全市场期货数据，计算CTA友好度、品种趋势扫描、宏观比价
"""

import requests, json, time, os, re, math
from datetime import datetime, timedelta
from collections import defaultdict

TUSHARE_TOKEN = '33b3ff939d0d7954cd76cacce7cf6cbb2b3c3feda13d1ca2cfa594e20ecd'
TUSHARE_URL = 'http://lianghua.nanyangqiankun.top'
BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/commodity_cta'
OUTPUT_JSON = os.path.join(BASE_DIR, 'commodity_cta.json')
CACHE_DIR = os.path.join(BASE_DIR, '_cache')
LOOKBACK_DAYS = 150  # 多拉一些确保120日窗口够

os.makedirs(CACHE_DIR, exist_ok=True)

# ═══ 品种配置 ═══

COMMODITY_NAMES = {
    'RB':'螺纹钢','HC':'热卷','I':'铁矿石','J':'焦炭','JM':'焦煤',
    'SF':'硅铁','SM':'锰硅','SS':'不锈钢',
    'CU':'铜','AL':'铝','ZN':'锌','PB':'铅','NI':'镍','SN':'锡',
    'BC':'国际铜','AO':'氧化铝','SI':'工业硅',
    'AU':'黄金','AG':'白银',
    'SC':'原油','FU':'燃料油','LU':'低硫燃油','BU':'沥青',
    'MA':'甲醇','EG':'乙二醇','EB':'苯乙烯','TA':'PTA',
    'PP':'聚丙烯','L':'塑料','V':'PVC','PF':'短纤',
    'SA':'纯碱','FG':'玻璃','UR':'尿素','PX':'对二甲苯',
    'SP':'纸浆','RU':'橡胶','NR':'20号胶','BR':'丁二烯橡胶','PG':'液化气',
    'A':'豆一','B':'豆二','M':'豆粕','Y':'豆油','P':'棕榈油',
    'OI':'菜油','RM':'菜粕','CF':'棉花','CY':'棉纱',
    'SR':'白糖','C':'玉米','CS':'玉米淀粉',
    'JD':'鸡蛋','LH':'生猪','AP':'苹果','CJ':'红枣','PK':'花生',
    'WH':'强麦','RI':'早稻','RR':'粳米',
}

SECTORS = {
    '黑色系':['RB','HC','I','J','JM','SF','SM','SS'],
    '有色金属':['CU','AL','ZN','PB','NI','SN','BC','AO','SI'],
    '贵金属':['AU','AG'],
    '能源化工':['SC','FU','LU','BU','MA','EG','EB','TA','PP','L','V','PF','SA','FG','UR','PX','SP','RU','NR','BR','PG'],
    '农产品':['A','B','M','Y','P','OI','RM','CF','CY','SR','C','CS','JD','LH','AP','CJ','PK','WH','RI','RR'],
}

SYMBOL_TO_SECTOR = {}
for sec, syms in SECTORS.items():
    for s in syms:
        SYMBOL_TO_SECTOR[s] = sec

INDUSTRIAL_BASKET = ['RB','CU','AL','MA','TA','EG']
AGRI_BASKET = ['M','P','SR','C','OI','CF']

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



# ═══ Tushare 工具函数 ═══

def tushare_call(api_name, params, fields='', retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(TUSHARE_URL, json={
                'api_name': api_name, 'token': TUSHARE_TOKEN,
                'params': params, 'fields': fields
            }, timeout=20)
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                cols = data['data']['fields']
                return [dict(zip(cols, row)) for row in data['data']['items']]
            return []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return []


def get_trade_dates(n_days=LOOKBACK_DAYS):
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=n_days * 2)).strftime('%Y%m%d')
    data = tushare_call('trade_cal', {'exchange': 'SSE', 'start_date': start, 'end_date': end, 'is_open': '1'})
    if not data:
        return []
    dates = sorted([d['cal_date'] for d in data])
    return dates[-n_days:]


def fetch_day_cached(trade_date):
    """拉取某日全市场期货日线，有缓存直接读"""
    cache_file = os.path.join(CACHE_DIR, f'{trade_date}_all.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    data = tushare_call('fut_daily', {'trade_date': trade_date},
                        fields='ts_code,trade_date,open,high,low,close,vol,amount,oi')
    time.sleep(0.3)

    if data:
        with open(cache_file, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
    return data


def extract_symbol(ts_code):
    """从连续合约 ts_code 提取品种代码，如 'RB.SFE' -> 'RB'"""
    return ts_code.split('.')[0]


def is_continuous(ts_code):
    """判断是否为连续合约（纯字母.纯字母）"""
    return bool(re.match(r'^[A-Z]+\.[A-Z]+$', ts_code))


# ═══ 核心计算 ═══

def build_commodity_series(trade_dates):
    """逐日拉取全市场数据，构建品种时序"""
    # symbol -> [{date, close, vol, amount, oi, high, low}, ...]
    series = defaultdict(list)

    for i, td in enumerate(trade_dates):
        cached = os.path.exists(os.path.join(CACHE_DIR, f'{td}_all.json'))
        tag = '📦' if cached else '🌐'
        print(f"  [{i+1}/{len(trade_dates)}] {td} {tag}", end='', flush=True)

        data = fetch_day_cached(td)
        if not data:
            print(" ❌ empty")
            continue

        day_count = 0
        for row in data:
            tc = row.get('ts_code', '')
            if not is_continuous(tc):
                continue
            sym = extract_symbol(tc)
            if sym not in COMMODITY_NAMES:
                continue

            close = row.get('close')
            if close is None or close == 0:
                continue

            series[sym].append({
                'date': td,
                'close': float(close),
                'high': float(row.get('high') or close),
                'low': float(row.get('low') or close),
                'vol': float(row.get('vol') or 0),
                'amount': float(row.get('amount') or 0),
                'oi': float(row.get('oi') or 0),
            })
            day_count += 1

        print(f" → {day_count} 品种")

    return dict(series)


def calc_returns(closes):
    """计算日收益率序列"""
    ret = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            ret.append(math.log(closes[i] / closes[i-1]))
        else:
            ret.append(0)
    return ret


def calc_vol_20d(returns, idx):
    """计算第idx个收益率对应的20日年化波动率"""
    if idx < 19:
        return None
    window = returns[idx-19:idx+1]
    if len(window) < 20:
        return None
    mean = sum(window) / len(window)
    var = sum((r - mean)**2 for r in window) / len(window)
    return round(math.sqrt(var) * math.sqrt(252) * 100, 2)


def calc_ma(values, n):
    """计算移动平均"""
    result = []
    for i in range(len(values)):
        if i < n - 1:
            result.append(None)
        else:
            window = values[i-n+1:i+1]
            valid = [v for v in window if v is not None]
            result.append(sum(valid) / len(valid) if valid else None)
    return result


def percentile_in_window(values, idx, window=60):
    """计算 values[idx] 在最近 window 个值中的分位数"""
    start = max(0, idx - window + 1)
    w = [v for v in values[start:idx+1] if v is not None]
    if not w or values[idx] is None:
        return None
    v = values[idx]
    below = sum(1 for x in w if x <= v)
    return round(below / len(w) * 100, 2)



def compute_commodity_metrics(series, trade_dates):
    """对每个品种计算完整指标时序"""
    # 只保留有足够数据的品种
    MIN_DAYS = 60
    active_symbols = []
    for sym, data in series.items():
        if len(data) >= MIN_DAYS:
            # 检查日均成交额 > 500万
            avg_amt = sum(d['amount'] for d in data[-20:]) / min(20, len(data))
            if avg_amt > 5000000:
                active_symbols.append(sym)

    print(f"\n📊 活跃品种: {len(active_symbols)} / {len(series)}")

    # 构建每个品种的指标时序
    commodity_data = {}
    for sym in active_symbols:
        data = series[sym]
        dates = [d['date'] for d in data]
        closes = [d['close'] for d in data]
        vols = [d['vol'] for d in data]
        amounts = [d['amount'] for d in data]

        returns = calc_returns(closes)

        # 20日波动率序列
        vol_20d = []
        for i in range(len(returns)):
            v = calc_vol_20d(returns, i)
            vol_20d.append(v)

        # MA20
        ma20 = calc_ma(closes, 20)

        # 成交量 MA20 和 MA60
        vol_ma20 = calc_ma(vols, 20)
        vol_ma60 = calc_ma(vols, 60)

        commodity_data[sym] = {
            'dates': dates,
            'closes': closes,
            'returns': returns,
            'vol_20d': vol_20d,
            'ma20': ma20,
            'vol_ma20': vol_ma20,
            'vol_ma60': vol_ma60,
            'amounts': amounts,
            'vols': vols,
        }

    return commodity_data, active_symbols


def compute_scan(commodity_data, active_symbols):
    """计算品种趋势扫描（最新一天）"""
    scan = []
    for sym in active_symbols:
        cd = commodity_data[sym]
        if len(cd['closes']) < 21:
            continue

        closes = cd['closes']
        ma20 = cd['ma20']
        vol_20d = cd['vol_20d']
        vol_ma20 = cd['vol_ma20']
        vol_ma60 = cd['vol_ma60']

        latest_close = closes[-1]
        latest_ma20 = ma20[-1]

        # 20日涨跌幅
        if len(closes) >= 21:
            chg_20d = round((closes[-1] / closes[-21] - 1) * 100, 2)
        else:
            chg_20d = 0

        # 趋势方向
        trend_dir = 'none'
        if latest_ma20 and ma20[-6] and ma20[-6] > 0:
            ma20_slope = (latest_ma20 - ma20[-6]) / ma20[-6]
            if latest_close > latest_ma20 and ma20_slope > 0.005:
                trend_dir = 'long'
            elif latest_close < latest_ma20 and ma20_slope < -0.005:
                trend_dir = 'short'

        # 波动率
        latest_vol = vol_20d[-1] if vol_20d[-1] is not None else 0
        vol_pctile = percentile_in_window(vol_20d, len(vol_20d)-1, 60)

        # 波动率趋势（近5日 vs 20日均值）
        recent_vols = [v for v in vol_20d[-5:] if v is not None]
        all_vols = [v for v in vol_20d[-20:] if v is not None]
        vol_trend = 'flat'
        if recent_vols and all_vols:
            rv = sum(recent_vols) / len(recent_vols)
            av = sum(all_vols) / len(all_vols)
            if av > 0:
                ratio = (rv - av) / av
                if ratio > 0.10:
                    vol_trend = 'up'
                elif ratio < -0.10:
                    vol_trend = 'down'

        # 成交量比
        vm20 = vol_ma20[-1]
        vm60 = vol_ma60[-1]
        volume_ratio = round(vm20 / vm60, 2) if vm20 and vm60 and vm60 > 0 else 1.0
        volume_signal = 'flat'
        if volume_ratio > 1.2:
            volume_signal = 'expand'
        elif volume_ratio < 0.8:
            volume_signal = 'shrink'

        # 趋势强度评分
        chg_norm = min(abs(chg_20d) / 15 * 100, 100)
        vol_p = vol_pctile if vol_pctile is not None else 50
        vr_norm = min(max((volume_ratio - 0.8) / 0.6 * 100, 0), 100)
        trend_score = round(0.40 * chg_norm + 0.30 * vol_p + 0.30 * vr_norm, 2)

        # 信号计数
        signal_count = 0
        if trend_dir != 'none':
            signal_count += 1
        if vol_trend == 'up':
            signal_count += 1
        if volume_signal == 'expand':
            signal_count += 1

        scan.append({
            'symbol': sym,
            'name': COMMODITY_NAMES.get(sym, sym),
            'sector': SYMBOL_TO_SECTOR.get(sym, '其他'),
            'close': latest_close,
            'chg_20d': chg_20d,
            'trend_dir': trend_dir,
            'vol_20d': round(latest_vol, 2),
            'vol_pctile_60d': round(vol_p, 2),
            'vol_trend': vol_trend,
            'volume_ratio': volume_ratio,
            'volume_signal': volume_signal,
            'trend_score': trend_score,
            'signal_count': signal_count,
            'drivers': INDUSTRY_DRIVERS.get(sym, ''),
        })

    scan.sort(key=lambda x: x['trend_score'], reverse=True)
    return scan



def compute_environment(commodity_data, active_symbols, trade_dates):
    """计算CTA整体环境指标时序"""
    # 找出所有品种都有数据的日期范围
    all_dates = set()
    for sym in active_symbols:
        for d in commodity_data[sym]['dates']:
            all_dates.add(d)
    env_dates = sorted(all_dates)

    # 只取最近120天
    env_dates = env_dates[-120:]

    env = {'dates': [], 'cta_friendly': [], 'avg_vol_20d': [],
           'vol_percentile_60d': [], 'trend_pct': [], 'volume_ratio': []}

    for di, date in enumerate(env_dates):
        vols_today = []
        trend_count = 0
        vol_ratios = []
        active_count = 0

        for sym in active_symbols:
            cd = commodity_data[sym]
            if date not in cd['dates']:
                continue
            idx = cd['dates'].index(date)

            # 波动率
            if idx < len(cd['vol_20d']) and cd['vol_20d'][idx] is not None:
                vols_today.append(cd['vol_20d'][idx])

            # 趋势判定
            closes = cd['closes']
            ma20 = cd['ma20']
            if idx >= 5 and ma20[idx] and ma20[idx-5] and ma20[idx-5] > 0:
                slope = (ma20[idx] - ma20[idx-5]) / ma20[idx-5]
                if closes[idx] > ma20[idx] and slope > 0.005:
                    trend_count += 1
                elif closes[idx] < ma20[idx] and slope < -0.005:
                    trend_count += 1

            # 成交量比
            vm20 = cd['vol_ma20'][idx] if idx < len(cd['vol_ma20']) else None
            vm60 = cd['vol_ma60'][idx] if idx < len(cd['vol_ma60']) else None
            if vm20 and vm60 and vm60 > 0:
                vol_ratios.append(vm20 / vm60)

            active_count += 1

        if active_count == 0:
            continue

        avg_vol = round(sum(vols_today) / len(vols_today), 2) if vols_today else 0
        t_pct = round(trend_count / active_count * 100, 2)
        avg_vr = round(sum(vol_ratios) / len(vol_ratios), 2) if vol_ratios else 1.0

        env['dates'].append(date)
        env['avg_vol_20d'].append(avg_vol)
        env['trend_pct'].append(t_pct)
        env['volume_ratio'].append(avg_vr)

    # 波动率分位数和CTA友好度
    for i in range(len(env['dates'])):
        vp = percentile_in_window(env['avg_vol_20d'], i, 60)
        env['vol_percentile_60d'].append(vp if vp is not None else 50)

        tp = env['trend_pct'][i]
        vp_val = env['vol_percentile_60d'][i]
        vr = env['volume_ratio'][i]

        tp_norm = min(tp / 60 * 100, 100)
        vr_norm = min(max((vr - 0.8) / 0.6 * 100, 0), 100)
        cta_f = round(0.40 * tp_norm + 0.30 * vp_val + 0.30 * vr_norm, 2)
        env['cta_friendly'].append(cta_f)

    return env


def compute_ratios(commodity_data):
    """计算宏观比价指标"""
    ratios = {}

    # 铜金比、油金比
    pairs = [('copper_gold', 'CU', 'AU', '铜金比'),
             ('oil_gold', 'SC', 'AU', '油金比')]

    for key, num_sym, den_sym, name in pairs:
        if num_sym not in commodity_data or den_sym not in commodity_data:
            continue
        nd = commodity_data[num_sym]
        dd = commodity_data[den_sym]

        # 对齐日期
        nd_map = dict(zip(nd['dates'], nd['closes']))
        dd_map = dict(zip(dd['dates'], dd['closes']))
        common = sorted(set(nd['dates']) & set(dd['dates']))
        common = common[-120:]

        if len(common) < 20:
            continue

        dates = []
        values = []
        for d in common:
            if dd_map[d] > 0:
                v = round(nd_map[d] / dd_map[d], 6)
                dates.append(d)
                values.append(v)

        if len(values) < 20:
            continue

        current = values[-1]
        chg_20d = round((values[-1] / values[-21] - 1) * 100, 2) if len(values) >= 21 else 0
        pctile = percentile_in_window(values, len(values)-1, 60)

        # 趋势
        ma20 = calc_ma(values, 20)
        trend = 'flat'
        if ma20[-1] and ma20[-6] and ma20[-6] > 0:
            slope = (ma20[-1] - ma20[-6]) / ma20[-6]
            if slope > 0.005: trend = 'up'
            elif slope < -0.005: trend = 'down'

        interp_map = {
            'copper_gold': {
                'up': '铜金比上行，经济扩张预期，工业品CTA多头环境偏友好',
                'down': '铜金比下行，避险情绪升温，贵金属CTA多头环境偏友好',
                'flat': '铜金比震荡，宏观方向不明确'
            },
            'oil_gold': {
                'up': '油金比上行，通胀预期升温，能化品CTA多头环境偏友好',
                'down': '油金比下行，通缩/避险逻辑，贵金属CTA多头环境偏友好',
                'flat': '油金比震荡，能源vs避险博弈中'
            }
        }

        ratios[key] = {
            'name': name,
            'dates': dates[-60:],
            'values': values[-60:],
            'current': current,
            'chg_20d': chg_20d,
            'percentile_60d': round(pctile, 2) if pctile else 50,
            'trend': trend,
            'interpretation': interp_map.get(key, {}).get(trend, '')
        }

    # 工业品/农产品比
    ind_syms = [s for s in INDUSTRIAL_BASKET if s in commodity_data]
    agr_syms = [s for s in AGRI_BASKET if s in commodity_data]

    if ind_syms and agr_syms:
        # 找公共日期
        all_dates_sets = []
        for s in ind_syms + agr_syms:
            all_dates_sets.append(set(commodity_data[s]['dates']))
        common = sorted(set.intersection(*all_dates_sets))
        common = common[-120:]

        if len(common) >= 20:
            ind_nav = [1.0]
            agr_nav = [1.0]
            dates = [common[0]]

            for i in range(1, len(common)):
                d, pd = common[i], common[i-1]
                # 工业品等权日收益
                ind_rets = []
                agr_rets = []
                for s in ind_syms:
                    cd = commodity_data[s]
                    dm = dict(zip(cd['dates'], cd['closes']))
                    if d in dm and pd in dm and dm[pd] > 0:
                        ind_rets.append(dm[d] / dm[pd] - 1)
                for s in agr_syms:
                    cd = commodity_data[s]
                    dm = dict(zip(cd['dates'], cd['closes']))
                    if d in dm and pd in dm and dm[pd] > 0:
                        agr_rets.append(dm[d] / dm[pd] - 1)

                if ind_rets and agr_rets:
                    ir = sum(ind_rets) / len(ind_rets)
                    ar = sum(agr_rets) / len(agr_rets)
                    ind_nav.append(round(ind_nav[-1] * (1 + ir), 6))
                    agr_nav.append(round(agr_nav[-1] * (1 + ar), 6))
                    dates.append(d)

            if len(dates) >= 20:
                ratio_vals = [round(ind_nav[i] / agr_nav[i], 6) if agr_nav[i] > 0 else 1.0
                              for i in range(len(dates))]
                current = ratio_vals[-1]
                chg_20d = round((ratio_vals[-1] / ratio_vals[-21] - 1) * 100, 2) if len(ratio_vals) >= 21 else 0
                pctile = percentile_in_window(ratio_vals, len(ratio_vals)-1, 60)

                ma20 = calc_ma(ratio_vals, 20)
                trend = 'flat'
                if ma20[-1] and ma20[-6] and ma20[-6] > 0:
                    slope = (ma20[-1] - ma20[-6]) / ma20[-6]
                    if slope > 0.005: trend = 'up'
                    elif slope < -0.005: trend = 'down'

                interp = {
                    'up': '工业品相对农产品走强，需求驱动逻辑，工业品CTA趋势更强',
                    'down': '农产品相对工业品走强，供给驱动或衰退逻辑',
                    'flat': '工业品与农产品相对均衡'
                }

                ratios['industrial_agri'] = {
                    'name': '工业品/农产品',
                    'dates': dates[-60:],
                    'values': ratio_vals[-60:],
                    'current': current,
                    'chg_20d': chg_20d,
                    'percentile_60d': round(pctile, 2) if pctile else 50,
                    'trend': trend,
                    'interpretation': interp.get(trend, '')
                }

    return ratios



def main():
    print("🔥 商品CTA策略环境数据生成（带缓存）")

    # Step 1: 交易日历
    dates = get_trade_dates(LOOKBACK_DAYS)
    if not dates:
        print("❌ 无法获取交易日历"); return
    print(f"📅 {len(dates)} 个交易日: {dates[0]} ~ {dates[-1]}")

    # Step 2: 逐日拉取全市场数据
    print("\n📡 拉取全市场期货日线...")
    series = build_commodity_series(dates)
    if not series:
        print("❌ 无数据"); return
    print(f"\n📦 共 {len(series)} 个品种有数据")

    # Step 3: 计算指标
    print("\n📊 计算品种指标...")
    commodity_data, active_symbols = compute_commodity_metrics(series, dates)
    if not active_symbols:
        print("❌ 无活跃品种"); return

    # Step 4: 品种扫描
    print("🔍 品种趋势扫描...")
    scan = compute_scan(commodity_data, active_symbols)

    # Step 5: CTA环境
    print("🌡️ 计算CTA整体环境...")
    env = compute_environment(commodity_data, active_symbols, dates)

    # Step 6: 宏观比价
    print("⚖️ 计算宏观比价...")
    ratios = compute_ratios(commodity_data)

    # Step 7: 汇总 latest
    latest_date = env['dates'][-1] if env['dates'] else ''
    latest_cta = env['cta_friendly'][-1] if env['cta_friendly'] else 0

    cta_label = '偏友好' if latest_cta >= 60 else ('中性' if latest_cta >= 40 else '偏冷淡')

    long_syms = [s['symbol'] for s in scan if s['trend_dir'] == 'long'][:5]
    short_syms = [s['symbol'] for s in scan if s['trend_dir'] == 'short'][:5]
    signal_count = sum(1 for s in scan if s['signal_count'] >= 2)

    latest = {
        'date': latest_date,
        'cta_friendly': latest_cta,
        'cta_label': cta_label,
        'avg_vol': env['avg_vol_20d'][-1] if env['avg_vol_20d'] else 0,
        'trend_count': sum(1 for s in scan if s['trend_dir'] != 'none'),
        'total_active': len(active_symbols),
        'trend_pct': env['trend_pct'][-1] if env['trend_pct'] else 0,
        'top_long': long_syms,
        'top_short': short_syms,
        'signal_commodities': signal_count,
    }

    # Step 8: 输出 JSON
    output = {
        'meta': {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'date_range': f"{env['dates'][0]} ~ {env['dates'][-1]}" if env['dates'] else '',
            'trade_days': len(env['dates']),
            'active_commodities': len(active_symbols),
        },
        'environment': env,
        'scan': scan,
        'ratios': ratios,
        'latest': latest,
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成！{len(active_symbols)} 个活跃品种 → {OUTPUT_JSON}")
    print(f"   CTA友好度: {latest_cta} ({cta_label})")
    print(f"   趋势品种: {latest['trend_count']}/{len(active_symbols)} ({latest['trend_pct']:.1f}%)")
    print(f"   三重信号品种: {signal_count}")
    if long_syms:
        print(f"   多头Top: {', '.join(COMMODITY_NAMES.get(s,s) for s in long_syms)}")
    if short_syms:
        print(f"   空头Top: {', '.join(COMMODITY_NAMES.get(s,s) for s in short_syms)}")
    for k, v in ratios.items():
        print(f"   {v['name']}: {v['interpretation']}")


if __name__ == '__main__':
    main()
