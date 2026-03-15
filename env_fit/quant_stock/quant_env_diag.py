#!/usr/bin/env python3
"""
量化宽基 — 超额环境诊断模块 v2
================================================

【核心命题】
量化超额好不好做？不是看指增产品净值，是看 alpha 环境。

【五因子嵌套框架】
① 流动性水位 (前提) — 全A成交额 + 稳定性 + 趋势
   → 枯竭直接红灯，其他因子不看
② 个股离散度 (alpha来源) — 截面波动率
   → 高=选股空间大，低=同涨同跌没得选
③ 风格集中度 (alpha杀手) — 宽基占比HHI + 因子极端演绎
   → 与离散度是交互项：离散度高但风格极集中时alpha不稳
④ 市场预期 (情绪结构) — 基差历史分位 + 大票虹吸三条件验证
   → 升水不直接扣分，要验证大票是否真的在吸走流动性
⑤ 微观结构 (尾部风险) — 行业拥挤度 + 资金面共识
   → 拥挤+偏空=踩踏预警

【嵌套逻辑（不是简单加权！）】
流动性枯竭 → 直接红灯
流动性OK → alpha环境 = f(离散度, 集中度) → 市场预期修正 → 微观尾部叠加

【中性策略辅助】
超额 < 基差 → 亏钱 | = 基差 → 平 | > 基差 → 正收益 | ≥ 2×基差 → 有配置价值

输出：quant_env_diag.json
设计文档：README_design.md
"""
import json, os, math, statistics
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(os.path.dirname(BASE))  # gamt-dashboard 根目录

def load(path):
    with open(path, 'r') as f:
        return json.load(f)

def safe_load(path, default=None):
    try:
        return load(path)
    except Exception:
        return default

# ═══════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════
# quant_stock_data.json — 成交额、宽基占比、基差、因子净值（日频）
qs_data    = load(os.path.join(BASE, 'quant_stock_data.json'))
# amount_vol.json — 成交额波动率/水位/脉冲检测（由 amount_vol_calc.py 生成）
amount_vol = load(os.path.join(BASE, 'amount_vol.json'))
# cross_vol.json — 全A个股截面波动率（由 cross_vol_data.py 从 Tushare 拉取计算）
cross_vol  = safe_load(os.path.join(BASE, 'cross_vol.json'), {})
# crowding.json — 行业拥挤度 + 三资金面共识（由 micro_flow/crowding 模块生成）
crowding   = safe_load(os.path.join(DASH, 'micro_flow', 'crowding', 'crowding.json'), {})
# style_spread_signals.json — 风格拥挤标签（由 size_spread 模块生成）
style_sig  = safe_load(os.path.join(DASH, 'size_spread', 'style_spread_signals.json'), {})
# fund_nav_quant-stock.json — 产品净值数据（用于中性辅助计算）
fund_nav   = safe_load(os.path.join(DASH, 'size_spread', 'fund_nav', 'fund_nav_quant-stock.json'), {})


# ═══════════════════════════════════════
# 辅助：读取指数日线 CSV
# ═══════════════════════════════════════
def load_index_csv():
    """
    读 qs_index_daily.csv，返回 {ts_code: [{date, close, amount}, ...]}
    用于计算大票/小票涨跌幅差（市场预期因子的虹吸验证）
    """
    import csv
    path = os.path.join(BASE, 'qs_index_daily.csv')
    data = {}
    try:
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('ts_code', '')
                if not code:
                    continue
                if code not in data:
                    data[code] = []
                data[code].append({
                    'date': row.get('trade_date', ''),
                    'close': float(row.get('close', 0)),
                    'amount': float(row.get('amount', 0)) if row.get('amount') else 0,
                })
        for code in data:
            data[code].sort(key=lambda x: x['date'])
    except Exception as e:
        print(f'  ⚠️ 读取 qs_index_daily.csv 失败: {e}')
    return data

index_daily = load_index_csv()


def _calc_index_return(ts_code, days):
    """计算某指数近N日涨幅(%)，用于大票/小票相对强弱比较"""
    series = index_daily.get(ts_code, [])
    if len(series) < days + 1:
        return None
    recent = series[-1]['close']
    prev = series[-(days + 1)]['close']
    if prev == 0:
        return None
    return (recent / prev - 1) * 100


