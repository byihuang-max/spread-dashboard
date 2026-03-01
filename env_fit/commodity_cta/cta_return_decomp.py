#!/usr/bin/env python3
"""CTA产品收益归因：beta贡献 + PCA环境贡献 + 管理人alpha

参照强势股 momentum_return_decomp.py 的框架，针对CTA策略定制：
- Beta基准：南华商品指数（产品净值JSON里已有index_nav）
- 环境因子：PCA友好度（mod1b输出），替代强势股的情绪指标
- 管理人alpha：残差 = 产品收益 - beta贡献 - 环境贡献

归因公式：
  产品日收益 = β × 南华商品日收益 + γ × PCA友好度变化 + α(残差)
  - β：60日滚动OLS回归系数，衡量产品对商品beta的暴露
  - γ：PCA环境对超额收益的解释力
  - α：管理人择时+择品种能力

数据源：
  - fund_nav_cta.json（产品净值+南华商品指数，火富牛已拉好）
  - mod1b_pca_engine.json（PCA友好度时序，本模块已有）
"""

import json, csv, os, math
from datetime import datetime
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
NAV_PATH = os.path.join(os.path.dirname(DIR), '..', 'size_spread', 'fund_nav', 'fund_nav_cta.json')
PCA_PATH = os.path.join(DIR, 'mod1b_pca_engine.json')
VOL_PATH = os.path.join(DIR, 'mod1c_market_vol.json')
OUT_CSV = os.path.join(DIR, 'cta_return_decomp.csv')
OUT_JSON = os.path.join(DIR, 'cta_return_decomp.json')

WINDOW = 60  # rolling OLS window


def ols_beta(y, x):
    """Hand-written OLS: y = a + b*x, return (a, b)"""
    n = len(y)
    if n < 2:
        return 0.0, 1.0
    sx = sum(x)
    sy = sum(y)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    sxx = sum(xi * xi for xi in x)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.0, 1.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a, b


def ols_r2(y, x):
    """R² of simple OLS"""
    n = len(y)
    if n < 3:
        return 0.0
    a, b = ols_beta(y, x)
    y_mean = sum(y) / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - a - b * xi) ** 2 for yi, xi in zip(y, x))
    if ss_tot < 1e-15:
        return 0.0
    return max(0, 1 - ss_res / ss_tot)


