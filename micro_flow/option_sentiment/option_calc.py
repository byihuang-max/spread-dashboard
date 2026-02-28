#!/usr/bin/env python3
"""
期权情绪面板 - 计算
1. BS模型反算IV
2. IV期限结构 + 20日滚动分位
3. PCR(OI) + OI分布
4. 异常检测（IV突变 + OI激增）
"""
import os, json, math
import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'option_sentiment.json')

RISK_FREE = 0.015  # 无风险利率 1.5%

# 标的映射
UNDERLYING_MAP = {
    'OP000300.SH': {'name': '沪深300',    'etf': '000300.SH'},
    'OP000016.SH': {'name': '上证50',     'etf': '000016.SH'},
    'OP510500.SH': {'name': '中证500ETF', 'etf': '510500.SH'},
    'OP000852.SH': {'name': '中证1000',   'etf': '000852.SH'},
}


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


# ══════════════════════════════════════
# Black-Scholes
# ══════════════════════════════════════
def bs_price(S, K, T, r, sigma, cp='C'):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0) if cp == 'C' else max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if cp == 'C':
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(market_price, S, K, T, r, cp='C'):
    if T <= 1e-6:
        return None
    intrinsic = max(S - K, 0) if cp == 'C' else max(K - S, 0)
    if market_price <= intrinsic + 1e-6:
        return None
    try:
        iv = brentq(lambda sig: bs_price(S, K, T, r, sig, cp) - market_price,
                     0.01, 5.0, xtol=1e-6, maxiter=100)
        return iv if 0.01 < iv < 5.0 else None
    except:
        return None


