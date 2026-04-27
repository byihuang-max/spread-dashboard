#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meme反身性信号计算器 (calc_meme.py)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【反身性理论（索罗斯）】

  正常市场：基本面 → 价格
  反身性市场：叙事 → 价格 → 强化叙事 → 更高价格

  Meme行情 = 反身性的极端体现：
  "故事本身成为基本面" ── 有多少人相信这个故事，比公司值多少钱更重要。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【两个核心指标】

  1. 叙事联动指数 (NLI, Narrative Linkage Index)
     ─────────────────────────────────────────
     来源：rolling_corr.json（30天滚动相关性矩阵）
     算法：取矩阵中所有正值的非对角线元素求均值
           只取正值：负相关代表资产"分化"，不是"联动"
           排除对角线：自相关=1，不算

     信号含义：
       高 → 各资产同涨同跌，同一叙事驱动市场
       低 → 各资产走独立行情，无主导叙事

     注意：恐慌下跌时NLI也会升高（"全面崩跌"也是联动），
           需结合量能加速度（下跌时量放大 vs 上涨时量放大）区分。

  2. 量能加速度 (VA, Volume Acceleration)
     ─────────────────────────────────────────
     算法：近5日均量 / 近30日均量 - 1（每个资产独立计算）
           然后按权重加权平均

     权重分配（反映不同市场对Meme叙事的敏感度）：
       BTC         35%  ← Crypto最先感知叙事情绪，领先指标
       纳斯达克ETF  25%  ← 美国科技板块，全球Meme的主战场
       恒生科技ETF  20%  ← HK科技，中国叙事溢出
       科创50ETF   20%  ← A股科技，本土叙事

     信号含义：
       > +30%  → 量能爆发，参与者激增，叙事在快速扩散
       0~+30%  → 量能温和放大，健康趋势
       < 0     → 量能萎缩，即使价格还在涨也是警惕信号（顶部特征）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【综合Meme信号（0-100分）】

  = 叙事联动历史分位 × 50% + 量能加速度历史分位 × 50%

  分位计算：用过去252个交易日（约1年）的数据
  含义：今天的信号，比过去1年中多少天更强

  阶段判断：
    < 25   🟢 叙事离散期   各走各的，无Meme行情
    25-50  🟡 叙事聚合期   开始联动，观察方向
    50-75  🟠 反身性强化期  正反馈循环建立中
    ≥ 75   🔴 反身性高峰期  极度同步，注意尾部风险

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime


# ────────────────────────────────────────────────
# 量能加速度权重配置
# ────────────────────────────────────────────────
VOL_WEIGHTS = {
    'BTC':              0.35,  # Crypto，对叙事最敏感，往往最先反应
    '纳斯达克ETF(QQQ)': 0.25,  # 美国科技，全球Meme主战场
    '恒生科技ETF':       0.20,  # 港股科技
    '科创50ETF':        0.20,  # A股科技
}

# 量能加速度计算窗口
SHORT_WINDOW = 5   # 近5日（约1周），捕捉短期热度
LONG_WINDOW  = 30  # 近30日（约1月），作为基准

# 历史分位计算窗口（交易日）
LOOKBACK = 252  # 约1年


# ────────────────────────────────────────────────
# 叙事联动指数
# ────────────────────────────────────────────────

def calc_narrative_linkage(corr_matrices):
    """
    计算叙事联动指数（NLI）的历史时间序列

    输入：corr_matrices dict → {日期: {资产A: {资产B: 相关系数}}}
    输出：{日期: NLI值(0~1)} 字典

    算法细节：
    - 相关性矩阵是对称的，只取上三角（i < j），避免重复计数
    - 只累加正相关：负相关是"分化"，不贡献联动分数
    - 如果市场全是负相关（极罕见），NLI=0
    """
    nli_series = {}

    for date_str, matrix in corr_matrices.items():
        assets = list(matrix.keys())
        positive_corrs = []

        for i, a1 in enumerate(assets):
            for j, a2 in enumerate(assets):
                if i >= j:
                    # i >= j：包含对角线(i==j，自相关=1)和下三角(重复)，跳过
                    continue
                v = matrix[a1][a2]
                if v > 0:
                    positive_corrs.append(v)

        nli_series[date_str] = round(float(np.mean(positive_corrs)), 4) if positive_corrs else 0.0

    return nli_series


# ────────────────────────────────────────────────
# 量能加速度
# ────────────────────────────────────────────────