def main():
    print("=" * 60)
    print("CTA产品收益归因：beta + PCA环境 + 管理人alpha")
    print("=" * 60)

    # 1. 加载产品净值
    if not os.path.exists(NAV_PATH):
        print(f"❌ 产品净值文件不存在: {NAV_PATH}")
        return
    with open(NAV_PATH) as f:
        nav_data = json.load(f)
    chart = nav_data['fund']['chart']
    dates_nav = chart['dates']       # '2025-01-02' format
    fund_nav = chart['fund_nav']     # 归一化净值
    index_nav = chart['index_nav']   # 南华商品归一化净值

    print(f"  产品: {nav_data['fund'].get('name', 'CTA')}")
    print(f"  基准: 南华商品指数")
    print(f"  数据: {dates_nav[0]} ~ {dates_nav[-1]} ({len(dates_nav)}天)")

    # 2. 加载PCA友好度时序
    pca_map = {}  # date_compact -> pca_friendly
    if os.path.exists(PCA_PATH):
        with open(PCA_PATH) as f:
            pca_data = json.load(f)
        for r in pca_data.get('rolling', []):
            pca_map[r['date']] = {
                'pca_friendly': r['pca_friendly'],
                'pc1_ratio': r['pc1_ratio'],
                'env_type': r['env_type'],
                'momentum_signal': r['momentum_signal'],
            }
        print(f"  PCA数据: {len(pca_map)}天")
    else:
        print(f"  ⚠️ PCA数据不存在，将只做beta归因")

    # 2b. 加载全市场波动率时序
    vol_map = {}  # date_compact -> {avg_vol, vol_quantile, vol_regime, delta_vol}
    if os.path.exists(VOL_PATH):
        with open(VOL_PATH) as f:
            vol_data = json.load(f)
        for r in vol_data.get('series', []):
            vol_map[r['date']] = {
                'avg_vol': r['avg_vol'],
                'vol_quantile': r['vol_quantile'],
                'vol_regime': r['vol_regime'],
                'delta_vol': r['delta_vol'],
            }
        print(f"  波动率数据: {len(vol_map)}天")
    else:
        print(f"  ⚠️ 波动率数据不存在")

    # 3. 构建日收益率序列
    records = []
    for i in range(1, len(dates_nav)):
        date_fmt = dates_nav[i]
        date_compact = date_fmt.replace('-', '')

        if fund_nav[i-1] == 0 or index_nav[i-1] == 0:
            continue

        fund_ret = fund_nav[i] / fund_nav[i-1] - 1
        index_ret = index_nav[i] / index_nav[i-1] - 1

        pca_info = pca_map.get(date_compact, {})
        pca_friendly = pca_info.get('pca_friendly', None)
        env_type = pca_info.get('env_type', '—')

        vol_info = vol_map.get(date_compact, {})
        avg_vol = vol_info.get('avg_vol', None)
        vol_quantile = vol_info.get('vol_quantile', None)
        vol_regime = vol_info.get('vol_regime', '—')

        records.append({
            'date': date_compact,
            'date_fmt': date_fmt,
            'fund_return': fund_ret,
            'index_return': index_ret,
            'pca_friendly': pca_friendly,
            'env_type': env_type,
            'avg_vol': avg_vol,
            'vol_quantile': vol_quantile,
            'vol_regime': vol_regime,
        })

    print(f"  有效交易日: {len(records)}")

    # 4. PCA友好度变化量（Δpca）
    for i, r in enumerate(records):
        if i > 0 and records[i-1].get('pca_friendly') is not None and r.get('pca_friendly') is not None:
            r['delta_pca'] = r['pca_friendly'] - records[i-1]['pca_friendly']
        else:
            r['delta_pca'] = 0.0

    # 5. 滚动OLS beta（产品 ~ 南华商品）
    fund_rets = [r['fund_return'] for r in records]
    idx_rets = [r['index_return'] for r in records]

    for i, r in enumerate(records):
        start = max(0, i - WINDOW + 1)
        _, beta = ols_beta(fund_rets[start:i+1], idx_rets[start:i+1])
        r['beta'] = round(beta, 6)
        r['beta_contribution'] = round(beta * r['index_return'], 8)

    # 6. 超额（超beta部分）
    for r in records:
        r['excess_over_beta'] = r['fund_return'] - r['beta_contribution']

    # 7. 环境贡献回归：excess = γ1*(pca-50) + γ2*(vol-vol_mean) + ε
    # 收集同时有PCA和波动率的天
    valid_for_reg = []
    for r in records:
        if r.get('pca_friendly') is not None and r.get('avg_vol') is not None:
            valid_for_reg.append((
                r['excess_over_beta'],
                r['pca_friendly'] - 50,
                r['avg_vol'],
            ))

    # 波动率均值（centering）
    vol_mean = sum(v[2] for v in valid_for_reg) / len(valid_for_reg) if valid_for_reg else 25.0

    if len(valid_for_reg) >= 10:
        y = [v[0] for v in valid_for_reg]
        x_pca = [v[1] for v in valid_for_reg]
        x_vol = [v[2] - vol_mean for v in valid_for_reg]

        # 两步OLS: 先PCA，再vol on residual
        _, gamma_pca = ols_beta(y, x_pca)
        resid1 = [y[i] - gamma_pca * x_pca[i] for i in range(len(y))]
        _, gamma_vol = ols_beta(resid1, x_vol)

        # Combined R²
        y_mean = sum(y) / len(y)
        ss_tot = sum((yi - y_mean) ** 2 for yi in y)
        predicted = [gamma_pca * x_pca[i] + gamma_vol * x_vol[i] for i in range(len(y))]
        ss_res = sum((y[i] - predicted[i]) ** 2 for i in range(len(y)))
        r2_env = max(0, 1 - ss_res / ss_tot) if ss_tot > 1e-15 else 0.0

        # Individual R²s
        r2_pca = ols_r2(y, x_pca)
        r2_vol = ols_r2(resid1, x_vol)
    else:
        gamma_pca = 0.0
        gamma_vol = 0.0
        r2_env = 0.0
        r2_pca = 0.0
        r2_vol = 0.0

    print(f"  环境回归: γ_pca={gamma_pca:.6f}, γ_vol={gamma_vol:.6f}")
    print(f"  R²: 综合={r2_env:.4f}, PCA={r2_pca:.4f}, 波动率={r2_vol:.4f}")

    # 8. 逐日分解
    for r in records:
        pca_contrib = 0.0
        vol_contrib = 0.0
        if r.get('pca_friendly') is not None:
            pca_contrib = gamma_pca * (r['pca_friendly'] - 50)
        if r.get('avg_vol') is not None:
            vol_contrib = gamma_vol * (r['avg_vol'] - vol_mean)
        r['pca_contribution'] = round(pca_contrib, 8)
        r['vol_contribution'] = round(vol_contrib, 8)
        r['env_contribution'] = round(pca_contrib + vol_contrib, 8)
        r['manager_alpha'] = round(r['fund_return'] - r['beta_contribution'] - r['env_contribution'], 8)

    # 9. 按环境类型分组统计
    env_stats = defaultdict(lambda: {'days': 0, 'fund_ret': 0, 'beta_ret': 0, 'alpha_ret': 0})
    for r in records:
        env = r.get('env_type', '—')
        env_stats[env]['days'] += 1
        env_stats[env]['fund_ret'] += r['fund_return']
        env_stats[env]['beta_ret'] += r['beta_contribution']
        env_stats[env]['alpha_ret'] += r['manager_alpha']

    # 10. 累计收益
    cum_fund = cum_beta = cum_env = cum_pca = cum_vol = cum_alpha = 0.0
    for r in records:
        cum_fund += r['fund_return']
        cum_beta += r['beta_contribution']
        cum_pca += r['pca_contribution']
        cum_vol += r['vol_contribution']
        cum_env += r['env_contribution']
        cum_alpha += r['manager_alpha']
        r['cum_fund'] = round(cum_fund * 100, 4)
        r['cum_beta'] = round(cum_beta * 100, 4)
        r['cum_pca'] = round(cum_pca * 100, 4)
        r['cum_vol'] = round(cum_vol * 100, 4)
        r['cum_env'] = round(cum_env * 100, 4)
        r['cum_alpha'] = round(cum_alpha * 100, 4)

    # 11. 写CSV
    fields = ['date', 'fund_return', 'index_return', 'beta', 'beta_contribution',
              'pca_friendly', 'avg_vol', 'vol_quantile', 'env_type', 'vol_regime',
              'pca_contribution', 'vol_contribution', 'env_contribution', 'manager_alpha',
              'cum_fund', 'cum_beta', 'cum_pca', 'cum_vol', 'cum_env', 'cum_alpha']
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in records:
            row = {k: r.get(k, '') for k in fields}
            for k in ['fund_return', 'index_return']:
                if isinstance(row[k], float):
                    row[k] = round(row[k], 8)
            w.writerow(row)
    print(f"  CSV: {OUT_CSV} ({len(records)} rows)")

    # 12. 写JSON
    total_ret = round(cum_fund * 100, 2)
    beta_total = round(cum_beta * 100, 2)
    vol_total = round(cum_vol * 100, 2)
    env_total = round(cum_env * 100, 2)
    pca_total = round(cum_pca * 100, 2)
    alpha_total = round(cum_alpha * 100, 2)
    avg_beta = round(sum(r['beta'] for r in records) / len(records), 4)

    env_summary = {}
    for env, s in env_stats.items():
        env_summary[env] = {
            'days': s['days'],
            'avg_fund_ret': round(s['fund_ret'] / s['days'] * 100, 4) if s['days'] else 0,
            'avg_beta_ret': round(s['beta_ret'] / s['days'] * 100, 4) if s['days'] else 0,
            'avg_alpha_ret': round(s['alpha_ret'] / s['days'] * 100, 4) if s['days'] else 0,
            'total_fund_ret': round(s['fund_ret'] * 100, 2),
            'total_alpha_ret': round(s['alpha_ret'] * 100, 2),
        }

    daily_json = []
    for r in records:
        daily_json.append({
            'date': r['date'],
            'fund_return': round(r['fund_return'], 6),
            'index_return': round(r['index_return'], 6),
            'beta': r['beta'],
            'beta_contribution': round(r['beta_contribution'], 6),
            'pca_friendly': r['pca_friendly'],
            'avg_vol': r['avg_vol'],
            'vol_quantile': r['vol_quantile'],
            'env_type': r['env_type'],
            'vol_regime': r['vol_regime'],
            'pca_contribution': round(r['pca_contribution'], 6),
            'vol_contribution': round(r['vol_contribution'], 6),
            'env_contribution': round(r['env_contribution'], 6),
            'manager_alpha': round(r['manager_alpha'], 6),
            'cum_fund': r['cum_fund'],
            'cum_beta': r['cum_beta'],
            'cum_pca': r['cum_pca'],
            'cum_vol': r['cum_vol'],
            'cum_env': r['cum_env'],
            'cum_alpha': r['cum_alpha'],
        })

    out = {
        'updated': datetime.now().strftime('%Y-%m-%d'),
        'date_range': f"{records[0]['date']} ~ {records[-1]['date']}",
        'benchmark': '南华商品指数',
        'env_factors': ['PCA友好度', '全市场波动率'],
        'summary': {
            'total_return': total_ret,
            'beta_total': beta_total,
            'env_total': env_total,
            'pca_total': pca_total,
            'vol_total': vol_total,
            'alpha_total': alpha_total,
            'avg_beta': avg_beta,
            'gamma_pca': round(gamma_pca, 6),
            'gamma_vol': round(gamma_vol, 6),
            'vol_mean': round(vol_mean, 2),
            'r2_env': round(r2_env, 4),
            'r2_pca': round(r2_pca, 4),
            'r2_vol': round(r2_vol, 4),
            'env_summary': env_summary,
        },
        'daily': daily_json,
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {OUT_JSON}")

    # 13. 打印结果
    print(f"\n{'='*60}")
    print(f"📊 CTA产品收益归因（4因子）")
    print(f"{'='*60}")
    print(f"  产品总收益:     {total_ret:+.2f}%")
    print(f"  ├─ Beta贡献:    {beta_total:+.2f}%  (南华商品 × β={avg_beta:.2f})")
    print(f"  ├─ 环境贡献:    {env_total:+.2f}%  (综合R²={r2_env:.3f})")
    print(f"  │  ├─ PCA:      {pca_total:+.2f}%  (γ={gamma_pca:.6f}, R²={r2_pca:.3f})")
    print(f"  │  └─ 波动率:   {vol_total:+.2f}%  (γ={gamma_vol:.6f}, R²={r2_vol:.3f})")
    print(f"  └─ 管理人Alpha: {alpha_total:+.2f}%  (择时+择品种)")

    print(f"\n  【各环境类型下表现】")
    for env in ['单一趋势主导', '温和趋势', '双阵营对抗', '全市场震荡']:
        s = env_summary.get(env)
        if s:
            print(f"    {env:8s}  {s['days']:3d}天  "
                  f"产品日均={s['avg_fund_ret']:+.4f}%  "
                  f"alpha日均={s['avg_alpha_ret']:+.4f}%  "
                  f"alpha累计={s['total_alpha_ret']:+.2f}%")

    print(f"\n✅ 归因完成")


if __name__ == '__main__':
    main()