# ═══════════════════════════════════════
# Factor ① 流动性水位
# ═══════════════════════════════════════
# 【逻辑】
# 量化策略的基础生存条件——没有流动性，选股再好也无法执行。
# 不只看成交额绝对值，还看稳定性和相对变化：
# - 稳定放量 > 脉冲放量（脉冲=情绪驱动，量化难赚）
# - 用变异系数(CV)衡量稳定性
# - 周度环比(MA5 vs MA20)捕捉相对水位变化
# 枯竭（<8000亿）→ 直接红灯，其他因子都不用看
#
# 【2026-03-15 优化 by Roni】
# 绝对值有滞后性：之前常态3.2万亿，现在2.5万亿，decay了22%
# 按旧逻辑2.5万亿→90分(过热)，但实际是缩量信号
# 解决：加入周度环比修正，捕捉相对于近期常态的变化
# ═══════════════════════════════════════
def calc_liquidity():
    lat = amount_vol.get('latest', {})
    amount = lat.get('amount_yi', 0)    # 当日全A成交额（亿）
    ma5 = lat.get('ma5', 0)             # 5日均线
    ma20 = lat.get('ma20', 0)           # 20日均线
    cv = lat.get('cv_20d', 0)           # 20日变异系数 = std/mean
    trend = lat.get('trend', '')        # 放量/缩量/平稳（MA5 vs MA20）
    pulse = lat.get('pulse', False)     # 脉冲检测（偏离>2σ）
    level = lat.get('level', '')        # 水位等级文本

    # ── 基础评分：按成交额绝对值（降低权重，60-80分区间）──
    # 2026-03-15 优化：量化占比6成+，基础流动性需求提高
    # 阈值整体上移，同时降低绝对值权重，让环比修正更有效
    if amount < 12000:   score = 20  # 枯竭（+4000）
    elif amount < 15000: score = 40  # 偏低（+5000）
    elif amount < 18000: score = 55  # 一般（+6000）
    elif amount < 22000: score = 65  # 正常（+7000）
    elif amount < 28000: score = 75  # 充裕（+8000）
    else:                score = 80  # 过热（降低上限）

    # ── 周度环比修正（相对水位，扩大权重到-40~+20分）──
    # 关键洞察：2.5万亿在牛市=缩量(危险)，在熊市=过热(也危险)
    # 要看相对于近期常态的变化，而不是绝对值
    # 环比权重加大，可以大幅改变评级
    decay_signal = None
    if ma20 > 0:
        ma5_vs_ma20_pct = (ma5 / ma20 - 1) * 100  # 周度环比百分比
        
        if ma5_vs_ma20_pct < -20:      # 周度缩量超20%
            score -= 40
            decay_signal = '暴跌式缩量'
        elif ma5_vs_ma20_pct < -15:    # 周度缩量15-20%
            score -= 30
            decay_signal = '急剧缩量'
        elif ma5_vs_ma20_pct < -10:    # 周度缩量10-15%
            score -= 20
            decay_signal = '明显缩量'
        elif ma5_vs_ma20_pct < -5:     # 周度缩量5-10%
            score -= 10
            decay_signal = '温和缩量'
        elif ma5_vs_ma20_pct > 20:     # 周度放量超20%
            score += 20
            decay_signal = '暴涨式放量'
        elif ma5_vs_ma20_pct > 15:     # 周度放量15-20%
            score += 15
            decay_signal = '急剧放量'
        elif ma5_vs_ma20_pct > 10:     # 周度放量10-15%
            score += 10
            decay_signal = '明显放量'
        else:
            decay_signal = '平稳'
    else:
        ma5_vs_ma20_pct = 0
        decay_signal = '数据不足'

    # ── 稳定性修正：CV越高说明成交额波动越大，不是好事 ──
    # CV > 20% 说明成交额忽高忽低，情绪驱动明显
    if cv > 0.20:   score -= 15; stability = '极不稳定'
    elif cv > 0.15: score -= 8;  stability = '波动偏大'
    elif cv > 0.10: score -= 3;  stability = '正常波动'
    else:                        stability = '非常稳定'

    # ── 趋势修正：缩量不好，放量加分 ──
    if trend == '缩量':   score -= 5
    elif trend == '放量': score += 5

    # ── 脉冲标记：单日异常放量，往往第二天就缩回去 ──
    if pulse: score -= 5

    score = max(0, min(100, score))

    if score >= 75:   grade, emoji = '充裕', '🟢'
    elif score >= 55: grade, emoji = '正常', '🟡'
    elif score >= 35: grade, emoji = '偏低', '🟠'
    else:             grade, emoji = '枯竭', '🔴'

    signals = [
        f'成交额{amount:.0f}亿 ({level})',
        f'趋势{trend} (MA5={ma5:.0f} vs MA20={ma20:.0f})',
        f'周度环比: {decay_signal} ({ma5_vs_ma20_pct:+.1f}%)',
        f'稳定性: {stability} (CV={cv:.1%})',
    ]
    if pulse: signals.append('⚡ 脉冲放量')

    return {
        'score': score, 'grade': grade, 'emoji': emoji,
        'amount': amount, 'trend': trend, 'stability': stability,
        'cv': round(cv, 4), 'signals': signals,
        'decay_signal': decay_signal,
        'ma5_vs_ma20_pct': round(ma5_vs_ma20_pct, 2)
    }