def calc_volume_acceleration(vol_data):
    """
    计算多资产加权量能加速度历史时间序列

    输入：vol_data dict → {资产名: {日期: 成交量}}
    输出：{日期: 加权VA值} 字典

    计算步骤：
    1. 每个资产按日期构建时间序列，ffill填充节假日空值
    2. 计算5日均量 / 30日均量 - 1（= 当前热度 vs 基准线）
    3. 只用有VOL_WEIGHTS定义的资产
    4. 按权重加权均值（若某资产当日无有效数据，自动归一化其余权重）
    """

    # 只处理有权重定义且有数据的资产
    available = {k: vol_data[k] for k in VOL_WEIGHTS if k in vol_data}
    if not available:
        print("  ⚠️ 无量能数据（需先运行 fetch_data.py）")
        return {}

    # 构建 DataFrame，日期为索引
    df = pd.DataFrame({k: pd.Series(v) for k, v in available.items()})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.ffill()  # 用前值填充节假日（不是零成交，是市场没开）

    # 对每个资产计算量能加速度序列
    va_dict = {}
    for asset in available:
        s = df[asset].dropna()
        # 短期均量（5日）
        short_avg = s.rolling(SHORT_WINDOW, min_periods=SHORT_WINDOW).mean()
        # 长期均量（30日，作为"正常水平"基准）
        long_avg  = s.rolling(LONG_WINDOW,  min_periods=LONG_WINDOW).mean()
        # 加速度 = 短期/长期 - 1，正值=放量，负值=缩量
        va_dict[asset] = (short_avg / long_avg - 1).replace([np.inf, -np.inf], np.nan)

    va_df = pd.DataFrame(va_dict).dropna(how='all')

    # 按权重加权均值
    weighted_va = {}
    for date in va_df.index:
        row = va_df.loc[date]
        # 只取当日有有效值的资产
        valid = {k: float(v) for k, v in row.items() if not np.isnan(v) and k in VOL_WEIGHTS}
        if not valid:
            continue
        # 权重归一化（缺失资产的权重分给其他资产）
        total_w = sum(VOL_WEIGHTS[k] for k in valid)
        wa = sum(VOL_WEIGHTS[k] * v for k, v in valid.items()) / total_w
        weighted_va[date.strftime('%Y-%m-%d')] = round(wa, 4)

    return weighted_va


# ────────────────────────────────────────────────
# 历史分位
# ────────────────────────────────────────────────

def to_percentile_series(series_dict, lookback=LOOKBACK):
    """
    将时间序列的每个点转换为历史百分位（0-100）

    输入：{日期: 数值}
    输出：{日期: 百分位(0-100)}

    算法：对每个日期，取过去lookback天的窗口数据，
          计算今天的值在这个窗口里排在第几位（百分比）

    用途：把NLI和VA转换成"今天比过去1年中多少天更高"，
          使两个量纲不同的指标可以放在一起加权。
    """
    dates  = sorted(series_dict.keys())
    values = [series_dict[d] for d in dates]
    s = pd.Series(values, index=pd.to_datetime(dates))

    percentiles = {}
    for i, date in enumerate(s.index):
        start_i = max(0, i - lookback)
        window = s.iloc[start_i: i + 1].dropna()
        if len(window) < 2:
            # 数据不足时给中性值50，避免过早触发信号
            percentiles[date.strftime('%Y-%m-%d')] = 50.0
        else:
            pct = float((window <= window.iloc[-1]).mean() * 100)
            percentiles[date.strftime('%Y-%m-%d')] = round(pct, 1)

    return percentiles


# ────────────────────────────────────────────────
# 阶段判断
# ────────────────────────────────────────────────

def get_phase(score):
    """
    根据综合Meme信号分数（0-100）判断当前市场阶段

    分数含义：今天的信号，比过去1年中多少天更强
    """
    if score >= 75:
        return {
            'level': 4,
            'label': '反身性高峰期',
            'emoji': '🔴',
            'desc':  '极度叙事同步。正反馈循环达到顶点，注意尾部风险和循环破裂信号（量能开始萎缩即警报）'
        }
    elif score >= 50:
        return {
            'level': 3,
            'label': '反身性强化期',
            'emoji': '🟠',
            'desc':  '正反馈循环建立中。可参与趋势，但控制仓位，设置止损'
        }
    elif score >= 25:
        return {
            'level': 2,
            'label': '叙事聚合期',
            'emoji': '🟡',
            'desc':  '各资产开始联动。关注叙事方向（是风险偏好还是避险），量能是否持续放大'
        }
    else:
        return {
            'level': 1,
            'label': '叙事离散期',
            'emoji': '🟢',
            'desc':  '市场各走各的，无主导叙事。适合选股/选策略，不适合做方向性博弈'
        }


