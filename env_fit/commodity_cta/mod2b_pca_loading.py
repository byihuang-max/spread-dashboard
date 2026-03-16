#!/usr/bin/env python3
"""
模块2b：PCA Loading增强版品种扫描

基于mod1b的PCA结果，从loading角度分析每个品种对市场主成分的贡献。
- PC1 loading 高的品种 = 驱动全市场共振的主力
- PC2 loading 高的品种 = 市场内部分化的主力
- loading符号 = 品种在该成分上的方向

与原mod2的区别：
  mod2: 看单品种自身的趋势强度（涨跌幅、MA排列、Donchian）
  mod2b: 看品种在全市场结构中的角色（谁在带节奏、谁在对抗）

数据源：读取 mod1b_pca_engine.json（需先跑mod1b）+ fut_daily.csv（补充价格信息）
输出：mod2b_pca_loading.json + mod2b_pca_loading.csv
"""

import json, os, csv, math
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PCA_JSON = os.path.join(BASE_DIR, 'mod1b_pca_engine.json')
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'mod2b_pca_loading.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod2b_pca_loading.csv')

SECTORS = {
    '黑色系': ['RB','HC','I','J','JM','SF','SM','SS'],
    '有色金属': ['CU','AL','ZN','PB','NI','SN','BC','AO','SI'],
    '贵金属': ['AU','AG'],
    '能源化工': ['SC','FU','LU','BU','MA','EG','EB','TA','PP','L','V','PF','SA','FG','UR','PX','SP','RU','NR','BR','PG'],
    '农产品': ['A','B','M','Y','P','OI','RM','CF','CY','SR','C','CS','JD','LH','AP','CJ','PK','WH','RI','RR'],
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


def load_pca_data():
    """读取mod1b输出"""
    if not os.path.exists(PCA_JSON):
        log(f"ERROR: {PCA_JSON} 不存在，先跑 mod1b_pca_engine.py")
        return None
    with open(PCA_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_latest_prices():
    """从fut_daily.csv读取最新价格和20日涨跌幅"""
    if not os.path.exists(FUT_CSV):
        return {}
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
            })
    result = {}
    for sym, data in series.items():
        data.sort(key=lambda x: x['date'])
        if len(data) >= 2:
            close = data[-1]['close']
            n20 = min(len(data), 21)
            close_20d = data[-n20]['close']
            chg_20d = (close / close_20d - 1) * 100 if close_20d > 0 else 0
            result[sym] = {'close': close, 'chg_20d': round(chg_20d, 2)}
    return result