# ═══════════════════════════════════════
# Factor ② 个股离散度
# ═══════════════════════════════════════
# 【逻辑】
# 截面波动率 = 当日全A个股收益率的标准差
# 高离散 → 个股涨跌分化大 → 选股alpha空间大
# 低离散 → 同涨同跌 → 不管用什么因子选股都没用
# A股经验区间：1.5~4.5，通常2.0~3.0为正常
# ═══════════════════════════════════════
def calc_dispersion():
    cv_data = cross_vol.get('data', [])
    if not cv_data:
        return {'score': 50, 'grade': '数据缺失', 'emoji': '⚪',
                'cross_vol': None, 'signals': ['截面波动率数据缺失']}

    latest = cv_data[-1]
    vol = latest.get('cross_vol', 0)
    recent_vols = [d['cross_vol'] for d in cv_data]
    avg_vol = sum(recent_vols) / len(recent_vols)  # 近期均值（目前5天）

    # ── 评分：按截面波动率均值 ──
    if avg_vol < 1.5:   score, grade, emoji = 15, '极低', '🔴'   # 几乎无分化
    elif avg_vol < 2.0: score, grade, emoji = 35, '偏低', '🟠'   # 分化不足
    elif avg_vol < 2.5: score, grade, emoji = 55, '中等', '🟡'   # 一般
    elif avg_vol < 3.0: score, grade, emoji = 75, '偏高', '🟢'   # alpha友好
    elif avg_vol < 4.0: score, grade, emoji = 90, '高', '🟢'     # 非常好
    else:               score, grade, emoji = 85, '极高', '🟢'   # 极高可能伴随恐慌，微扣

    # ── 趋势：离散度在扩大还是收敛 ──
    if len(recent_vols) >= 3:
        t_r = sum(recent_vols[-2:]) / 2       # 近2天均值
        t_e = sum(recent_vols[:2]) / max(len(recent_vols[:2]), 1)  # 早期2天均值
        trend = '扩大' if t_r > t_e * 1.1 else ('收敛' if t_r < t_e * 0.9 else '平稳')
    else:
        trend = '数据不足'

    signals = [
        f'截面波动率={avg_vol:.2f} ({grade})',
        f'最新={vol:.2f} 趋势{trend}',
    ]

    return {
        'score': score, 'grade': grade, 'emoji': emoji,
        'cross_vol': round(avg_vol, 2), 'latest_vol': round(vol, 2),
        'trend': trend, 'signals': signals
    }


