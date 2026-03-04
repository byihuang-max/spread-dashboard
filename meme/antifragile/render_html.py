#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - HTML生成（含相关性热力图 + 中位数对标）
"""

import json
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ── 资产分类常量 ──
EQUITY_INDICES = ['纳斯达克100', '恒生科技ETF', '科创50ETF', '日经225', '韩国KOSPI', '道琼斯']
COMPARISON_ASSETS = ['COMEX黄金', 'WTI原油', 'BTC']

def calc_median_nav(nav_data, window_days=365):
    """计算股票指数中位数净值曲线，及各对标资产净值，近N天"""
    # 合并所有资产
    all_assets = EQUITY_INDICES + COMPARISON_ASSETS
    df = pd.DataFrame({k: nav_data[k] for k in all_assets if k in nav_data})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().dropna(how='all')

    # 截取近一年
    cutoff = df.index[-1] - timedelta(days=window_days)
    df = df[df.index >= cutoff]

    # 前向填充（解决各市场交易日不同导致的断线）
    df = df.ffill()

    # 重归一化（以窗口第一个有效值为1）
    first_valid = df.apply(lambda s: s.dropna().iloc[0] if s.dropna().shape[0] > 0 else 1)
    df_norm = df.div(first_valid, axis=1)

    # 每日取6股票指数的中位数（中位数NAV线）
    equity_df = df_norm[EQUITY_INDICES]
    df_norm['股票中位数'] = equity_df.median(axis=1)

    return df_norm

def calc_returns(nav_data):
    """计算各周期涨跌幅（1D/1W/1M/3M/6M/1Y）"""
    all_assets = EQUITY_INDICES + COMPARISON_ASSETS
    df = pd.DataFrame({k: nav_data[k] for k in all_assets if k in nav_data})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().ffill()

    today = df.index[-1]
    periods = {'1D': 1, '1W': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252}
    rows = []

    # 计算每个资产的各周期涨跌
    equity_rets = {}
    for name in all_assets:
        if name not in df.columns:
            continue
        s = df[name].dropna()
        row = {'资产': name}
        for label, days in periods.items():
            if len(s) > days:
                row[label] = (s.iloc[-1] / s.iloc[-1 - days] - 1)
            else:
                row[label] = None
        rows.append(row)
        if name in EQUITY_INDICES:
            equity_rets[name] = row

    # 计算股票中位数行
    median_row = {'资产': '股票中位数'}
    for label in periods:
        vals = [equity_rets[n][label] for n in EQUITY_INDICES if n in equity_rets and equity_rets[n][label] is not None]
        median_row[label] = float(np.median(vals)) if vals else None
    rows.insert(0, median_row)

    return rows

def fmt_ret(v):
    if v is None:
        return '-'
    color = '#16a34a' if v > 0 else '#dc2626' if v < 0 else '#6b7280'
    sign = '+' if v > 0 else ''
    return f'<span style="color:{color};font-weight:600">{sign}{v:.1%}</span>'

def render_html():
    """生成HTML看板"""

    # 读取净值数据
    with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
        nav_data_file = json.load(f)
    nav_data = nav_data_file['nav_data']
    update_time = nav_data_file['update_time']

    # 读取相关性数据
    with open('rolling_corr.json', 'r', encoding='utf-8') as f:
        corr_data = json.load(f)
    assets = corr_data['assets']
    corr_matrices = corr_data['corr_matrices']
    latest_date = sorted(corr_matrices.keys())[-1]
    latest_corr = corr_matrices[latest_date]

    # ── 净值曲线图表（原始价格归一化到起点=1）──
    MAIN_ASSETS = ['纳斯达克100', '恒生科技ETF', '科创50ETF', 'BTC', '日经225', '韩国KOSPI', '道琼斯', 'COMEX黄金']
    fig_nav = go.Figure()
    colors = {
        '纳斯达克100': '#2563eb', '恒生科技ETF': '#10b981', '科创50ETF': '#f59e0b',
        'BTC': '#F7931A', '日经225': '#ef4444', '韩国KOSPI': '#8b5cf6',
        '道琼斯': '#06b6d4', 'COMEX黄金': '#eab308'
    }
    for name in MAIN_ASSETS:
        if name not in nav_data:
            continue
        raw = nav_data[name]
        dates = sorted(raw.keys())
        raw_vals = [raw[d] for d in dates]
        # 归一化：起点=1
        first = raw_vals[0]
        values = [v / first for v in raw_vals]
        fig_nav.add_trace(go.Scatter(
            x=dates, y=values, mode='lines', name=name,
            line=dict(width=2.5, color=colors.get(name, '#6b7280')),
            connectgaps=True,
            hovertemplate='<b>%{fullData.name}</b><br>净值: %{y:.3f}<br>涨跌: %{customdata:.2%}<extra></extra>',
            customdata=[(v - 1) for v in values]
        ))
    fig_nav.update_layout(
        title=None,
        xaxis=dict(title=None, showgrid=True, gridcolor='#e8eaef', zeroline=False),
        yaxis=dict(title='净值', showgrid=True, gridcolor='#e8eaef', zeroline=False, tickformat='.2f'),
        hovermode='x unified', template='plotly_white', height=500,
        autosize=True,
        margin=dict(l=60, r=20, t=20, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0, font=dict(size=12)),
        plot_bgcolor='white', paper_bgcolor='white'
    )

    # ── 相关性热力图 ──
    corr_matrix = [[latest_corr[a1][a2] for a2 in assets] for a1 in assets]
    fig_corr = go.Figure(data=go.Heatmap(
        z=corr_matrix, x=assets, y=assets,
        colorscale='RdBu', zmid=0, zmin=-1, zmax=1,
        text=[[f'{val:.2f}' for val in row] for row in corr_matrix],
        texttemplate='%{text}', textfont=dict(size=11),
        hovertemplate='%{y} vs %{x}<br>相关性: %{z:.3f}<extra></extra>',
        colorbar=dict(title='相关系数')
    ))
    fig_corr.update_layout(
        title=None,
        xaxis=dict(side='bottom', tickangle=-45),
        yaxis=dict(side='left'),
        template='plotly_white', height=500,
        autosize=True,
        margin=dict(l=120, r=80, t=20, b=120),
        plot_bgcolor='white', paper_bgcolor='white'
    )

    # ── 中位数对标图表 ──
    df_norm = calc_median_nav(nav_data)
    median_colors = {
        '股票中位数': '#64748b', 'COMEX黄金': '#eab308', 'WTI原油': '#0ea5e9', 'BTC': '#F7931A'
    }
    median_dash = {'股票中位数': 'solid', 'COMEX黄金': 'solid', 'WTI原油': 'solid', 'BTC': 'solid'}
    median_width = {'股票中位数': 3, 'COMEX黄金': 2, 'WTI原油': 2, 'BTC': 2}

    fig_median = go.Figure()
    # 先画6个股票指数（灰色细线，背景参考，不参与hover）
    for eq in EQUITY_INDICES:
        if eq in df_norm.columns:
            fig_median.add_trace(go.Scatter(
                x=df_norm.index.strftime('%Y-%m-%d').tolist(),
                y=df_norm[eq].tolist(),
                mode='lines', name=eq, showlegend=True,
                line=dict(width=1, color='#cbd5e1'),
                connectgaps=True,
                hoverinfo='skip'
            ))
    # 再画4条主线（中位数+三个对标）
    for name in ['股票中位数', 'COMEX黄金', 'WTI原油', 'BTC']:
        if name in df_norm.columns:
            fig_median.add_trace(go.Scatter(
                x=df_norm.index.strftime('%Y-%m-%d').tolist(),
                y=df_norm[name].tolist(),
                mode='lines', name=name,
                line=dict(width=median_width[name], color=median_colors[name]),
                connectgaps=True,
                hovertemplate=f'<b>{name}</b><br>涨跌: %{{customdata:.2%}}<extra></extra>',
                customdata=(df_norm[name] - 1).tolist()
            ))
    fig_median.update_layout(
        title=None,
        xaxis=dict(title=None, showgrid=True, gridcolor='#e8eaef', zeroline=False),
        yaxis=dict(title='归一净值', showgrid=True, gridcolor='#e8eaef', zeroline=False, tickformat='.2f'),
        hovermode='x unified', template='plotly_white', height=460,
        autosize=True,
        margin=dict(l=60, r=20, t=20, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0, font=dict(size=12)),
        plot_bgcolor='white', paper_bgcolor='white'
    )

    # ── 涨跌幅汇总表 ──
    ret_rows = calc_returns(nav_data)
    period_labels = ['1D', '1W', '1M', '3M', '6M', '1Y']

    # 生成表格HTML
    table_rows_html = ''
    for row in ret_rows:
        name = row['资产']
        is_median = name == '股票中位数'
        style = 'background:#f8fafc;font-weight:700;border-top:2px solid #e2e8f0;' if is_median else ''
        cells = f'<td style="padding:10px 14px;{style}">{name}</td>'
        for p in period_labels:
            cells += f'<td style="text-align:right;padding:10px 14px;{style}">{fmt_ret(row.get(p))}</td>'
        table_rows_html += f'<tr>{cells}</tr>'

    table_html = f'''
<table style="width:100%;border-collapse:collapse;font-size:13px;color:#2d3142">
<thead>
<tr style="background:#f1f5f9;color:#64748b;font-size:12px">
  <th style="text-align:left;padding:10px 14px;border-bottom:1px solid #e2e8f0">资产</th>
  {"".join(f'<th style="text-align:right;padding:10px 14px;border-bottom:1px solid #e2e8f0">{p}</th>' for p in period_labels)}
</tr>
</thead>
<tbody>
{table_rows_html}
</tbody>
</table>'''

    # HTML模板
    html = f"""<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>反脆弱看板</title>
