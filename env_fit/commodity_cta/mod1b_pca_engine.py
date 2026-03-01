#!/usr/bin/env python3
"""
模块1b：PCA核心引擎 — 商品市场动量/反转结构分析

核心思路（Roni × Eva 2026-03-01 共创）：
  商品指数长期低夏普、熊长牛短，CTA趋势跟踪的盈利依赖品种间的共振持续性。
  用PCA从活跃品种的日收益矩阵中提取主成分，比人为定义"什么算趋势"更客观。

输出指标：
  - PC1/PC2 时序 + 累计值（动量 vs 反转信号）
  - 方差解释比（PC1高=品种共振强=趋势环境好）
  - PC1+PC2 联合判定环境类型
  - 滚动60日窗口，每个交易日一个快照

数据源：fut_daily.csv（commodity_data.py 生成，无需新数据）
依赖：仅 numpy（macOS 自带）

输出：mod1b_pca_engine.json + mod1b_pca_engine.csv
"""

import json, os, csv, math
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUT_CSV = os.path.join(BASE_DIR, 'fut_daily.csv')
OUT_JSON = os.path.join(BASE_DIR, 'mod1b_pca_engine.json')
OUT_CSV = os.path.join(BASE_DIR, 'mod1b_pca_engine.csv')

ROLLING_WINDOW = 60  # PCA滚动窗口（交易日）
MIN_SYMBOLS = 15     # 最少需要的活跃品种数
MIN_AMT = 500        # 日均成交额门槛（万元）

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


def log(msg):
    print(msg, flush=True)


def load_fut_csv():
    """从 fut_daily.csv 读取，返回 {symbol: [{date, close, amount}, ...]}"""
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
                'amount': float(row['amount']) if row.get('amount') else 0,
            })
    for sym in series:
        series[sym].sort(key=lambda x: x['date'])
    return dict(series)


def build_return_matrix(series):
    """
    构建日收益率矩阵。
    返回 (dates, symbols, matrix)
      dates: [str, ...]  交易日列表
      symbols: [str, ...]  品种列表
      matrix: [[float, ...], ...]  T×N 矩阵，matrix[t][n] = 品种n在日期t的日收益率%
    只保留在整个时间范围内都有连续数据的活跃品种。
    """
    # 收集所有日期
    all_dates = set()
    for sym, data in series.items():
        for d in data:
            all_dates.add(d['date'])
    dates = sorted(all_dates)

    if len(dates) < ROLLING_WINDOW + 10:
        log(f"  数据天数不足: {len(dates)}")
        return None, None, None

    # 为每个品种建 date -> close/amount 映射
    sym_maps = {}
    for sym, data in series.items():
        sym_maps[sym] = {d['date']: d for d in data}

    # 筛选活跃品种：在最近 ROLLING_WINDOW+10 天中至少出现 90%，且日均成交额>MIN_AMT
    recent_dates = dates[-(ROLLING_WINDOW + 30):]
    active_symbols = []
    for sym, dmap in sym_maps.items():
        present = sum(1 for dt in recent_dates if dt in dmap)
        if present < len(recent_dates) * 0.9:
            continue
        # 检查成交额
        recent_amts = [dmap[dt]['amount'] for dt in recent_dates if dt in dmap]
        if recent_amts:
            avg_amt = sum(recent_amts) / len(recent_amts)
            if avg_amt > MIN_AMT:
                active_symbols.append(sym)

    active_symbols.sort()
    if len(active_symbols) < MIN_SYMBOLS:
        log(f"  活跃品种不足: {len(active_symbols)} < {MIN_SYMBOLS}")
        return None, None, None

    # 构建收益率矩阵
    # 对每个品种，在每个日期计算日收益率；缺失日用 0 填充
    ret_matrix = []  # T×N
    valid_dates = []

    for i in range(1, len(dates)):
        dt = dates[i]
        dt_prev = dates[i - 1]
        row = []
        valid = True
        for sym in active_symbols:
            d_now = sym_maps[sym].get(dt)
            d_prev = sym_maps[sym].get(dt_prev)
            if d_now and d_prev and d_prev['close'] > 0:
                ret = (d_now['close'] / d_prev['close'] - 1) * 100
            else:
                ret = 0.0
            row.append(ret)
        ret_matrix.append(row)
        valid_dates.append(dt)

    return valid_dates, active_symbols, ret_matrix