# ═══════════════════════════════════════
# Factor ③ 风格集中度
# ═══════════════════════════════════════
# 【逻辑】
# 两层判断：
#   A. 静态HHI — 当前分布是否均匀（截面）
#   B. 动态迁移速度 — 各风格占比的变化率（时序）
#
# 关键洞察（Roni 2026-03-01）：
# 截面看着均匀不代表安全！比如今天各占20%~30%，
# 但科创可能是两天从15%→30%飙上来的。
# 这种剧烈的流动性迁移 = 资金涌入单一风格 → 其他被抽水 → 超额炸。
#
# 所以：
# - 静态HHI正常 + 迁移平缓 → 安全
# - 静态HHI正常 + 迁移剧烈 → 危险！（截面看不出来）
# - 静态HHI集中 + 迁移剧烈 → 非常危险
#
# 与离散度是交互项：
# - 离散度高 + 分散且稳 = 最佳
# - 离散度高 + 分散但迁移快 = 有空间但不稳
# - 离散度低 = 不管怎样都难做
# ═══════════════════════════════════════
def calc_style_concentration():
    shares = qs_data.get('index_share', [])
    if not shares:
        return {'score': 50, 'grade': '数据缺失', 'emoji': '⚪',
                'hhi': None, 'dominant': None, 'signals': ['数据缺失'],
                'migration': None}

    style_keys = ['沪深300', '中证500', '中证1000', '中证2000', '科创+创业板']

    # ═══ A. 静态HHI（当前截面） ═══
    recent = shares[-5:] if len(shares) >= 5 else shares
    avg_shares = {}
    for k in style_keys:
        vals = [d.get(k, 0) for d in recent if k in d]
        avg_shares[k] = sum(vals) / max(len(vals), 1)

    total = sum(avg_shares.values())
    if total == 0:
        return {'score': 50, 'grade': '数据异常', 'emoji': '⚪',
                'hhi': None, 'dominant': None, 'signals': ['合计为0'],
                'migration': None}

    norm = {k: v / total for k, v in avg_shares.items()}
    hhi = sum(v ** 2 for v in norm.values())

    dominant_style = max(avg_shares, key=avg_shares.get)
    dominant_pct = avg_shares[dominant_style]

    # ═══ B. 动态迁移速度（5日 vs 20日均值 Δpp） ═══
    #
    # 【数据来源】quant_stock_data.py → index_share
    #   每日计算 5 个宽基板块各自的成交额占中证全指(000985.CSI)的百分比：
    #     沪深300      = 000300.SH amount / 全A amount × 100
    #     中证500      = 000905.SH / 全A × 100
    #     中证1000     = 000852.SH / 全A × 100
    #     中证2000     = 932000.CSI / 全A × 100
    #     科创+创业板  = (000688.SH + 399006.SZ) / 全A × 100
    #
    # 【算法】
    #   对每个风格 k:
    #     avg_5  = 近5个交易日的占比均值
    #     avg_20 = 近20个交易日的占比均值
    #     Δ(k)   = avg_5 − avg_20  （单位: pp，百分点）
    #       Δ > 0 → 该风格近期占比增加（资金涌入）
    #       Δ < 0 → 该风格近期占比缩减（资金流出）
    #   迁移强度 = max(|Δ(k)|)，即变化最剧烈的那个风格
    #
    # 【阈值】
    #   max_delta < 2pp  → 平缓（正常轮动，安全）         score=10
    #   2~3pp            → 温和（风格切换中，需注意）       score=30
    #   3~5pp            → 快速（明显迁移，超额可能受影响） score=60
    #   > 5pp            → 剧烈（资金大搬家，超额大概率受损）score=90
    #
    # 【关键洞察 Roni 2026-03-01】
    #   截面看着均匀不代表安全！科创可能两天从15%→30%飙上来。
    #   剧烈的流动性迁移 = 资金涌入单一风格 → 其他被抽水 → 超额炸。
    #   所以此指标与静态 HHI 搭配使用：
    #     HHI正常 + 迁移平缓 → 安全 ✅
    #     HHI正常 + 迁移剧烈 → 截面看不出但危险 ⚠️
    #     HHI集中 + 迁移剧烈 → 非常危险 🔴
    migration = {
        'deltas': {},           # 每个风格的占比变化量(pp)
        'max_mover': None,      # 变化最大的风格名
        'max_delta': 0,         # 最大变化量(pp)
        'intensity': '平缓',   # 平缓/温和/剧烈
        'intensity_score': 0,   # 0-100，越高越危险
        'history': [],          # 近20日每日各风格占比（给前端画图用）
    }

    if len(shares) >= 20:
        recent_5 = shares[-5:]
        recent_20 = shares[-20:]

        for k in style_keys:
            avg_5 = sum(d.get(k, 0) for d in recent_5) / 5
            avg_20 = sum(d.get(k, 0) for d in recent_20) / 20
            delta = avg_5 - avg_20  # 正=占比增加，负=占比减少
            migration['deltas'][k] = round(delta, 2)

        # 找到变化最剧烈的风格
        abs_deltas = {k: abs(v) for k, v in migration['deltas'].items()}
        max_mover = max(abs_deltas, key=abs_deltas.get)
        max_delta = abs_deltas[max_mover]
        migration['max_mover'] = max_mover
        migration['max_delta'] = round(max_delta, 2)
        migration['max_delta_signed'] = migration['deltas'][max_mover]

        # 迁移强度判断
        # < 2pp = 正常轮动
        # 2~5pp = 风格切换中，需注意
        # > 5pp = 剧烈迁移，超额大概率受损
        if max_delta < 2:
            migration['intensity'] = '平缓'
            migration['intensity_score'] = 10
        elif max_delta < 3:
            migration['intensity'] = '温和'
            migration['intensity_score'] = 30
        elif max_delta < 5:
            migration['intensity'] = '快速'
            migration['intensity_score'] = 60
        else:
            migration['intensity'] = '剧烈'
            migration['intensity_score'] = 90

        # 近20日每日占比数据（给前端子图表用）
        history_window = shares[-20:] if len(shares) >= 20 else shares
        for d in history_window:
            row = {'date': d.get('date', '')}
            for k in style_keys:
                row[k] = d.get(k, 0)
            migration['history'].append(row)

    elif len(shares) >= 5:
        # 数据不够20天，用有的算
        for k in style_keys:
            first_val = shares[0].get(k, 0)
            last_val = shares[-1].get(k, 0)
            migration['deltas'][k] = round(last_val - first_val, 2)
        abs_deltas = {k: abs(v) for k, v in migration['deltas'].items()}
        max_mover = max(abs_deltas, key=abs_deltas.get)
        migration['max_mover'] = max_mover
        migration['max_delta'] = round(abs_deltas[max_mover], 2)
        migration['max_delta_signed'] = migration['deltas'][max_mover]
        migration['intensity'] = '数据有限'
        migration['intensity_score'] = 0

    # ═══ 因子极端演绎检查 ═══
    factors = qs_data.get('factor', [])
    factor_extremes = []
    if len(factors) >= 10:
        recent_f = factors[-5:]
        early_f = factors[-10:-5]
        for fn in qs_data.get('factor_names', []):
            r_avg = sum(d.get(fn, 1) for d in recent_f) / 5
            e_avg = sum(d.get(fn, 1) for d in early_f) / 5
            chg = (r_avg / e_avg - 1) * 100 if e_avg else 0
            if abs(chg) > 2:
                factor_extremes.append(f'{fn}{"↑" if chg > 0 else "↓"}{abs(chg):.1f}%')

    # ═══ 综合评分：静态HHI + 动态迁移 ═══
    # 先按HHI给基础分
    if hhi <= 0.22:   hhi_score = 90
    elif hhi <= 0.25: hhi_score = 70
    elif hhi <= 0.28: hhi_score = 55
    elif hhi <= 0.32: hhi_score = 35
    else:             hhi_score = 15

    # 迁移速度扣分
    # intensity_score: 10=平缓, 30=温和, 60=快速, 90=剧烈
    migration_penalty = 0
    mi = migration['intensity_score']
    if mi >= 60:
        migration_penalty = 20  # 快速/剧烈迁移，大扣
    elif mi >= 30:
        migration_penalty = 8   # 温和迁移，小扣

    # 因子极端演绎扣分
    factor_penalty = 5 * len(factor_extremes) if factor_extremes else 0

    score = max(0, min(100, hhi_score - migration_penalty - factor_penalty))

    # 综合等级（结合静态+动态）
    if score >= 75:   grade, emoji = '分散稳定', '🟢'
    elif score >= 55: grade, emoji = '较分散', '🟢'
    elif score >= 40: grade, emoji = '有迁移', '🟡'
    elif score >= 25: grade, emoji = '快速迁移', '🟠'
    else:             grade, emoji = '剧烈迁移', '🔴'

    # ═══ 信号 ═══
    signals = [
        f'HHI={hhi:.3f} | 主导: {dominant_style} {dominant_pct:.1f}%',
    ]
    # 迁移信号（最重要的一句话，会显示在顶部因子卡片里）
    mm = migration.get('max_mover')
    md = migration.get('max_delta_signed', 0)
    if mm and abs(md) >= 2:
        direction = '↑' if md > 0 else '↓'
        signals.append(f'⚠️ {mm}{direction}{abs(md):.1f}pp ({migration["intensity"]})')
    else:
        signals.append(f'迁移{migration["intensity"]}，最大变化{mm} {md:+.1f}pp')

    if factor_extremes:
        signals.append(f'因子极致: {", ".join(factor_extremes)}')

    ss_sigs = style_sig.get('signals', [])
    crowded = [s for s in ss_sigs if '拥挤' in s]
    if crowded:
        signals.append(crowded[0])

    return {
        'score': score, 'grade': grade, 'emoji': emoji,
        'hhi': round(hhi, 4), 'hhi_score': hhi_score,
        'dominant': dominant_style, 'dominant_pct': round(dominant_pct, 1),
        'migration': migration,
        'factor_extremes': factor_extremes,
        'shares': {k: round(v, 1) for k, v in avg_shares.items()},
        'signals': signals
    }


