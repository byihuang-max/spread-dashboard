#!/usr/bin/env python3
"""经济基本面 - 计算 + 美林时钟"""
import os, json
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
OUTPUT_JSON = os.path.join(SCRIPT_DIR, 'fundamentals.json')


def load_csv(name):
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


def calc():
    pmi = load_csv('pmi.csv')
    cpi = load_csv('cpi.csv')
    ppi = load_csv('ppi.csv')

    result = {
        'update_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
        'signals': [],
    }

    # ── PMI ──
    if not pmi.empty:
        pmi = pmi.sort_values('month')
        for col in pmi.columns:
            if col != 'month':
                pmi[col] = pd.to_numeric(pmi[col], errors='coerce')

        pmi_col = 'pmi' if 'pmi' in pmi.columns else None
        nmp_col = 'pmi_nmp' if 'pmi_nmp' in pmi.columns else None

        pmi_data = []
        for _, r in pmi.iterrows():
            d = {'month': str(r['month']).replace('.0', '')}
            if pmi_col and pd.notna(r.get(pmi_col)):
                d['pmi'] = round(float(r[pmi_col]), 1)
            if nmp_col and pd.notna(r.get(nmp_col)):
                d['pmi_nmp'] = round(float(r[nmp_col]), 1)
            pmi_data.append(d)
        result['pmi'] = pmi_data

        # 信号
        if pmi_col:
            latest_pmi = pmi.dropna(subset=[pmi_col]).iloc[-1]
            pmi_val = float(latest_pmi[pmi_col])
            if pmi_val >= 51:
                result['signals'].append(f"PMI {pmi_val:.1f}，制造业扩张 🟢")
            elif pmi_val < 49:
                result['signals'].append(f"PMI {pmi_val:.1f}，制造业收缩 🔴")
            else:
                result['signals'].append(f"PMI {pmi_val:.1f}，荣枯线附近")

    # ── CPI / PPI ──
    if not cpi.empty and not ppi.empty:
        cpi = cpi.sort_values('month')
        ppi = ppi.sort_values('month')
        cpi['nt_yoy'] = pd.to_numeric(cpi['nt_yoy'], errors='coerce')
        ppi['ppi_yoy'] = pd.to_numeric(ppi['ppi_yoy'], errors='coerce')

        # 合并
        merged = cpi.merge(ppi, on='month', how='outer').sort_values('month')
        merged['scissors'] = merged['nt_yoy'] - merged['ppi_yoy']

        result['cpi_ppi'] = [
            {'month': str(r['month']).replace('.0', ''),
             'cpi': round(float(r['nt_yoy']), 1) if pd.notna(r.get('nt_yoy')) else None,
             'ppi': round(float(r['ppi_yoy']), 1) if pd.notna(r.get('ppi_yoy')) else None,
             'scissors': round(float(r['scissors']), 1) if pd.notna(r.get('scissors')) else None}
            for _, r in merged.iterrows()
        ]

        # CPI-PPI剪刀差信号
        latest = merged.dropna(subset=['nt_yoy', 'ppi_yoy']).iloc[-1]
        scissors = float(latest['scissors'])
        cpi_val = float(latest['nt_yoy'])
        ppi_val = float(latest['ppi_yoy'])
        if scissors > 3:
            result['signals'].append(f"CPI-PPI剪刀差 {scissors:+.1f}%，下游利润承压 ⚠️")
        if ppi_val < -2:
            result['signals'].append(f"PPI {ppi_val:+.1f}%，工业通缩 🟡")

    # ── 美林时钟 ──
    if not pmi.empty and not cpi.empty:
        pmi_col_use = 'pmi' if 'pmi' in pmi.columns else None
        if pmi_col_use:
            latest_pmi_val = float(pmi.dropna(subset=[pmi_col_use]).iloc[-1][pmi_col_use])
            latest_cpi_val = float(cpi.dropna(subset=['nt_yoy']).iloc[-1]['nt_yoy'])

            # PMI>50 = 经济上行, CPI>2.5 = 通胀上行
            econ_up = latest_pmi_val > 50
            infl_up = latest_cpi_val > 2.5

            if econ_up and not infl_up:
                clock = '复苏期'
                clock_emoji = '🌱'
                clock_advice = '超配股票，低配债券'
            elif econ_up and infl_up:
                clock = '过热期'
                clock_emoji = '🔥'
                clock_advice = '超配商品，低配债券'
            elif not econ_up and infl_up:
                clock = '滞胀期'
                clock_emoji = '⚠️'
                clock_advice = '超配现金，低配股票'
            else:
                clock = '衰退期'
                clock_emoji = '❄️'
                clock_advice = '超配债券，低配商品'

            result['merrill_clock'] = {
                'phase': clock,
                'emoji': clock_emoji,
                'advice': clock_advice,
                'pmi': latest_pmi_val,
                'cpi': latest_cpi_val,
            }
            result['signals'].append(f"美林时钟: {clock_emoji} {clock}（PMI={latest_pmi_val:.1f}, CPI={latest_cpi_val:.1f}%）→ {clock_advice}")

    if not result['signals']:
        result['signals'] = ['基本面指标无极端信号 ✅']

    # ── 利润周期 + 内需接棒 ──
    profit_cycle_json = os.path.join(SCRIPT_DIR, 'profit_cycle', 'profit_cycle.json')
    if os.path.exists(profit_cycle_json):
        try:
            with open(profit_cycle_json, 'r', encoding='utf-8') as f:
                pc_data = json.load(f)
            
            latest = pc_data.get('latest', {})
            if latest:
                # 利润周期信号
                stage = latest.get('profit_cycle_stage', '')
                score = latest.get('profit_cycle_score', 0)
                ppi_mom = latest.get('ppi_mom', 0)
                
                if stage == '上行':
                    result['signals'].append(f"利润周期: {stage}（{score}/4分），股票策略适配度提升 🟢")
                elif stage == '见顶':
                    result['signals'].append(f"利润周期: {stage}（{score}/4分），警惕回调风险 ⚠️")
                elif stage == '下行':
                    result['signals'].append(f"利润周期: {stage}（{score}/4分），防御为主 🔴")
                elif stage == '筑底' and ppi_mom > -0.5:
                    result['signals'].append(f"利润周期: {stage}（{score}/4分），等待拐点 🟡")
                
                # 内需接棒信号
                demand_score = latest.get('demand_recovery_score', 0)
                if demand_score >= 67:
                    result['signals'].append(f"内需接棒: {demand_score}/100分，内需强劲，大盘价值受益 🌱")
                elif demand_score >= 34:
                    result['signals'].append(f"内需接棒: {demand_score}/100分，结构性改善 🟡")
        except Exception as e:
            print(f"  ⚠️ 读取利润周期数据失败: {e}")

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"输出: {OUTPUT_JSON}")
    for s in result['signals']:
        print(f"  - {s}")


if __name__ == '__main__':
    calc()