def pca_eigen(matrix_TxN):
    """
    手写PCA（不依赖numpy的linalg，用幂迭代法提取前2个主成分）。
    输入: T×N 矩阵（列=品种，行=交易日），已标准化
    输出: (eigenvalues[0:2], eigenvectors[0:2], explained_ratios[0:2], scores_T×2)
    """
    T = len(matrix_TxN)
    N = len(matrix_TxN[0])

    # 标准化：每列减均值、除标准差
    means = [0.0] * N
    for j in range(N):
        s = sum(matrix_TxN[t][j] for t in range(T))
        means[j] = s / T

    std_matrix = []
    stds = [0.0] * N
    for j in range(N):
        var = sum((matrix_TxN[t][j] - means[j]) ** 2 for t in range(T)) / T
        stds[j] = math.sqrt(var) if var > 0 else 1.0

    for t in range(T):
        row = [(matrix_TxN[t][j] - means[j]) / stds[j] for j in range(N)]
        std_matrix.append(row)

    # 协方差矩阵 N×N: C = X^T X / (T-1)
    cov = [[0.0] * N for _ in range(N)]
    for i in range(N):
        for j in range(i, N):
            s = sum(std_matrix[t][i] * std_matrix[t][j] for t in range(T))
            cov[i][j] = s / (T - 1)
            cov[j][i] = cov[i][j]

    total_var = sum(cov[i][i] for i in range(N))

    # 幂迭代法提取特征值/特征向量
    def power_iteration(mat, n_iter=200):
        """提取最大特征值和对应特征向量"""
        N = len(mat)
        # 初始向量
        v = [1.0 / math.sqrt(N)] * N
        eigenval = 0.0
        for _ in range(n_iter):
            # w = mat @ v
            w = [sum(mat[i][j] * v[j] for j in range(N)) for i in range(N)]
            # 归一化
            norm = math.sqrt(sum(x * x for x in w))
            if norm < 1e-12:
                break
            v = [x / norm for x in w]
            eigenval = norm
        return eigenval, v

    def deflate(mat, eigenval, eigenvec):
        """矩阵降秩：移除已提取的成分"""
        N = len(mat)
        new_mat = [row[:] for row in mat]
        for i in range(N):
            for j in range(N):
                new_mat[i][j] -= eigenval * eigenvec[i] * eigenvec[j]
        return new_mat

    eigenvalues = []
    eigenvectors = []
    mat = [row[:] for row in cov]

    for k in range(2):
        val, vec = power_iteration(mat)
        eigenvalues.append(val)
        eigenvectors.append(vec)
        mat = deflate(mat, val, vec)

    explained_ratios = [v / total_var if total_var > 0 else 0 for v in eigenvalues]

    # 计算 scores: T×2  (score[t][k] = sum(std_matrix[t][j] * eigenvectors[k][j]))
    scores = []
    for t in range(T):
        row = []
        for k in range(2):
            s = sum(std_matrix[t][j] * eigenvectors[k][j] for j in range(N))
            row.append(s)
        scores.append(row)

    return eigenvalues, eigenvectors, explained_ratios, scores


def rolling_pca(dates, symbols, ret_matrix):
    """
    滚动窗口PCA，每个交易日输出一组指标。
    """
    T = len(dates)
    N = len(symbols)
    results = []
    running_cumsum = 0.0  # 跨窗口滚动累计
    prev_eigvec = None    # 上一窗口的PC1特征向量，用于符号对齐

    for end in range(ROLLING_WINDOW, T):
        start = end - ROLLING_WINDOW
        window = [ret_matrix[t] for t in range(start, end)]
        dt = dates[end]

        eigenvalues, eigenvectors, explained, scores = pca_eigen(window)

        # 符号对齐：PCA特征向量方向有任意性（v和-v都是解）
        # 通过与上一窗口的特征向量做内积来保持方向一致
        if prev_eigvec is not None:
            dot = sum(eigenvectors[0][j] * prev_eigvec[j] for j in range(N))
            if dot < 0:
                # 翻转PC1
                eigenvectors[0] = [-x for x in eigenvectors[0]]
                scores = [[-s[0], s[1]] for s in scores]
        prev_eigvec = eigenvectors[0][:]

        pc1_ratio = explained[0]
        pc2_ratio = explained[1]
        pc1_score = scores[-1][0]  # 最新一天的PC1得分
        pc2_score = scores[-1][1]

        # PC1累计值：跨窗口逐日累加当天的PC1得分
        # 持续正值=动量偏多持续，持续负值=动量偏空持续，反复翻转=反转环境
        running_cumsum += pc1_score
        pc1_cumsum = running_cumsum

        # 环境类型判定
        if pc1_ratio > 0.35:
            if pc2_ratio < 0.15:
                env_type = '单一趋势主导'   # 最好的CTA环境
            else:
                env_type = '双阵营对抗'     # 板块轮动
        elif pc1_ratio > 0.20:
            env_type = '温和趋势'
        else:
            env_type = '全市场震荡'         # 最差环境

        # PC1方向：正=多数品种上涨方向，负=多数品种下跌方向
        # 用最近5天PC1得分的均值判定
        recent_pc1 = [scores[-(i+1)][0] for i in range(min(5, len(scores)))]
        pc1_direction = sum(recent_pc1) / len(recent_pc1)

        if pc1_direction > 0.5:
            momentum_signal = '动量偏多'
        elif pc1_direction < -0.5:
            momentum_signal = '动量偏空'
        else:
            momentum_signal = '中性'

        # CTA友好度（PCA版）：方差解释比为核心
        # pc1_ratio 高 = 共振强 = 趋势跟踪友好
        # 映射到0-100：pc1_ratio在0.15~0.50区间线性映射
        friendly_raw = max(0, min(1, (pc1_ratio - 0.15) / 0.35))
        # 如果PC1+PC2合计解释>50%，额外加分（结构清晰）
        combined_ratio = pc1_ratio + pc2_ratio
        structure_bonus = max(0, min(0.15, (combined_ratio - 0.40) / 0.30 * 0.15))
        pca_friendly = round((friendly_raw + structure_bonus) * 100, 1)
        pca_friendly = min(pca_friendly, 100)

        results.append({
            'date': dt,
            'pc1_ratio': round(pc1_ratio, 4),
            'pc2_ratio': round(pc2_ratio, 4),
            'combined_ratio': round(combined_ratio, 4),
            'pc1_score': round(pc1_score, 4),
            'pc2_score': round(pc2_score, 4),
            'pc1_cumsum': round(pc1_cumsum, 4),
            'env_type': env_type,
            'momentum_signal': momentum_signal,
            'pca_friendly': pca_friendly,
        })

    return results