# ═══════════════════════════════════════
# Factor ④ 市场预期（原"基差成本"）
# ═══════════════════════════════════════
# 【逻辑】（Roni 关键洞察）
# 基差是结果变量，不是原因。不能看到贴水就说"成本高"。
# 必须用历史分位数定位当前基差处于什么水平。
#
# 升水时不直接扣分！要验证"大票虹吸"三条件：
#   A. 大票(300+500)成交额占比急增（5日vs20日 >2pp）
#   B. 大票涨幅跑赢小票（300 vs 1000 >2%）
#   C. 基差升水或处于高分位(>80%)
# 三条件同时满足 → 确认虹吸 → 超额承压
# 仅升水但没虹吸 → 不调整
#
# 【为什么升水+虹吸=超额差】
# 量化1000指增实际持仓约30%在样本外，偏小票，
# 赚的是流动性溢价和动量的钱。
# 大票吸走流动性 + 小票相对跑输 = 量化持仓端被碾压。
# ═══════════════════════════════════════
def calc_market_expectation():
    basis = qs_data.get('basis', [])
    if not basis:
        return {'score': 50, 'grade': '数据缺失', 'emoji': '⚪',
                'im_basis': None, 'signals': ['基差数据缺失']}

    latest = basis[-1]
    im = latest.get('IM', 0)       # IM（中证1000）年化基差%
    ic = latest.get('IC', 0)       # IC（中证500）
    if_b = latest.get('IF', 0)     # IF（沪深300）

    # ── 历史分位数：当前IM在全部历史中的位置 ──
    im_hist = [d.get('IM', 0) for d in basis]
    im_sorted = sorted(im_hist)
    n = len(im_sorted)
    rank = sum(1 for x in im_sorted if x <= im)
    pctile = rank / n * 100 if n > 0 else 50  # 分位数(0~100)

    # 近5日均值
    im_5d = im_hist[-5:] if len(im_hist) >= 5 else im_hist
    im_avg5 = sum(im_5d) / len(im_5d)

    # ── 大票虹吸三条件验证（仅在升水/高分位时触发） ──
    siphon_confirmed = False
    siphon_details = {}

    shares = qs_data.get('index_share', [])
    is_premium = im > 0 or pctile > 80  # 触发条件：升水或处于历史高分位

    if is_premium and len(shares) >= 20:
        # 条件A：大票成交额占比急增
        # 300+500 近5日占比均值 vs 近20日均值，差值>2个百分点
        recent_5 = shares[-5:]
        recent_20 = shares[-20:]
        big_5d = sum(d.get('沪深300', 0) + d.get('中证500', 0) for d in recent_5) / 5
        big_20d = sum(d.get('沪深300', 0) + d.get('中证500', 0) for d in recent_20) / 20
        share_surge = big_5d - big_20d  # 正值=大票占比增加

        # 条件B：大票涨幅跑赢小票
        # 沪深300近5日涨幅 vs 中证1000近5日涨幅，差值>2%
        ret_300 = _calc_index_return('000300.SH', 5)
        ret_1000 = _calc_index_return('000852.SH', 5)
        big_outperform = None
        if ret_300 is not None and ret_1000 is not None:
            big_outperform = ret_300 - ret_1000  # 正值=大票跑赢

        siphon_details = {
            'big_share_5d': round(big_5d, 1),
            'big_share_20d': round(big_20d, 1),
            'share_surge': round(share_surge, 1),
            'ret_300_5d': round(ret_300, 2) if ret_300 is not None else None,
            'ret_1000_5d': round(ret_1000, 2) if ret_1000 is not None else None,
            'big_outperform': round(big_outperform, 2) if big_outperform is not None else None,
        }

        # 条件C：升水/高分位（已满足 is_premium）
        # 三条件联合判断
        cond_a = share_surge > 2.0       # 大票占比增加超2pp
        cond_b = big_outperform is not None and big_outperform > 2.0  # 大票跑赢超2%
        cond_c = True                     # is_premium 已满足

        siphon_confirmed = cond_a and cond_b and cond_c

    # ── 评分 ──
    score = 60  # 默认中性

    if siphon_confirmed:
        # 三条件全满足：大票虹吸确认，超额大概率走差
        score = 20
        grade = '大票虹吸'
        emoji = '🔴'
    elif is_premium:
        # 升水/高分位但虹吸未确认：需观察，暂不调整
        score = 50
        grade = '升水观察'
        emoji = '🟡'
    elif pctile < 10:
        # 极端贴水：市场极度悲观，超额波动可能加大
        score = 45
        grade = '极端悲观'
        emoji = '🟠'
    elif pctile < 30:
        score = 55
        grade = '偏悲观'
        emoji = '🟡'
    elif pctile < 70:
        # 正常区间：对超额没什么影响
        score = 65
        grade = '正常'
        emoji = '🟢'
    else:
        score = 55
        grade = '偏乐观'
        emoji = '🟡'

    signals = [
        f'IM基差: {im:+.2f}% (历史分位{pctile:.0f}%)',
        f'IC: {ic:+.2f}% | IF: {if_b:+.2f}%',
    ]
    if siphon_confirmed:
        sd = siphon_details
        signals.append(f'🚨 大票虹吸: 占比+{sd["share_surge"]:.1f}pp, 300跑赢1000达{sd["big_outperform"]:.1f}%')
    elif is_premium and siphon_details:
        sd = siphon_details
        signals.append(f'升水但虹吸未确认 (占比差{sd["share_surge"]:+.1f}pp)')

    return {
        'score': max(0, min(100, score)), 'grade': grade, 'emoji': emoji,
        'im_basis': round(im, 2), 'im_pctile': round(pctile, 1),
        'im_avg5': round(im_avg5, 2),
        'ic_basis': round(ic, 2), 'if_basis': round(if_b, 2),
        'siphon_confirmed': siphon_confirmed,
        'siphon_details': siphon_details if siphon_details else None,
        'signals': signals
    }