def calc_option_sentiment():
    contracts = load_csv('opt_contracts.csv')
    opt_daily = load_csv('opt_daily.csv')
    etf_daily = load_csv('etf_daily.csv')

    if contracts.empty or opt_daily.empty or etf_daily.empty:
        print("数据不足!")
        return

    # 类型转换
    for col in ['exercise_price']:
        if col in contracts.columns:
            contracts[col] = pd.to_numeric(contracts[col], errors='coerce')
    for col in ['close', 'settle', 'vol', 'amount', 'oi']:
        if col in opt_daily.columns:
            opt_daily[col] = pd.to_numeric(opt_daily[col], errors='coerce')
    etf_daily['close'] = pd.to_numeric(etf_daily['close'], errors='coerce')

    # 合并合约信息到日线
    merged = opt_daily.merge(
        contracts[['ts_code', 'opt_code', 'call_put', 'exercise_price', 'maturity_date', 'underlying', 'underlying_name']],
        on='ts_code', how='inner'
    )

    # 获取每天每个ETF的收盘价
    etf_prices = {}
    for _, row in etf_daily.iterrows():
        etf_prices[(str(row['ts_code']), str(row['trade_date']))] = float(row['close'])

    # 构建 underlying -> etf 映射
    und_etf = {k: v['etf'] for k, v in UNDERLYING_MAP.items()}

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'underlyings': [],
    }

    trade_dates = sorted(merged['trade_date'].unique())
    latest_date = str(trade_dates[-1])

    for und_code, und_info in UNDERLYING_MAP.items():
        print(f"\n处理 {und_info['name']}...")
        etf_code = und_info['etf']
        und_data = merged[merged['underlying'] == und_code].copy()
        if und_data.empty:
            continue

        # ── 计算IV ──
        iv_records = []
        for _, row in und_data.iterrows():
            td = str(row['trade_date'])
            # 处理日期格式
            td_key = td.replace('-', '') if '-' in td else td
            S = etf_prices.get((etf_code, td_key))
            if S is None:
                # 尝试带横线的格式
                td_dash = f"{td_key[:4]}-{td_key[4:6]}-{td_key[6:8]}" if len(td_key) == 8 else td_key
                S = etf_prices.get((etf_code, td_dash))
            if S is None or S <= 0:
                continue

            K = float(row['exercise_price'])
            mat = str(row['maturity_date']).replace('-', '')
            if len(mat) != 8:
                continue
            try:
                mat_date = pd.Timestamp(mat)
                td_date = pd.Timestamp(td_key if len(td_key) == 8 else td)
            except:
                continue
            T = (mat_date - td_date).days / 365.0
            if T <= 0:
                continue

            price = float(row['settle']) if pd.notna(row['settle']) and row['settle'] > 0 else float(row['close'])
            if price <= 0:
                continue

            cp = str(row['call_put'])
            iv = implied_vol(price, S, K, T, RISK_FREE, cp)

            iv_records.append({
                'ts_code': row['ts_code'],
                'trade_date': td_key,
                'call_put': cp,
                'exercise_price': K,
                'maturity_date': mat,
                'S': S, 'T': T,
                'settle': price,
                'vol': float(row['vol']) if pd.notna(row['vol']) else 0,
                'oi': float(row['oi']) if pd.notna(row['oi']) else 0,
                'iv': iv,
                'moneyness': S / K,  # >1 实值Call/虚值Put
            })

        if not iv_records:
            print(f"  无有效IV数据")
            continue

        iv_df = pd.DataFrame(iv_records)
        iv_df = iv_df[iv_df['iv'].notna()].copy()
        print(f"  有效IV记录: {len(iv_df)}")

        # ── 平值附近合约（moneyness 0.95~1.05）──
        atm = iv_df[(iv_df['moneyness'] >= 0.95) & (iv_df['moneyness'] <= 1.05)].copy()

        # ── 1. IV期限结构（最新一天）──
        latest_atm = atm[atm['trade_date'] == latest_date.replace('-', '')]
        if latest_atm.empty:
            # 尝试最近有数据的日期
            avail = sorted(atm['trade_date'].unique())
            if avail:
                latest_date_use = avail[-1]
                latest_atm = atm[atm['trade_date'] == latest_date_use]
            else:
                latest_date_use = latest_date
        else:
            latest_date_use = latest_date.replace('-', '')

        term_structure = []
        if not latest_atm.empty:
            for mat, grp in latest_atm.groupby('maturity_date'):
                avg_iv = grp['iv'].median()
                T = grp['T'].iloc[0]
                mat_label = f"{mat[4:6]}-{mat[6:8]}"
                term_structure.append({
                    'maturity': mat_label,
                    'maturity_date': mat,
                    'T': round(T, 4),
                    'iv': round(float(avg_iv) * 100, 2),  # 转百分比
                })
            term_structure.sort(key=lambda x: x['maturity_date'])

        # ── 2. IV 20日滚动分位 ──
        # 取近月平值Call的IV时间序列
        maturities = sorted(atm['maturity_date'].unique())
        near_mat = maturities[0] if maturities else None
        iv_history = []
        if near_mat:
            near_atm = atm[(atm['maturity_date'] == near_mat) & (atm['call_put'] == 'C')]
            daily_iv = near_atm.groupby('trade_date')['iv'].median().sort_index()
            for td, iv_val in daily_iv.items():
                # 20日滚动分位
                idx = daily_iv.index.get_loc(td)
                window = daily_iv.iloc[max(0, idx - 19):idx + 1]
                if len(window) >= 5:
                    pct = (window < iv_val).sum() / len(window)
                else:
                    pct = 0.5
                td_str = str(td)
                iv_history.append({
                    'date': f"{td_str[4:6]}-{td_str[6:8]}" if len(td_str) == 8 else td_str,
                    'iv': round(float(iv_val) * 100, 2),
                    'percentile': round(float(pct) * 100, 1),
                })

        # ── 3. PCR (by OI) ──
        pcr_history = []
        for td in sorted(iv_df['trade_date'].unique()):
            day = iv_df[iv_df['trade_date'] == td]
            put_oi = day[day['call_put'] == 'P']['oi'].sum()
            call_oi = day[day['call_put'] == 'C']['oi'].sum()
            pcr = put_oi / call_oi if call_oi > 0 else 0
            put_vol = day[day['call_put'] == 'P']['vol'].sum()
            call_vol = day[day['call_put'] == 'C']['vol'].sum()
            pcr_vol = put_vol / call_vol if call_vol > 0 else 0
            td_str = str(td)
            pcr_history.append({
                'date': f"{td_str[4:6]}-{td_str[6:8]}" if len(td_str) == 8 else td_str,
                'pcr_oi': round(float(pcr), 3),
                'pcr_vol': round(float(pcr_vol), 3),
            })

        # ── 4. OI 按行权价分布（最新一天）──
        latest_all = iv_df[iv_df['trade_date'] == latest_date_use]
        # 取近月
        if near_mat:
            latest_near = latest_all[latest_all['maturity_date'] == near_mat]
        else:
            latest_near = latest_all
        
        oi_dist = []
        if not latest_near.empty:
            S_latest = latest_near['S'].iloc[0]
            for K, grp in latest_near.groupby('exercise_price'):
                call_oi = grp[grp['call_put'] == 'C']['oi'].sum()
                put_oi = grp[grp['call_put'] == 'P']['oi'].sum()
                call_iv = grp[grp['call_put'] == 'C']['iv'].median()
                put_iv = grp[grp['call_put'] == 'P']['iv'].median()
                oi_dist.append({
                    'strike': float(K),
                    'call_oi': int(call_oi),
                    'put_oi': int(put_oi),
                    'call_iv': round(float(call_iv) * 100, 2) if pd.notna(call_iv) else None,
                    'put_iv': round(float(put_iv) * 100, 2) if pd.notna(put_iv) else None,
                })
            oi_dist.sort(key=lambda x: x['strike'])

        # ── 5. 异常检测 ──
        anomalies = []
        # OI 异常：最新一天 vs 前5天均值
        dates_sorted = sorted(iv_df['trade_date'].unique())
        if len(dates_sorted) >= 6:
            prev_dates = dates_sorted[-6:-1]
            prev_data = iv_df[iv_df['trade_date'].isin(prev_dates)]
            prev_oi_avg = prev_data.groupby(['ts_code'])['oi'].mean()
            
            latest_data = iv_df[iv_df['trade_date'] == latest_date_use]
            for _, row in latest_data.iterrows():
                prev_avg = prev_oi_avg.get(row['ts_code'], 0)
                if prev_avg > 50 and row['oi'] > prev_avg * 2:
                    anomalies.append({
                        'type': 'oi_surge',
                        'label': f"{'P' if row['call_put']=='P' else 'C'}{row['exercise_price']:.2f}",
                        'detail': f"OI {int(row['oi'])} vs 均值{int(prev_avg)}（{row['oi']/prev_avg:.1f}x）",
                        'call_put': row['call_put'],
                        'strike': float(row['exercise_price']),
                        'oi': int(row['oi']),
                        'prev_avg': int(prev_avg),
                    })

            # IV 异常：当日IV vs 前5日的变化
            if not atm.empty:
                for mat in atm['maturity_date'].unique():
                    mat_atm = atm[atm['maturity_date'] == mat]
                    for cp in ['C', 'P']:
                        cp_data = mat_atm[mat_atm['call_put'] == cp]
                        daily_med = cp_data.groupby('trade_date')['iv'].median().sort_index()
                        if len(daily_med) >= 6:
                            prev_ivs = daily_med.iloc[-6:-1]
                            latest_iv = daily_med.iloc[-1]
                            mean_iv = prev_ivs.mean()
                            std_iv = prev_ivs.std()
                            if std_iv > 0 and abs(latest_iv - mean_iv) > 2 * std_iv:
                                direction = '放大' if latest_iv > mean_iv else '缩小'
                                mat_label = f"{str(mat)[4:6]}月"
                                anomalies.append({
                                    'type': 'iv_spike',
                                    'label': f"{mat_label}{cp} IV{direction}",
                                    'detail': f"IV {latest_iv*100:.1f}% vs 均值{mean_iv*100:.1f}%（{abs(latest_iv-mean_iv)/std_iv:.1f}σ）",
                                    'direction': direction,
                                })

        # ── 汇总 ──
        latest_pcr = pcr_history[-1] if pcr_history else {}
        latest_iv_val = iv_history[-1] if iv_history else {}

        und_result = {
            'code': und_code,
            'name': und_info['name'],
            'latest_date': latest_date_use,
            'term_structure': term_structure,
            'iv_history': iv_history,
            'pcr_history': pcr_history,
            'oi_distribution': oi_dist,
            'anomalies': anomalies,
            'summary': {
                'pcr_oi': latest_pcr.get('pcr_oi', 0),
                'pcr_vol': latest_pcr.get('pcr_vol', 0),
                'atm_iv': latest_iv_val.get('iv', 0),
                'iv_percentile': latest_iv_val.get('percentile', 50),
                'spot': float(latest_near['S'].iloc[0]) if not latest_near.empty else 0,
                'anomaly_count': len(anomalies),
            },
        }
        result['underlyings'].append(und_result)
        print(f"  PCR(OI)={latest_pcr.get('pcr_oi',0)}, ATM IV={latest_iv_val.get('iv',0)}%, 异常={len(anomalies)}")

    # ══════════════════════════════════════════
    # 全局信号汇总
    # ══════════════════════════════════════════
    global_signals = []
    for u in result['underlyings']:
        s = u['summary']
        name = u['name']

        # PCR 极端
        if s['pcr_oi'] > 1.3:
            global_signals.append(f"{name} PCR(OI) {s['pcr_oi']:.2f}，看空持仓极重 🔴")
        elif s['pcr_oi'] < 0.5:
            global_signals.append(f"{name} PCR(OI) {s['pcr_oi']:.2f}，看多情绪亢奋 ⚠️")

        # IV 分位极端
        if s['iv_percentile'] <= 10:
            global_signals.append(f"{name} IV分位 {s['iv_percentile']:.0f}%，波动率极低，对冲成本便宜 🟢")
        elif s['iv_percentile'] >= 90:
            global_signals.append(f"{name} IV分位 {s['iv_percentile']:.0f}%，波动率极高，市场恐慌 🔴")

        # IV 期限结构倒挂
        ts = u.get('term_structure', [])
        if len(ts) >= 2 and ts[0]['iv'] > ts[1]['iv'] * 1.05:
            global_signals.append(f"{name} IV期限倒挂（近月{ts[0]['iv']:.1f}% > 次月{ts[1]['iv']:.1f}%）⚠️")

        # OI激增的大头
        oi_surges = [a for a in u.get('anomalies', []) if a['type'] == 'oi_surge']
        if oi_surges:
            biggest = max(oi_surges, key=lambda x: x.get('oi', 0))
            ratio = biggest['oi'] / biggest['prev_avg'] if biggest.get('prev_avg', 0) > 0 else 0
            global_signals.append(f"{name} {biggest['label']} OI激增{ratio:.1f}x，大资金建仓 🔶")

    result['global_signals'] = global_signals if global_signals else ['当前期权市场无极端信号 ✅']

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n输出: {OUTPUT_JSON}")


if __name__ == '__main__':
    calc_option_sentiment()