def get_latest_loadings(dates, symbols, ret_matrix):
    """
    用最近60天窗口做PCA，返回每个品种在PC1/PC2上的loading。
    供 mod2b 使用，也在本模块输出。
    """
    T = len(dates)
    window = ret_matrix[T - ROLLING_WINDOW:T]

    eigenvalues, eigenvectors, explained, scores = pca_eigen(window)

    loadings = []
    for j, sym in enumerate(symbols):
        loadings.append({
            'symbol': sym,
            'sector': SYMBOL_SECTOR.get(sym, '其他'),
            'pc1_loading': round(eigenvectors[0][j], 4),
            'pc2_loading': round(eigenvectors[1][j], 4),
            'pc1_abs': round(abs(eigenvectors[0][j]), 4),
        })

    loadings.sort(key=lambda x: x['pc1_abs'], reverse=True)

    return {
        'date': dates[-1],
        'pc1_explained': round(explained[0], 4),
        'pc2_explained': round(explained[1], 4),
        'n_symbols': len(symbols),
        'loadings': loadings,
    }


def write_output(rolling_results, loading_snapshot, symbols_used):
    """输出JSON + CSV"""
    output = {
        'meta': {
            'rolling_window': ROLLING_WINDOW,
            'n_symbols': len(symbols_used),
            'symbols': symbols_used,
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'rolling': rolling_results,
        'latest_loadings': loading_snapshot,
    }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # CSV: 滚动时序
    csv_headers = [
        'date', 'pc1_ratio', 'pc2_ratio', 'combined_ratio',
        'pc1_score', 'pc2_score', 'pc1_cumsum',
        'env_type', 'momentum_signal', 'pca_friendly',
    ]
    with open(OUT_CSV, 'w', newline='', encoding='gb18030') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        for r in rolling_results:
            writer.writerow(r)

    log(f"  JSON: {OUT_JSON}")
    log(f"  CSV:  {OUT_CSV}")


def main():
    log("=" * 60)
    log("模块1b：PCA核心引擎 — 商品市场动量/反转结构分析")
    log("=" * 60)

    series = load_fut_csv()
    if not series:
        return

    log(f"  原始品种数: {len(series)}")

    dates, symbols, ret_matrix = build_return_matrix(series)
    if dates is None:
        return

    log(f"  活跃品种数: {len(symbols)}")
    log(f"  交易日数:   {len(dates)}")
    log(f"  滚动窗口:   {ROLLING_WINDOW}天")

    log("\n  正在计算滚动PCA...")
    rolling_results = rolling_pca(dates, symbols, ret_matrix)
    log(f"  滚动结果:   {len(rolling_results)}个交易日")

    log("\n  计算最新loading快照...")
    loading_snapshot = get_latest_loadings(dates, symbols, ret_matrix)

    write_output(rolling_results, loading_snapshot, symbols)

    # 打印最新结果
    if rolling_results:
        latest = rolling_results[-1]
        log(f"\n{'='*60}")
        log(f"📊 最新PCA环境快照 ({latest['date']})")
        log(f"{'='*60}")
        log(f"  PC1 方差解释比: {latest['pc1_ratio']:.1%}")
        log(f"  PC2 方差解释比: {latest['pc2_ratio']:.1%}")
        log(f"  合计解释比:     {latest['combined_ratio']:.1%}")
        log(f"  环境类型:       {latest['env_type']}")
        log(f"  动量信号:       {latest['momentum_signal']}")
        log(f"  PCA友好度:      {latest['pca_friendly']}")
        log(f"  PC1累计值:      {latest['pc1_cumsum']:+.2f}")

    if loading_snapshot:
        log(f"\n  Top 5 PC1 驱动品种:")
        for i, ld in enumerate(loading_snapshot['loadings'][:5]):
            sign = '+' if ld['pc1_loading'] > 0 else ''
            log(f"    {i+1}. {ld['symbol']:>4s} ({ld['sector']})  "
                f"PC1={sign}{ld['pc1_loading']:.3f}  PC2={ld['pc2_loading']:+.3f}")

    log(f"\n✅ 模块1b完成")


if __name__ == '__main__':
    main()