# ═══════════════════════════════════════
# Factor ⑤ 微观结构
# ═══════════════════════════════════════
# 【逻辑】
# 行业拥挤度高 + 资金面偏空 = 踩踏风险
# 量化在踩踏中首先被止损（程序化止损触发快于人工）
# 看三个维度：
# - 拥挤行业数量（越多越危险）
# - 追高风险行业数量（近期涨幅大+资金涌入）
# - 三资金面共识（北向+两融+ETF 的合力方向）
# ═══════════════════════════════════════
def calc_micro_risk():
    heatmap = crowding.get('industry_heatmap', [])
    three_flows = crowding.get('three_flows', {})
    consensus = three_flows.get('consensus', '') if isinstance(three_flows, dict) else ''

    # 拥挤度信号列表
    crowd_signal = crowding.get('crowding_signal', {})
    if isinstance(crowd_signal, dict):
        sig_list = crowd_signal.get('signals', [])
    elif isinstance(crowd_signal, str):
        sig_list = [crowd_signal]
    else:
        sig_list = []

    hot_count = cold_count = chase_risk = total_industries = 0

    if isinstance(heatmap, list):
        total_industries = len(heatmap)
        for ind in heatmap:
            cl = ind.get('crowd_label', '') or ''
            sig = ind.get('signal', '') or ''
            tags_str = str(ind.get('tags', '') or '')
            if cl == 'hot' or '拥挤' in tags_str:
                hot_count += 1
            if cl == 'cold' or '冷清' in tags_str:
                cold_count += 1
            if '追高' in (sig or ''):
                chase_risk += 1

    # ── 评分 ──
    score = 80  # 基准分

    # 拥挤行业越多越危险
    if hot_count > 10:   score -= 30
    elif hot_count > 7:  score -= 20
    elif hot_count > 4:  score -= 10

    # 每个追高行业扣5分
    score -= chase_risk * 5

    # 资金面共识
    if '偏空' in consensus:   score -= 15  # 偏空+拥挤=踩踏风险最高
    elif '分歧' in consensus: score -= 5
    elif '偏多' in consensus: score += 5   # 偏多时拥挤不一定危险

    score = max(0, min(100, score))

    if score >= 70:   grade, emoji = '健康', '🟢'
    elif score >= 45: grade, emoji = '有压力', '🟡'
    elif score >= 25: grade, emoji = '风险偏高', '🟠'
    else:             grade, emoji = '踩踏预警', '🔴'

    signals = []
    if total_industries:
        signals.append(f'拥挤行业: {hot_count}/{total_industries} 冷清: {cold_count}')
    if chase_risk:
        signals.append(f'⚠️ {chase_risk}个行业追高风险')
    if consensus:
        signals.append(f'资金面共识: {consensus}')
    for s in sig_list[:2]:
        signals.append(s)

    return {
        'score': score, 'grade': grade, 'emoji': emoji,
        'hot_count': hot_count, 'cold_count': cold_count,
        'chase_risk': chase_risk, 'consensus': consensus,
        'signals': signals
    }