def analyze_loadings(pca_data, prices):
    """增强loading分析"""
    loadings_raw = pca_data['latest_loadings']['loadings']
    pc1_explained = pca_data['latest_loadings']['pc1_explained']
    pc2_explained = pca_data['latest_loadings']['pc2_explained']
    date = pca_data['latest_loadings']['date']

    # 增强每个品种的信息
    enhanced = []
    for ld in loadings_raw:
        sym = ld['symbol']
        price_info = prices.get(sym, {})

        # PC1角色判定
        pc1_abs = abs(ld['pc1_loading'])
        if pc1_abs > 0.20:
            pc1_role = '核心驱动'
        elif pc1_abs > 0.12:
            pc1_role = '显著参与'
        elif pc1_abs > 0.06:
            pc1_role = '一般参与'
        else:
            pc1_role = '独立运行'

        # PC2角色：loading大说明在市场分化中站队明显
        pc2_abs = abs(ld['pc2_loading'])
        if pc2_abs > 0.20:
            pc2_role = '分化主力'
        elif pc2_abs > 0.12:
            pc2_role = '明显站队'
        else:
            pc2_role = '中立'

        # 综合角色
        if pc1_role == '核心驱动' and pc2_role in ('分化主力', '明显站队'):
            combined_role = '领涨/领跌核心'
        elif pc1_role == '核心驱动':
            combined_role = '趋势跟随主力'
        elif pc2_role == '分化主力':
            combined_role = '板块分化旗手'
        elif pc1_role == '独立运行':
            combined_role = '独立行情'
        else:
            combined_role = '一般品种'

        enhanced.append({
            'symbol': sym,
            'sector': ld['sector'],
            'pc1_loading': ld['pc1_loading'],
            'pc2_loading': ld['pc2_loading'],
            'pc1_abs': ld['pc1_abs'],
            'pc1_role': pc1_role,
            'pc2_role': pc2_role,
            'combined_role': combined_role,
            'close': price_info.get('close', 0),
            'chg_20d': price_info.get('chg_20d', 0),
            'industry_drivers': INDUSTRY_DRIVERS.get(sym, ''),
        })

    # 按PC1 |loading| 排序
    enhanced.sort(key=lambda x: x['pc1_abs'], reverse=True)

    # 板块聚合分析
    sector_analysis = {}
    for sec in SECTORS:
        sec_items = [e for e in enhanced if e['sector'] == sec]
        if not sec_items:
            continue
        avg_pc1 = sum(e['pc1_loading'] for e in sec_items) / len(sec_items)
        avg_pc2 = sum(e['pc2_loading'] for e in sec_items) / len(sec_items)
        # 板块内部一致性：PC1 loading的标准差，越小=越一致
        if len(sec_items) > 1:
            mean_l = avg_pc1
            coherence_var = sum((e['pc1_loading'] - mean_l)**2 for e in sec_items) / len(sec_items)
            coherence = 1 - min(1, math.sqrt(coherence_var) / 0.15)  # 标准差<0.15视为高一致性
        else:
            coherence = 1.0

        sector_analysis[sec] = {
            'sector': sec,
            'n_symbols': len(sec_items),
            'avg_pc1_loading': round(avg_pc1, 4),
            'avg_pc2_loading': round(avg_pc2, 4),
            'coherence': round(coherence, 4),
            'top_symbol': sec_items[0]['symbol'] if sec_items else '',
        }

    # PC1/PC2对抗轴解读
    # 找PC2正向和负向的板块
    sorted_by_pc2 = sorted(sector_analysis.values(), key=lambda x: x['avg_pc2_loading'])
    if len(sorted_by_pc2) >= 2:
        axis_negative = sorted_by_pc2[0]['sector']
        axis_positive = sorted_by_pc2[-1]['sector']
        divergence_desc = f"{axis_positive} vs {axis_negative}"
    else:
        divergence_desc = '无明显分化'

    from datetime import datetime
    return {
        'date': date,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'pc1_explained': pc1_explained,
        'pc2_explained': pc2_explained,
        'n_symbols': len(enhanced),
        'divergence_axis': divergence_desc,
        'symbols': enhanced,
        'sectors': sector_analysis,
    }


def write_output(result):
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    csv_headers = [
        'symbol', 'sector', 'pc1_loading', 'pc2_loading', 'pc1_abs',
        'pc1_role', 'pc2_role', 'combined_role',
        'close', 'chg_20d', 'industry_drivers',
    ]
    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for s in result['symbols']:
            writer.writerow({k: s[k] for k in csv_headers})

    log(f"  JSON: {OUT_JSON}")
    log(f"  CSV:  {OUT_CSV}")


def main():
    log("=" * 60)
    log("模块2b：PCA Loading增强版品种扫描")
    log("=" * 60)

    pca_data = load_pca_data()
    if not pca_data:
        return

    prices = load_latest_prices()
    log(f"  价格数据: {len(prices)} 个品种")

    result = analyze_loadings(pca_data, prices)

    write_output(result)

    # 打印结果
    log(f"\n{'='*60}")
    log(f"📊 PCA Loading品种分析 ({result['date']})")
    log(f"{'='*60}")
    log(f"  PC1解释比: {result['pc1_explained']:.1%}  |  PC2解释比: {result['pc2_explained']:.1%}")
    log(f"  分化轴:    {result['divergence_axis']}")

    log(f"\n  Top 8 PC1驱动品种:")
    for i, s in enumerate(result['symbols'][:8]):
        sign1 = '+' if s['pc1_loading'] > 0 else ''
        log(f"    {i+1}. {s['symbol']:>4s} ({s['sector']:4s})  "
            f"PC1={sign1}{s['pc1_loading']:.3f}  "
            f"chg20d={s['chg_20d']:+.1f}%  "
            f"[{s['combined_role']}]")

    log(f"\n  板块一致性:")
    for sec in sorted(result['sectors'].values(), key=lambda x: abs(x['avg_pc1_loading']), reverse=True):
        log(f"    {sec['sector']:6s}  PC1均值={sec['avg_pc1_loading']:+.3f}  "
            f"一致性={sec['coherence']:.2f}  代表={sec['top_symbol']}")

    log(f"\n✅ 模块2b完成")


if __name__ == '__main__':
    main()