<script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'PingFang SC','Helvetica Neue','Microsoft YaHei',sans-serif;background:#f5f6f8;color:#2d3142;padding:20px;font-size:14px;overflow-x:hidden}}
h2{{font-size:16px;font-weight:700;margin-bottom:12px;color:#1e2433}}
.section{{margin-bottom:24px}}
.signal-bar{{background:linear-gradient(135deg,#1e2433,#2a3350);border-radius:12px;padding:16px 20px;color:#e2e6ed;display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}}
.signal-main{{font-size:18px;font-weight:800}}
.signal-tags{{display:flex;gap:8px;flex-wrap:wrap}}
.signal-tag{{background:rgba(255,255,255,0.1);padding:4px 12px;border-radius:20px;font-size:12px;color:#b8bfce}}
.chart-box{{background:#fff;border-radius:10px;padding:16px;border:1px solid #e8eaef;margin-bottom:16px;min-width:0;overflow:hidden}}
.chart-box h3{{font-size:13px;font-weight:700;color:#374151;margin-bottom:12px}}
.chart-note{{font-size:11px;color:#8b92a5;line-height:1.7;margin-top:10px;padding:10px 12px;background:#f9fafb;border-radius:6px}}
.chart-note b{{color:#374151}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:900px){{.chart-row{{grid-template-columns:1fr}}}}
</style>
</head><body>

<div class="signal-bar">
  <div class="signal-main">🌐 反脆弱看板</div>
  <div class="signal-tags">
    <span class="signal-tag">全球风险资产</span>
    <span class="signal-tag">归一净值</span>
    <span class="signal-tag">30天相关性</span>
  </div>
  <div style="margin-left:auto;font-size:11px;color:#7c8598">更新: {update_time}</div>
</div>

<div class="section">
<div class="chart-box">
<h3>📈 全球8大资产归一净值曲线（起点=1）</h3>
<div id="chart" style="width:100%"></div>
<div class="chart-note">
  <b>怎么看：</b>全部资产以最早可用日期归一为1，便于跨资产涨跌幅对比。<br>
  <b>包含：</b>纳斯达克100、恒生科技ETF、科创50ETF、BTC、日经225、韩国KOSPI、道琼斯、COMEX黄金。
</div>
</div>
</div>

<div class="section">
<div class="chart-box">
<h3>📊 股票指数中位数 vs 黄金 / 原油 / BTC <span style="font-weight:400;color:#8b92a5;font-size:11px">（近一年，灰线=6只股指）</span></h3>
<div id="chart-median" style="width:100%"></div>
</div>
<div class="chart-box">
<h3>涨跌幅汇总</h3>
<div style="overflow-x:auto">{table_html}</div>
<div class="chart-note"><b>股票中位数</b>为纳斯达克100/恒生科技ETF/科创50ETF/日经225/韩国KOSPI/道琼斯共6只指数的各周期涨跌幅中位数。</div>
</div>
</div>

<div class="section">
<div class="chart-box">
<h3>🔥 30天滚动相关性矩阵 — 叙事联动监控 <span style="font-weight:400;color:#8b92a5;font-size:11px">（日期: {latest_date}）</span></h3>
<div id="chart-corr" style="width:100%"></div>
<div class="chart-note">
  <b>怎么看：</b>颜色越红=正相关越强（同涨跌），越蓝=负相关（一涨一跌）。<br>
  <b>注意：</b>WTI原油不参与相关性矩阵（仅用于中位数对标）。
</div>
</div>
</div>

<script>
var navData={fig_nav.to_json()};
var medianData={fig_median.to_json()};
var corrData={fig_corr.to_json()};
var cfg={{responsive:true,displayModeBar:false}};
Plotly.newPlot('chart',navData.data,navData.layout,cfg);
Plotly.newPlot('chart-median',medianData.data,medianData.layout,cfg);
Plotly.newPlot('chart-corr',corrData.data,corrData.layout,cfg);
// 确保 iframe 加载完后重新适配宽度
window.addEventListener('load',function(){{
  setTimeout(function(){{
    Plotly.Plots.resize(document.getElementById('chart'));
    Plotly.Plots.resize(document.getElementById('chart-median'));
    Plotly.Plots.resize(document.getElementById('chart-corr'));
  }},100);
}});
</script>
</body></html>"""

    with open('antifragile.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("✅ HTML已生成: antifragile.html")

if __name__ == '__main__':
    render_html()