# ────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────

def main():
    print("📊 开始计算Meme反身性信号...\n")

    # ── 读取数据 ──────────────────────────────────
    with open('rolling_corr.json', 'r', encoding='utf-8') as f:
        corr_data = json.load(f)

    with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
        nav_file = json.load(f)

    vol_data = nav_file.get('vol_data', {})
    print(f"  成交量数据可用资产：{list(vol_data.keys())}")
    print(f"  相关性矩阵日期数：{len(corr_data['corr_matrices'])}\n")

    # ── Step 1：叙事联动指数 ──────────────────────
    print("① 计算叙事联动指数（NLI）...")
    nli       = calc_narrative_linkage(corr_data['corr_matrices'])
    nli_pct   = to_percentile_series(nli)
    latest_nli     = list(nli.values())[-1]
    latest_nli_pct = list(nli_pct.values())[-1]
    print(f"  当前NLI: {latest_nli:.3f}（历史 {latest_nli_pct:.0f}% 分位）")

    # ── Step 2：量能加速度 ────────────────────────
    print("\n② 计算多资产加权量能加速度（VA）...")
    print(f"  权重：{ {k: f'{v*100:.0f}%' for k, v in VOL_WEIGHTS.items()} }")
    va = calc_volume_acceleration(vol_data)

    if va:
        va_pct         = to_percentile_series(va)
        latest_va      = list(va.values())[-1]
        latest_va_pct  = list(va_pct.values())[-1]
        print(f"  当前VA: {latest_va*100:+.1f}%（历史 {latest_va_pct:.0f}% 分位）")
    else:
        va_pct        = {}
        latest_va     = None
        latest_va_pct = None
        print("  ⚠️ 量能数据不足，VA设为中性值")

    # ── Step 3：综合Meme信号 ─────────────────────
    print("\n③ 计算综合Meme信号（NLI×50% + VA×50%）...")

    # 取NLI和VA都有分位数据的日期（VA可能比NLI短30天）
    common_dates = sorted(
        set(nli_pct.keys()) &
        (set(va_pct.keys()) if va_pct else set(nli_pct.keys()))
    )

    meme_scores = {}
    for d in common_dates:
        nli_val = nli_pct[d]
        va_val  = va_pct.get(d, 50.0)  # VA缺失时给中性值50
        # 综合信号 = NLI历史分位 × 50% + VA历史分位 × 50%
        meme_scores[d] = round(nli_val * 0.5 + va_val * 0.5, 1)

    # ── 最新状态 ──────────────────────────────────
    latest_date  = sorted(meme_scores.keys())[-1] if meme_scores else None
    latest_score = meme_scores.get(latest_date, 50.0)
    phase        = get_phase(latest_score)

    print(f"\n{'━'*50}")
    print(f"  {phase['emoji']} 当前阶段：{phase['label']}")
    print(f"  综合Meme信号：{latest_score:.0f} 分 / 100")
    print(f"  叙事联动指数：{latest_nli:.3f}（历史 {latest_nli_pct:.0f}% 分位）")
    if latest_va is not None:
        print(f"  量能加速度：  {latest_va*100:+.1f}%（历史 {latest_va_pct:.0f}% 分位）")
    print(f"  {phase['desc']}")
    print(f"{'━'*50}")

    # ── 保存结果 ──────────────────────────────────
    output = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),

        # 当前最新状态（供前端大卡片展示）
        'current': {
            'date':           latest_date,
            'meme_score':     latest_score,
            'phase':          phase,
            'nli':            round(latest_nli, 4),
            'nli_percentile': latest_nli_pct,
            'va':             round(latest_va * 100, 2) if latest_va is not None else None,
            'va_percentile':  latest_va_pct,
        },

        # 历史序列（供前端折线图/柱状图）
        'history': {
            'nli':        nli,         # 叙事联动指数原始值
            'nli_pct':    nli_pct,     # 叙事联动指数历史分位（0-100）
            'va':         va,          # 量能加速度原始值（-1 ~ ∞）
            'va_pct':     va_pct,      # 量能加速度历史分位（0-100）
            'meme_score': meme_scores, # 综合信号（0-100）
        },

        # 权重配置（供前端说明文字使用）
        'vol_weights': VOL_WEIGHTS,
    }

    with open('meme_signal.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存到 meme_signal.json")
    print(f"   历史信号点数：{len(meme_scores)} 天")


if __name__ == '__main__':
    main()