# ═══════════════════════════════════════
# 中性策略辅助模块
# ═══════════════════════════════════════
# 【逻辑】（Roni 指导）
# 中性策略 = 超额收益 - 对冲成本（基差）
# - 超额 < 基差 → 亏钱
# - 超额 = 基差 → 盈亏平衡
# - 超额 > 基差 → 有正收益
# - 超额 ≥ 2×基差 → 才有配置价值（覆盖波动/回撤/费用等摩擦成本）
#
# 注意：这只是辅助模块，主体是超额环境诊断
# ═══════════════════════════════════════
def calc_neutral_aux():
    """中性辅助：超额年化 vs 基差年化 → 比值判断配置价值"""
    result = {'available': False}

    # 从产品净值推算超额年化
    fund = fund_nav.get('fund', {})
    chart = fund.get('chart', {})
    dates = chart.get('dates', [])
    excess = chart.get('excess', [])  # 累计超额序列（如0.3164=31.64%）

    if len(dates) < 10 or len(excess) < 10:
        result['reason'] = '产品净值数据不足'
        return result

    # 近3个月年化（约13个周频点）
    latest_excess = excess[-1]
    lookback = min(13, len(excess) - 1)
    prev_excess = excess[-(lookback + 1)]
    period_excess = latest_excess - prev_excess        # 期间超额
    annualized_excess = period_excess / lookback * 52 * 100  # 周频→年化%

    # 基差年化成本：IM贴水（负值=成本）
    basis = qs_data.get('basis', [])
    if not basis:
        result['reason'] = '基差数据缺失'
        return result

    im = basis[-1].get('IM', 0)
    basis_annual_cost = abs(im)  # 取绝对值作为对冲成本

    # ── 比值判断 ──
    if basis_annual_cost > 0.01:
        ratio = annualized_excess / basis_annual_cost
    else:
        ratio = float('inf') if annualized_excess > 0 else 0

    # 配置价值判断
    if ratio >= 2:
        verdict = '有配置价值'          # 超额≥2×基差，覆盖摩擦后仍有充足收益
        verdict_emoji = '✅'
    elif ratio >= 1:
        verdict = '有正收益，但配置价值不足'  # 超额>基差，正收益但不够覆盖风险
        verdict_emoji = '🟡'
    elif annualized_excess > basis_annual_cost:
        verdict = '微幅正收益'
        verdict_emoji = '🟡'
    else:
        verdict = '中性亏钱'            # 超额<基差，对冲后亏损
        verdict_emoji = '❌'

    result = {
        'available': True,
        'excess_annual_pct': round(annualized_excess, 2),
        'basis_annual_cost_pct': round(basis_annual_cost, 2),
        'ratio': round(ratio, 2) if ratio != float('inf') else 'inf',
        'verdict': verdict,
        'verdict_emoji': verdict_emoji,
        'im_current': round(im, 2),
        'lookback_weeks': lookback,
        'note': f'超额年化{annualized_excess:.1f}% vs 基差成本{basis_annual_cost:.1f}% = {ratio:.1f}x → {verdict}'
    }
    return result


# ═══════════════════════════════════════
# 综合诊断（嵌套逻辑）
# ═══════════════════════════════════════
# 【嵌套，不是加权！】
# Step 1: 流动性门槛 — 枯竭直接出局
# Step 2: 离散度 × 集中度 — 交互项，决定alpha环境基调
# Step 3: 市场预期修正 — 条件验证，不粗暴扣分
# Step 4: 微观尾部叠加 — 踩踏预警红旗
# ═══════════════════════════════════════
def diagnose(liq, disp, conc, mkt, micro):
    factors_detail = {
        '流动性': liq,
        '离散度': disp,
        '风格集中度': conc,
        '市场预期': mkt,
        '微观结构': micro,
    }

    # ── Step 1: 流动性前提 ──
    # 枯竭=没水，量化活不了，不用看其他因子
    if liq['score'] < 30:
        env_score = 15
        narrative = f"⛔ 流动性枯竭（{liq['amount']:.0f}亿），量化生存环境恶劣"
        return build_result(env_score, '防御', '🔴', narrative, factors_detail)

    # ── Step 2: 离散度 × 风格集中度（交互项） ──
    # 这两个因子不是独立的！组合才有意义：
    d, c = disp['score'], conc['score']

    if d >= 65 and c >= 65:
        # 离散度高 + 风格分散 = 最佳环境
        alpha_env, alpha_label = 90, '极佳'
        alpha_note = f"离散度{disp['grade']}+风格{conc['grade']}，alpha空间充裕"
    elif d >= 65 and c < 45:
        # 离散度高但风格集中 = 有空间但alpha不稳
        # （某风格独涨时，量化的多因子分散逻辑可能失效）
        alpha_env, alpha_label = 55, '不稳定'
        alpha_note = f"离散度{disp['grade']}但{conc['dominant']}主导({conc['dominant_pct']:.0f}%)，alpha可能被风格碾压"
    elif d < 40:
        # 离散度低 = 不管集中不集中，alpha都难做
        alpha_env, alpha_label = 25, '困难'
        alpha_note = f"离散度{disp['grade']}(波动率{disp.get('cross_vol','?')})，同涨同跌选股难"
    else:
        # 中间状态：加权
        alpha_env = d * 0.6 + c * 0.4
        alpha_label = '中等'
        alpha_note = f"离散度{disp['grade']}+风格{conc['grade']}，超额环境一般"

    # ── Step 3: 市场预期修正 ──
    # 不粗暴扣分，只有虹吸确认才降级
    mkt_adj = 0
    mkt_note = ''
    if mkt.get('siphon_confirmed'):
        # 三条件全满足：大票虹吸确认
        mkt_adj = -15
        sd = mkt.get('siphon_details', {})
        mkt_note = f"🚨 大票虹吸确认(占比+{sd.get('share_surge',0):.1f}pp+跑赢{sd.get('big_outperform',0):.1f}%)，超额承压"
    elif mkt['grade'] == '升水观察':
        mkt_adj = 0  # 升水但没虹吸证据，暂不调整
        mkt_note = f"升水但虹吸未确认，暂不调整"
    elif mkt['grade'] == '极端悲观':
        mkt_adj = -3  # 极端贴水时超额波动可能加大
        mkt_note = f"极端贴水(分位{mkt.get('im_pctile',0):.0f}%)，超额波动可能加大"
    else:
        mkt_note = f"市场预期{mkt['grade']}(IM分位{mkt.get('im_pctile',0):.0f}%)"

    # ── Step 4: 微观尾部叠加 ──
    micro_adj = 0
    micro_note = ''
    if micro['score'] < 30:
        micro_adj = -12  # 踩踏预警，大幅降级
        micro_note = f"🚨 踩踏预警！{micro['hot_count']}行业拥挤+资金{micro['consensus']}"
    elif micro['score'] < 50:
        micro_adj = -5   # 有压力，小幅降级
        micro_note = f"微观有压力（{micro['hot_count']}行业拥挤）"
    else:
        micro_note = f"微观{micro['grade']}"

    # ── 综合评分 ──
    # 权重：流动性25% + alpha环境50% + 市场预期10% + 微观15%
    raw = liq['score'] * 0.25 + alpha_env * 0.50 + mkt['score'] * 0.10 + micro['score'] * 0.15
    env_score = max(0, min(100, round(raw + mkt_adj + micro_adj)))

    # 构建诊断叙事（用箭头串联每一步逻辑）
    parts = [
        f"流动性{liq['grade']}({liq['amount']:.0f}亿，{liq['trend']}，{liq['stability']})",
        alpha_note, mkt_note, micro_note
    ]
    narrative = ' → '.join(p for p in parts if p)

    if env_score >= 75:   env_grade, env_emoji = '进攻', '🟢'
    elif env_score >= 55: env_grade, env_emoji = '均衡', '🟡'
    elif env_score >= 40: env_grade, env_emoji = '谨慎', '🟠'
    else:                 env_grade, env_emoji = '防御', '🔴'

    return build_result(env_score, env_grade, env_emoji, narrative, factors_detail,
                        alpha_env=alpha_env, alpha_label=alpha_label)


def build_result(score, grade, emoji, narrative, factors, alpha_env=None, alpha_label=None):
    """组装最终输出JSON"""
    result = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'env_score': score,
        'env_grade': grade,
        'env_emoji': emoji,
        'narrative': narrative,
        'alpha_environment': {
            'score': alpha_env, 'label': alpha_label,
        } if alpha_env is not None else None,
        'factors': {}
    }
    for name, data in factors.items():
        entry = {
            'score': data['score'], 'grade': data['grade'],
            'emoji': data['emoji'], 'signals': data.get('signals', []),
        }
        extra_keys = [
            'amount', 'trend', 'stability', 'cv',
            'cross_vol', 'latest_vol',
            'hhi', 'dominant', 'dominant_pct', 'factor_extremes', 'shares',
            'im_basis', 'im_pctile', 'im_avg5', 'ic_basis', 'if_basis',
            'siphon_confirmed', 'siphon_details',
            'hot_count', 'cold_count', 'chase_risk', 'consensus',
            'migration', 'hhi_score',
        ]
        for k in extra_keys:
            if k in data:
                entry[k] = data[k]
        result['factors'][name] = entry
    return result


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════
if __name__ == '__main__':
    print('📊 量化宽基超额环境诊断 v2')
    print('=' * 55)

    liq   = calc_liquidity()
    disp  = calc_dispersion()
    conc  = calc_style_concentration()
    mkt   = calc_market_expectation()
    micro = calc_micro_risk()

    print(f'  ① 流动性:     {liq["emoji"]} {liq["score"]:3d} {liq["grade"]}')
    print(f'  ② 离散度:     {disp["emoji"]} {disp["score"]:3d} {disp["grade"]}')
    print(f'  ③ 风格集中度: {conc["emoji"]} {conc["score"]:3d} {conc["grade"]}')
    print(f'  ④ 市场预期:   {mkt["emoji"]} {mkt["score"]:3d} {mkt["grade"]}')
    print(f'  ⑤ 微观结构:   {micro["emoji"]} {micro["score"]:3d} {micro["grade"]}')
    print('=' * 55)

    result = diagnose(liq, disp, conc, mkt, micro)
    print(f'\n  综合: {result["env_emoji"]} {result["env_score"]} — {result["env_grade"]}')
    print(f'  诊断: {result["narrative"]}')

    # 中性辅助
    neutral = calc_neutral_aux()
    result['neutral_aux'] = neutral
    if neutral.get('available'):
        print(f'\n  📎 中性辅助: {neutral["note"]}')
    else:
        print(f'\n  📎 中性辅助: 不可用 ({neutral.get("reason","")})')

    out_path = os.path.join(BASE, 'quant_env_diag.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'\n✅ 输出 → {out_path}')
