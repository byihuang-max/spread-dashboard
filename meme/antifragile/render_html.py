#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - HTML生成（Chart.js版，风格与其他模块完全一致）
"""

import json
import html as html_lib
import pandas as pd
import numpy as np
from datetime import timedelta

EQUITY_INDICES = ['纳斯达克100', '恒生科技ETF', '科创50ETF', '日经225', '韩国KOSPI', '纳斯达克ETF(QQQ)']
COMPARISON_ASSETS = ['COMEX黄金', 'WTI原油', 'BTC', '美元兑日元']
MAIN_ASSETS = ['纳斯达克100', '恒生科技ETF', '科创50ETF', 'BTC', '日经225', '韩国KOSPI', '纳斯达克ETF(QQQ)', 'COMEX黄金']

COLORS = {
    '纳斯达克100': '#2563eb', '恒生科技ETF': '#10b981', '科创50ETF': '#f59e0b',
    'BTC': '#F7931A',        '日经225': '#ef4444',    '韩国KOSPI': '#8b5cf6',
    '纳斯达克ETF(QQQ)': '#06b6d4', 'COMEX黄金': '#eab308',
    'WTI原油': '#0ea5e9',    '股票中位数': '#475569',
    '美元兑日元': '#be185d', # 日元套息杠杆（玫红）
}


def calc_median_nav(nav_data, window_days=365):
    all_assets = EQUITY_INDICES + COMPARISON_ASSETS
    df = pd.DataFrame({k: nav_data[k] for k in all_assets if k in nav_data})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().dropna(how='all')
    cutoff = df.index[-1] - timedelta(days=window_days)
    df = df[df.index >= cutoff].ffill()
    first_valid = df.apply(lambda s: s.dropna().iloc[0] if s.dropna().shape[0] > 0 else 1)
    df_norm = df.div(first_valid, axis=1)
    df_norm['股票中位数'] = df_norm[EQUITY_INDICES].median(axis=1)
    return df_norm


def calc_returns(nav_data):
    all_assets = EQUITY_INDICES + COMPARISON_ASSETS
    df = pd.DataFrame({k: nav_data[k] for k in all_assets if k in nav_data})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().ffill()
    periods = {'1D': 1, '1W': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252}
    rows, equity_rets = [], {}
    for name in all_assets:
        if name not in df.columns:
            continue
        s = df[name].dropna()
        row = {'资产': name}
        for label, days in periods.items():
            row[label] = (s.iloc[-1] / s.iloc[-1 - days] - 1) if len(s) > days else None
        rows.append(row)
        if name in EQUITY_INDICES:
            equity_rets[name] = row
    median_row = {'资产': '股票中位数'}
    for label in periods:
        vals = [equity_rets[n][label] for n in EQUITY_INDICES
                if n in equity_rets and equity_rets[n][label] is not None]
        median_row[label] = float(np.median(vals)) if vals else None
    rows.insert(0, median_row)
    return rows


def fmt_ret(v):
    if v is None:
        return '-'
    # A股惯例：红=涨，绿=跌
    color = '#dc2626' if v > 0 else '#16a34a' if v < 0 else '#6b7280'
    sign = '+' if v > 0 else ''
    return f'<span style="color:{color};font-weight:600">{sign}{v:.1%}</span>'


def val_to_color(v):
    """相关系数 -1~1 → 蓝白红"""
    v = max(-1, min(1, v))
    if v >= 0:
        r = 255
        gb = int(255 * (1 - v * 0.85))
        return f'rgb({r},{gb},{gb})'
    else:
        b = 255
        rg = int(255 * (1 + v * 0.85))
        return f'rgb({rg},{rg},{b})'


def safe_vals(series):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)
            for v in series]


def render_html():
    with open('antifragile_nav.json', 'r', encoding='utf-8') as f:
        nav_data_file = json.load(f)

    # 动态主题：直接在生成HTML时内嵌，避免前端二次 fetch 相对路径失效
    dynamic_themes = []
    dynamic_themes_date = ''
    narrative_latest_path = '../../daily_report/meme交易/cache/narrative_latest.json'
    try:
        with open(narrative_latest_path, 'r', encoding='utf-8') as f:
            narrative_latest = json.load(f)
        dynamic_themes = narrative_latest.get('dynamic_themes', []) or []
        report_text = narrative_latest.get('report', '') or ''
        # 从报告第一行里尽量提取日期时间，例如：📊 叙事监控 V2 03-18 08:23 | 分析 186 条新闻
        if '叙事监控 V2' in report_text:
            first_line = report_text.splitlines()[0] if report_text.splitlines() else ''
            parts = first_line.split('叙事监控 V2', 1)
            if len(parts) > 1:
                dynamic_themes_date = parts[1].split('|')[0].strip()
    except Exception:
        dynamic_themes = []
        dynamic_themes_date = ''
    nav_data   = nav_data_file['nav_data']
    update_time = nav_data_file['update_time']

    with open('rolling_corr.json', 'r', encoding='utf-8') as f:
        corr_data = json.load(f)
    assets_corr  = corr_data['assets']
    corr_matrices = corr_data['corr_matrices']
    latest_date  = sorted(corr_matrices.keys())[-1]
    latest_corr  = corr_matrices[latest_date]

    # ── Meme反身性信号（如果calc_meme.py已运行）─────
    import os as _os
    meme_data = None
    if _os.path.exists('meme_signal.json'):
        with open('meme_signal.json', 'r', encoding='utf-8') as f:
            meme_data = json.load(f)

    # ─────────────────────────────────────────────
    # 1. 归一净值曲线（全量日期）
    # ─────────────────────────────────────────────
    all_dates = sorted(set().union(*[set(nav_data[a].keys()) for a in MAIN_ASSETS if a in nav_data]))
    nav_datasets = []
    for name in MAIN_ASSETS:
        if name not in nav_data:
            continue
        raw = nav_data[name]
        vals_raw = [raw.get(d) for d in all_dates]
        first = next((v for v in vals_raw if v is not None), None)
        if first is None:
            continue
        norm = [round(v / first, 4) if v is not None else None for v in vals_raw]
        nav_datasets.append({
            'label': name,
            'data': norm,
            'borderColor': COLORS.get(name, '#6b7280'),
            'borderWidth': 2,
            'tension': 0.3,
            'pointRadius': 0,
            'pointHoverRadius': 5,
            'fill': False,
            'spanGaps': True,
        })

    # ─────────────────────────────────────────────
    # 2. 股票中位数 vs 黄金/原油/BTC（近一年）
    # ─────────────────────────────────────────────
    df_norm = calc_median_nav(nav_data)
    median_dates = df_norm.index.strftime('%Y-%m-%d').tolist()
    median_datasets = []

    # 6条灰色背景线（不进 tooltip legend）
    for eq in EQUITY_INDICES:
        if eq in df_norm.columns:
            median_datasets.append({
                'label': eq,
                'data': safe_vals(df_norm[eq].tolist()),
                'borderColor': '#cbd5e1',
                'borderWidth': 1,
                'tension': 0.3,
                'pointRadius': 0,
                'pointHoverRadius': 0,
                'fill': False,
                'order': 2,
                'hidden_legend': True,  # 前端用
            })

    # 4条主线（归一化，左轴）
    for name in ['股票中位数', 'COMEX黄金', 'WTI原油', 'BTC']:
        if name in df_norm.columns:
            median_datasets.append({
                'label': name,
                'data': safe_vals(df_norm[name].tolist()),
                'borderColor': COLORS[name],
                'borderWidth': 2.5 if name == '股票中位数' else 2,
                'tension': 0.3,
                'pointRadius': 0,
                'pointHoverRadius': 5,
                'fill': False,
                'order': 1,
                'yAxisID': 'y',
            })

    # 美元兑日元：右轴，显示实际汇率（不归一化）
    if '美元兑日元' in nav_data:
        usdjpy_raw = nav_data['美元兑日元']
        usdjpy_vals = []
        last_v = None
        for d in median_dates:
            v = usdjpy_raw.get(d)
            if v is not None:
                last_v = v
            usdjpy_vals.append(round(last_v, 2) if last_v is not None else None)
        median_datasets.append({
            'label': '美元兑日元(右轴)',
            'data': usdjpy_vals,
            'borderColor': COLORS['美元兑日元'],
            'borderWidth': 1.5,
            'borderDash': [5, 3],
            'tension': 0.3,
            'pointRadius': 0,
            'pointHoverRadius': 5,
            'fill': False,
            'order': 1,
            'yAxisID': 'y2',
        })

    # ─────────────────────────────────────────────
    # 3. 涨跌幅表格
    # ─────────────────────────────────────────────
    ret_rows = calc_returns(nav_data)
    period_labels = ['1D', '1W', '1M', '3M', '6M', '1Y']
    table_rows_html = ''
    for row in ret_rows:
        name = row['资产']
        is_median = (name == '股票中位数')
        s = 'background:#f8fafc;font-weight:700;border-top:2px solid #e2e8f0;' if is_median else ''
        cells = f'<td style="padding:10px 14px;{s}">{name}</td>'
        for p in period_labels:
            cells += f'<td style="text-align:right;padding:10px 14px;{s}">{fmt_ret(row.get(p))}</td>'
        table_rows_html += f'<tr>{cells}</tr>'

    table_html = (
        '<table style="width:100%;border-collapse:collapse;font-size:13px;color:#2d3142">'
        '<thead><tr style="background:#f1f5f9;color:#64748b;font-size:12px">'
        '<th style="text-align:left;padding:10px 14px;border-bottom:1px solid #e2e8f0">资产</th>'
        + ''.join(f'<th style="text-align:right;padding:10px 14px;border-bottom:1px solid #e2e8f0">{p}</th>' for p in period_labels)
        + f'</tr></thead><tbody>{table_rows_html}</tbody></table>'
    )

    # ─────────────────────────────────────────────
    # 4. 相关性热力图（HTML 彩色表格）
    # ─────────────────────────────────────────────
    # 列头（竖排文字）
    col_w = f'width:calc((100% - 120px) / {len(assets_corr)})'
    corr_header = '<tr><th style="padding:4px 6px;width:120px"></th>' + ''.join(
        f'<th style="padding:4px 6px;font-size:10px;color:#64748b;font-weight:600;'
        f'text-align:center;white-space:nowrap;writing-mode:vertical-rl;'
        f'transform:rotate(180deg);height:70px;vertical-align:bottom;{col_w}">{a}</th>'
        for a in assets_corr
    ) + '</tr>'
    # 行
    corr_rows = ''
    for a1 in assets_corr:
        corr_rows += f'<tr><td style="padding:6px 10px;font-size:11px;font-weight:600;color:#374151;white-space:nowrap;width:120px">{a1}</td>'
        for a2 in assets_corr:
            v = latest_corr[a1][a2]
            bg = val_to_color(v)
            fc = '#fff' if abs(v) > 0.55 else '#374151'
            corr_rows += (
                f'<td style="padding:7px 6px;text-align:center;background:{bg};'
                f'color:{fc};font-size:11px;font-weight:600;border:1px solid #f5f5f5;'
                f'{col_w}">{v:.2f}</td>'
            )
        corr_rows += '</tr>'

    corr_table_html = (
        '<div style="overflow-x:auto">'
        '<table style="border-collapse:collapse;font-size:12px;width:100%;table-layout:fixed">'
        f'<thead>{corr_header}</thead><tbody>{corr_rows}</tbody>'
        '</table></div>'
    )

    # ─────────────────────────────────────────────
    # 5. Meme反身性信号模块数据准备
    # ─────────────────────────────────────────────
    meme_section_html = ''

    if meme_data:
        cur        = meme_data.get('current', {})
        phase      = cur.get('phase', {})
        history    = meme_data.get('history', {})
        wts        = meme_data.get('vol_weights', {})

        # 当前状态卡片
        score      = cur.get('meme_score', '--')
        phase_emoji = phase.get('emoji', '')
        phase_label = phase.get('label', '')
        phase_desc  = phase.get('desc', '')
        nli_val    = cur.get('nli', '--')
        nli_pct    = cur.get('nli_percentile', '--')
        va_val     = cur.get('va', '--')
        va_pct     = cur.get('va_percentile', '--')
        meme_date  = cur.get('date', '--')

        # 权重说明
        wt_html = ' · '.join([f'{k} <b>{int(v*100)}%</b>' for k, v in wts.items()])

        # 颜色：按阶段决定
        level = phase.get('level', 1)
        phase_color = {'1': '#16a34a', '2': '#ca8a04', '3': '#ea580c', '4': '#dc2626'}.get(str(level), '#6b7280')

        # NLI历史折线（分位数）
        nli_hist  = history.get('nli_pct', {})
        nli_dates = sorted(nli_hist.keys())
        nli_vals  = [nli_hist[d] for d in nli_dates]

        # VA历史折线（原始值×100 转成百分比显示）
        va_hist   = history.get('va', {})
        va_dates  = sorted(va_hist.keys())
        va_vals   = [round(va_hist[d] * 100, 2) for d in va_dates]

        # 综合Meme信号历史
        ms_hist   = history.get('meme_score', {})
        ms_dates  = sorted(ms_hist.keys())
        ms_vals   = [ms_hist[d] for d in ms_dates]

        meme_nli_labels_json = json.dumps(nli_dates)
        meme_nli_vals_json   = json.dumps(nli_vals)
        meme_va_labels_json  = json.dumps(va_dates)
        meme_va_vals_json    = json.dumps(va_vals)
        meme_ms_labels_json  = json.dumps(ms_dates)
        meme_ms_vals_json    = json.dumps(ms_vals)

        va_str = f'{va_val:+.1f}%' if isinstance(va_val, (int, float)) else '--'
        va_pct_str = f'{va_pct:.0f}%' if isinstance(va_pct, (int, float)) else '--'
        nli_str = f'{nli_val:.3f}' if isinstance(nli_val, (int, float)) else '--'
        nli_pct_str = f'{nli_pct:.0f}%' if isinstance(nli_pct, (int, float)) else '--'
        score_str = f'{score:.0f}' if isinstance(score, (int, float)) else '--'

        meme_section_html = f"""
<div class="section">
  <div class="chart-box">
    <h3>🚦 Meme反身性信号 <span style="font-weight:400;color:#8b92a5;font-size:11px">（截至 {meme_date}）</span></h3>

    <!-- 当前状态大卡片 -->
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;align-items:stretch">
      <!-- 主信号 -->
      <div style="flex:0 0 auto;background:linear-gradient(135deg,#1e2433,#2a3350);border-radius:10px;padding:20px 28px;color:#e2e6ed;min-width:180px;text-align:center">
        <div style="font-size:36px;margin-bottom:4px">{phase_emoji}</div>
        <div style="font-size:22px;font-weight:900;color:{phase_color}">{score_str}</div>
        <div style="font-size:11px;color:#7c8598;margin-top:2px">综合信号 / 100</div>
        <div style="font-size:13px;font-weight:700;color:{phase_color};margin-top:8px">{phase_label}</div>
      </div>
      <!-- 分项指标 -->
      <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div style="background:#f8fafc;border-radius:8px;padding:14px 16px;border-left:3px solid #2563eb">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">叙事联动指数 (NLI)</div>
          <div style="font-size:18px;font-weight:700;color:#1e293b">{nli_str}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:2px">历史 {nli_pct_str} 分位</div>
        </div>
        <div style="background:#f8fafc;border-radius:8px;padding:14px 16px;border-left:3px solid #F7931A">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">量能加速度 (VA)</div>
          <div style="font-size:18px;font-weight:700;color:#1e293b">{va_str}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:2px">历史 {va_pct_str} 分位</div>
        </div>
        <div style="background:#f8fafc;border-radius:8px;padding:12px 16px;grid-column:1/-1">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">信号解读</div>
          <div style="font-size:12px;color:#374151;line-height:1.6">{phase_desc}</div>
        </div>
      </div>
    </div>

    <!-- 综合Meme信号历史走势 -->
    <div style="margin-bottom:8px;font-size:12px;font-weight:600;color:#374151">综合Meme信号历史（0-100）</div>
    <div style="position:relative;height:160px;margin-bottom:16px"><canvas id="memeScoreChart"></canvas></div>

    <!-- 双图：NLI + VA -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:6px">叙事联动指数历史分位（%）</div>
        <div style="position:relative;height:140px"><canvas id="memeNliChart"></canvas></div>
      </div>
      <div>
        <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:6px">量能加速度 VA（%，正=放量 负=缩量）</div>
        <div style="position:relative;height:140px"><canvas id="memeVaChart"></canvas></div>
      </div>
    </div>

    <div class="chart-note" style="margin-top:12px">
      <b>叙事联动指数(NLI)：</b>相关性矩阵中正相关系数的均值，衡量资产同涨同跌程度。越高=叙事越趋同。<br>
      <b>量能加速度(VA)：</b>近5日均量 / 近30日均量 - 1，多资产加权（{wt_html}）。<br>
      <b>综合信号：</b>两指标各取历史分位后加权平均（各50%）。分位基于过去252个交易日。<br>
      <b>⚠️ 注意：</b>恐慌暴跌时NLI也会升高（全面崩跌也是联动），需结合价格方向判断是Meme狂欢还是系统性风险。
    </div>
  </div>
</div>

<script>
// ── Meme信号数据 ───────────────────────────────
var MEME_SCORE_LABELS = {meme_ms_labels_json};
var MEME_SCORE_VALS   = {meme_ms_vals_json};
var MEME_NLI_LABELS   = {meme_nli_labels_json};
var MEME_NLI_VALS     = {meme_nli_vals_json};
var MEME_VA_LABELS    = {meme_va_labels_json};
var MEME_VA_VALS      = {meme_va_vals_json};

// 综合Meme信号折线图（带阶段背景色）
new Chart(document.getElementById('memeScoreChart'), {{
  type: 'line',
  data: {{
    labels: MEME_SCORE_LABELS,
    datasets: [{{
      label: '综合Meme信号',
      data: MEME_SCORE_VALS,
      borderColor: '#7c3aed',
      backgroundColor: 'rgba(124,58,237,0.08)',
      borderWidth: 2,
      tension: 0.3,
      pointRadius: 0,
      pointHoverRadius: 4,
      fill: true,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{ return '信号强度: ' + ctx.parsed.y.toFixed(1) + '分'; }}
        }}
      }},
      annotation: {{ /* 可用chartjs-plugin-annotation加阶段分界线 */ }}
    }},
    scales: {{
      y: {{ min: 0, max: 100, grid: {{ color: '#f0f0f0' }},
            ticks: {{ callback: function(v) {{ return v + '分'; }} }} }},
      x: {{ ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 叙事联动指数分位历史
new Chart(document.getElementById('memeNliChart'), {{
  type: 'line',
  data: {{
    labels: MEME_NLI_LABELS,
    datasets: [{{
      label: 'NLI历史分位',
      data: MEME_NLI_VALS,
      borderColor: '#2563eb',
      backgroundColor: 'rgba(37,99,235,0.08)',
      borderWidth: 1.5,
      tension: 0.3,
      pointRadius: 0,
      fill: true,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: function(ctx) {{ return 'NLI分位: ' + ctx.parsed.y.toFixed(1) + '%'; }} }} }}
    }},
    scales: {{
      y: {{ min: 0, max: 100, grid: {{ color: '#f0f0f0' }},
            ticks: {{ callback: function(v) {{ return v + '%'; }}, font: {{ size: 9 }} }} }},
      x: {{ ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: {{ size: 9 }} }} }}
    }}
  }}
}});

// 量能加速度柱状图（正=蓝，负=橙）
var va_colors = MEME_VA_VALS.map(function(v) {{ return v >= 0 ? 'rgba(37,99,235,0.65)' : 'rgba(234,88,12,0.65)'; }});
new Chart(document.getElementById('memeVaChart'), {{
  type: 'bar',
  data: {{
    labels: MEME_VA_LABELS,
    datasets: [{{
      label: '量能加速度',
      data: MEME_VA_VALS,
      backgroundColor: va_colors,
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: function(ctx) {{
        var v = ctx.parsed.y;
        return '量能加速度: ' + (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
      }} }} }}
    }},
    scales: {{
      y: {{ grid: {{ color: '#f0f0f0' }},
            ticks: {{ callback: function(v) {{ return (v >= 0 ? '+' : '') + v + '%'; }}, font: {{ size: 9 }} }} }},
      x: {{ ticks: {{ maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: {{ size: 9 }} }} }}
    }}
  }}
}});
</script>
"""

    # ─────────────────────────────────────────────
    # 6. 今日新兴主题（生成时内嵌，避免前端二次 fetch）
    # ─────────────────────────────────────────────
    dynamic_themes_html = ''
    if dynamic_themes:
        cards = []
        for idx, theme in enumerate(dynamic_themes, 1):
            name = html_lib.escape(str(theme.get('theme', '未命名主题')))
            count = theme.get('count', 0)
            keywords = '、'.join(html_lib.escape(str(x)) for x in theme.get('keywords', [])[:3])
            examples = [html_lib.escape(str(x)) for x in theme.get('examples', [])[:2]]
            news_list = theme.get('news_list', [])[:8]
            heat_color = '#dc2626' if count >= 20 else '#ea580c' if count >= 10 else '#64748b'

            preview_html = ''
            if examples:
                preview_html = '<div style="font-size:11px;color:#64748b;line-height:1.6;">'
                for ex in examples:
                    preview_html += f'<div style="margin-bottom:4px;">• {ex}</div>'
                preview_html += '</div>'

            news_items_html = ''
            if news_list:
                items = []
                for i, item in enumerate(news_list, 1):
                    title = html_lib.escape(str(item.get('title', '')))
                    source = html_lib.escape(str(item.get('source', '')))
                    time = html_lib.escape(str(item.get('time', '')))
                    meta = ' · '.join(x for x in [source, time] if x)
                    meta_html = f'<div style="font-size:10px;color:#94a3b8;margin-top:2px;">{meta}</div>' if meta else ''
                    items.append(
                        f'<li style="margin:0 0 10px 18px;color:#374151;">'
                        f'<div style="font-size:12px;line-height:1.6;">{title}</div>{meta_html}</li>'
                    )
                news_items_html = '<ol style="margin:10px 0 0;padding:0;">' + ''.join(items) + '</ol>'
            else:
                news_items_html = '<div style="font-size:11px;color:#94a3b8;padding-top:8px;">暂无可展开新闻列表</div>'

            cards.append(
                f'''<details style="background:#f8fafc;border-radius:8px;padding:0;border-left:3px solid {heat_color};overflow:hidden;" {'open' if idx == 1 else ''}>
  <summary style="list-style:none;cursor:pointer;padding:14px 16px;display:flex;align-items:center;gap:8px;user-select:none;">
    <span style="font-size:13px;font-weight:600;color:#1e293b;">{name}</span>
    <span style="margin-left:auto;font-size:11px;color:{heat_color};font-weight:600;">{count}条新闻</span>
  </summary>
  <div style="padding:0 16px 14px;">
    <p style="margin:0 0 8px;font-size:11px;color:#94a3b8;">关键词：{keywords}</p>
    {preview_html}
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0;">
      <div style="font-size:11px;font-weight:600;color:#475569;margin-bottom:4px;">展开新闻列表</div>
      {news_items_html}
    </div>
  </div>
</details>'''
            )
        dynamic_themes_html = ''.join(cards)

    # ─────────────────────────────────────────────
    # 序列化到 JSON
    # ─────────────────────────────────────────────
    nav_labels_json    = json.dumps(all_dates)
    nav_datasets_json  = json.dumps(nav_datasets)
    med_labels_json    = json.dumps(median_dates)
    med_datasets_json  = json.dumps(median_datasets)

    # ─────────────────────────────────────────────
    # HTML 输出
    # ─────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>反脆弱看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'PingFang SC','Helvetica Neue',sans-serif;background:#f5f6f8;color:#2d3142;padding:20px;font-size:14px;overflow-x:hidden}}
.section{{margin-bottom:24px}}
.signal-bar{{background:linear-gradient(135deg,#1e2433,#2a3350);border-radius:12px;padding:16px 20px;color:#e2e6ed;display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}}
.signal-main{{font-size:18px;font-weight:800}}
.signal-tags{{display:flex;gap:8px;flex-wrap:wrap}}
.signal-tag{{background:rgba(255,255,255,0.1);padding:4px 12px;border-radius:20px;font-size:12px;color:#b8bfce}}
.chart-box{{background:#fff;border-radius:10px;padding:16px;border:1px solid #e8eaef;margin-bottom:16px;overflow:hidden}}
.chart-box h3{{font-size:13px;font-weight:700;color:#374151;margin-bottom:12px}}
.chart-wrap{{position:relative;height:380px}}
.chart-wrap-sm{{position:relative;height:320px}}
.chart-note{{font-size:11px;color:#8b92a5;line-height:1.7;margin-top:10px;padding:10px 12px;background:#f9fafb;border-radius:6px}}
.chart-note b{{color:#374151}}
</style>
</head><body>

<div class="signal-bar">
  <div class="signal-main">🌐 反脆弱看板</div>
  <div class="signal-tags">
    <span class="signal-tag">全球风险资产</span>
    <span class="signal-tag">归一净值</span>
    <span class="signal-tag">30天相关性</span>
    <span class="signal-tag">Meme反身性信号</span>
  </div>
  <div style="margin-left:auto;font-size:11px;color:#7c8598">更新: {update_time}</div>
</div>

{meme_section_html}

<div class="section">
  <div class="chart-box">
    <h3>📈 全球8大资产归一净值曲线（起点=1）</h3>
    <div class="chart-wrap"><canvas id="navChart"></canvas></div>
    <div class="chart-note">
      <b>怎么看：</b>全部资产以各自最早数据日期归一为1，便于跨资产涨跌幅对比。<br>
      <b>包含：</b>纳斯达克100、恒生科技ETF、科创50ETF、BTC、日经225、韩国KOSPI、标普500、COMEX黄金。
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h3>📊 股票指数中位数 vs 黄金 / 原油 / BTC / 美元兑日元 <span style="font-weight:400;color:#8b92a5;font-size:11px">（近一年，灰线=6只股指参考）</span></h3>
    <div class="chart-wrap-sm"><canvas id="medianChart"></canvas></div>
  </div>
  <div class="chart-box">
    <h3>涨跌幅汇总</h3>
    <div style="overflow-x:auto">{table_html}</div>
    <div class="chart-note"><b>股票中位数</b>为纳斯达克100/恒生科技ETF/科创50ETF/日经225/韩国KOSPI/标普500共6只指数各周期涨跌幅的中位数。</div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h3>🔥 30天滚动相关性矩阵 — 叙事联动监控 <span style="font-weight:400;color:#8b92a5;font-size:11px">（日期: {latest_date}）</span></h3>
    {corr_table_html}
    <div class="chart-note">
      <b>颜色：</b>红色=正相关（同涨跌），蓝色=负相关（反向）。
      <b>注意：</b>WTI原油不参与矩阵（仅用于中位数对标）。
    </div>
  </div>
</div>

<script>
var NAV_LABELS   = {nav_labels_json};
var NAV_DATASETS = {nav_datasets_json};
var MED_LABELS   = {med_labels_json};
var MED_DATASETS = {med_datasets_json};

// 通用 tooltip 回调
function pctLabel(ctx){{
  var v = ctx.parsed.y;
  if(v===null||v===undefined) return null;
  var chg = ((v - 1)*100).toFixed(2);
  var sign = chg >= 0 ? '+' : '';
  return ctx.dataset.label + ': ' + v.toFixed(3) + ' (' + sign + chg + '%)';
}}

// ─── 归一净值曲线 ───
new Chart(document.getElementById('navChart'),{{
  type:'line',
  data:{{labels:NAV_LABELS, datasets:NAV_DATASETS}},
  options:{{
    responsive:true, maintainAspectRatio:false,
    spanGaps:true,
    interaction:{{mode:'index', intersect:false}},
    animation:{{duration:600, easing:'easeOutQuart'}},
    plugins:{{
      legend:{{
        position:'top',
        labels:{{font:{{size:11}}, usePointStyle:true, boxWidth:18, padding:12}}
      }},
      tooltip:{{
        mode:'index', intersect:false,
        callbacks:{{label:pctLabel}},
        filter:function(item){{ return item.parsed.y !== null; }}
      }}
    }},
    scales:{{
      y:{{
        grid:{{color:'#f0f0f0'}},
        ticks:{{callback:function(v){{return v.toFixed(2);}}}}
      }},
      x:{{ticks:{{maxRotation:0, autoSkip:true, maxTicksLimit:12, font:{{size:10}}}}}}
    }}
  }}
}});

// ─── 中位数对标图 ───
// 隐藏6条灰色背景线的图例
var medOpts = {{
  responsive:true, maintainAspectRatio:false,
  interaction:{{mode:'index', intersect:false}},
  animation:{{duration:600, easing:'easeOutQuart'}},
  plugins:{{
    legend:{{
      position:'top',
      labels:{{
        font:{{size:11}}, usePointStyle:true, boxWidth:18, padding:12,
        filter:function(item){{ return item.datasetIndex >= {len(EQUITY_INDICES)}; }}
      }}
    }},
    tooltip:{{
      mode:'index', intersect:false,
      callbacks:{{
        label:function(ctx){{
          var v = ctx.parsed.y;
          if(v===null||v===undefined) return null;
          // 右轴（美元兑日元）显示实际汇率
          if(ctx.dataset.yAxisID === 'y2'){{
            return ctx.dataset.label + ': ' + v.toFixed(2);
          }}
          // 左轴显示归一化变化
          var chg = ((v-1)*100).toFixed(2);
          var sign = chg >= 0 ? '+' : '';
          return ctx.dataset.label + ': ' + v.toFixed(3) + ' (' + sign + chg + '%)';
        }}
      }},
      filter:function(item){{ return item.datasetIndex >= {len(EQUITY_INDICES)} && item.parsed.y !== null; }}
    }}
  }},
  scales:{{
    y:{{
      position:'left',
      grid:{{color:'#f0f0f0'}},
      ticks:{{callback:function(v){{return v.toFixed(2);}}}}
    }},
    y2:{{
      position:'right',
      grid:{{drawOnChartArea:false}},
      ticks:{{
        color:'#be185d',
        callback:function(v){{return v.toFixed(0);}}
      }},
      title:{{display:true, text:'USDJPY', color:'#be185d', font:{{size:10}}}}
    }},
    x:{{ticks:{{maxRotation:0, autoSkip:true, maxTicksLimit:10, font:{{size:10}}}}}}
  }}
}};
new Chart(document.getElementById('medianChart'),{{
  type:'line',
  data:{{labels:MED_LABELS, datasets:MED_DATASETS}},
  options:medOpts
}});
</script>

<!-- ================================================================
     宏观 Meme 叙事生命周期表（动态加载 lifecycle_output.json）
     ================================================================
     位置：反脆弱看板底部
     数据来源：meme/lifecycle_output.json（每日由 macro_lifecycle.py 更新）
     ================================================================ -->
<div style="background:#fff;border-radius:10px;box-shadow:0 1px 6px rgba(0,0,0,.08);
            padding:24px 28px;margin:32px 0 16px;font-family:inherit;">

  <!-- 标题 + 说明 -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
    <h2 style="margin:0;font-size:15px;font-weight:700;color:#1e293b;">
      📡 宏观 Meme 叙事生命周期
    </h2>
    <span id="lc-updated" style="font-size:11px;color:#94a3b8;"></span>
  </div>

  <!-- 副标题说明 -->
  <p style="margin:0 0 16px;font-size:12px;color:#64748b;line-height:1.6;">
    基于财经舆情关键词频次的叙事热度追踪，判断每条宏观叙事所处的生命周期阶段。
    <b>宏观 Meme 交易关注周级别趋势</b>，与短线题材炒作（1-5天）不同：
    核心逻辑是在叙事<span style="color:#16a34a;font-weight:600;">新兴期</span>布局，
    在<span style="color:#ea580c;font-weight:600;">共识期</span>（已充分定价）前退出。
  </p>

  <!-- 错误提示区（fetch 失败时显示） -->
  <div id="lc-error" style="display:none;color:#dc2626;font-size:12px;padding:8px 0;">
    ⚠️ 无法加载生命周期数据，请先运行 macro_lifecycle.py
  </div>

  <!-- 可排序表格 -->
  <div style="overflow-x:auto;">
    <table id="lc-table" style="width:100%;border-collapse:collapse;font-size:12.5px;">
      <thead>
        <tr style="border-bottom:2px solid #e2e8f0;background:#f8fafc;">
          <!-- 表头可点击排序，带 Tooltip 解释每列含义 -->
          <th class="lc-th" data-col="stage"    title="叙事当前生命周期阶段。新兴=最佳配置窗口；积累=窗口收窄；共识=市场已定价，慎追；消退=叙事降温">阶段</th>
          <th class="lc-th" data-col="name"     title="叙事主题名称（8大宏观叙事）">叙事主题</th>
          <th class="lc-th" data-col="assets"   title="该叙事热度上升时，通常受益的资产类别" style="min-width:100px">对应资产</th>
          <th class="lc-th" data-col="score"    title="今日热度得分 0-10（=关键词出现频次 × 系数）。越高=今天新闻里这个主题越热">今日热度</th>
          <th class="lc-th" data-col="ma7"      title="7日移动平均热度（过滤单日噪声，反映近1周趋势）">MA7</th>
          <th class="lc-th" data-col="hist_pct" title="当前MA7在过去366天历史中的百分位。越高=历史上越少见的高热度（接近共识区）；越低=历史低位（新兴机会区）">历史分位</th>
          <th class="lc-th" data-col="momentum" title="MA7斜率（每天平均涨/跌多少分）。正值=热度仍在上升；负值=开始降温">动量/天</th>
          <th class="lc-th" data-col="duration" title="连续高于活跃阈值（≥4分）的天数。持续越久=叙事越成熟">持续天数</th>
          <th class="lc-th lc-th-action" data-col="action" title="当前阶段的配置建议">信号建议</th>
        </tr>
      </thead>
      <tbody id="lc-tbody"></tbody>
    </table>
  </div>

  <!-- 图例说明 -->
  <div style="display:flex;flex-wrap:wrap;gap:16px;margin-top:16px;font-size:11px;color:#64748b;">
    <span><span style="background:#dcfce7;color:#15803d;border-radius:4px;padding:1px 6px;font-weight:600;">🌱新兴</span> 热度从低位升起，最大配置窗口</span>
    <span><span style="background:#fff7ed;color:#c2410c;border-radius:4px;padding:1px 6px;font-weight:600;">🔥积累</span> 持续升温，窗口收窄中</span>
    <span><span style="background:#fef9c3;color:#854d0e;border-radius:4px;padding:1px 6px;font-weight:600;">⚡共识</span> 高位稳定，市场已定价，慎追</span>
    <span><span style="background:#fef2f2;color:#991b1b;border-radius:4px;padding:1px 6px;font-weight:600;">📉消退</span> 热度下行，关注反向</span>
    <span><span style="background:#f1f5f9;color:#64748b;border-radius:4px;padding:1px 6px;font-weight:600;">🔍观察</span> 热度偏低，暂无信号</span>
  </div>

  <!-- 今日新兴主题（LLM动态发现，生成时内嵌） -->
  <div id="dynamic-themes-section" style="margin-top:24px;padding-top:20px;border-top:1px solid #e2e8f0;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
      <h3 style="margin:0;font-size:14px;font-weight:700;color:#1e293b;">🔍 今日新兴主题</h3>
      <span style="font-size:11px;color:#94a3b8;">LLM动态发现（每日更新）{(' · ' + dynamic_themes_date) if dynamic_themes_date else ''}</span>
    </div>
    <div id="dynamic-themes-content" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;">
      {dynamic_themes_html if dynamic_themes_html else '<div style="color:#94a3b8;font-size:12px;padding:12px 0;">暂无新兴主题数据</div>'}
    </div>
  </div>

  <!-- 数据说明脚注 -->
  <p style="margin:12px 0 0;font-size:11px;color:#94a3b8;">
    数据来源：Tushare 财经新闻关键词频次（wallstreetcn / cls / sina），每日更新。
    历史分位基于过去 366 天数据。建议数据积累 ≥ 14 天后参考。
    更新脚本：<code>meme/macro_lifecycle.py</code>
  </p>
</div>

<style>
/* 表格样式 */
.lc-th {{
  text-align: left;
  padding: 8px 10px;
  font-size: 11.5px;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
}}
.lc-th:hover {{ color: #1e293b; background: #f1f5f9; }}
.lc-th.sorted-asc::after  {{ content: ' ▲'; font-size: 9px; }}
.lc-th.sorted-desc::after {{ content: ' ▼'; font-size: 9px; }}
.lc-th-action {{ min-width: 180px; }}

#lc-table tbody tr {{ border-bottom: 1px solid #f1f5f9; transition: background .15s; }}
#lc-table tbody tr:hover {{ background: #f8fafc; }}
#lc-table td {{ padding: 8px 10px; vertical-align: middle; }}

/* 阶段徽章 */
.lc-badge {{
  display: inline-block;
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
}}
.lc-badge-新兴 {{ background:#dcfce7; color:#15803d; }}
.lc-badge-积累 {{ background:#fff7ed; color:#c2410c; }}
.lc-badge-共识 {{ background:#fef9c3; color:#854d0e; }}
.lc-badge-消退 {{ background:#fef2f2; color:#991b1b; }}
.lc-badge-观察 {{ background:#f1f5f9; color:#64748b; }}
.lc-badge-数据不足 {{ background:#f1f5f9; color:#94a3b8; }}

/* 历史分位进度条 */
.lc-pct-bar {{
  display: flex;
  align-items: center;
  gap: 6px;
}}
.lc-pct-track {{
  flex: 1;
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
  min-width: 60px;
}}
.lc-pct-fill {{
  height: 100%;
  border-radius: 3px;
  transition: width .4s;
}}
</style>

<script>
(function() {{
  // ─── 阶段排序权重（用于点击"阶段"列排序）───
  var STAGE_ORDER = {{'新兴':0,'积累':1,'共识':2,'消退':3,'观察':4,'数据不足':5}};

  // ─── 分位颜色（低=绿，中=黄，高=红）───
  function pctColor(pct) {{
    if (pct < 40)  return '#16a34a';  // 绿：低位，新兴机会
    if (pct < 70)  return '#ea580c';  // 橙：中位，积累中
    return '#dc2626';                  // 红：高位，共识/共识风险
  }}

  // ─── 渲染一行 ───
  function renderRow(key, r) {{
    var pct    = r.hist_pct  || 0;
    var mom    = r.momentum  || 0;
    var dur    = r.duration_days || 0;
    var score  = r.score     || 0;
    var ma7    = r.ma7       || 0;
    var stage  = r.stage     || '观察';
    var emoji  = r.stage_emoji || '';
    var action = r.action    || '';
    var name   = (r.narrative_name || key);
    var assets = (r.assets   || '-');
    var news   = r.key_news  || [];  // 重点事件标题列表（最多3条）
    var cnt    = r.matched_count;    // 命中条数（原始舆情强度）
    var total  = r.total_news;       // 当日总新闻量

    var momSign  = mom >= 0 ? '+' : '';
    var momColor = mom >= 0 ? '#16a34a' : '#dc2626';
    var fillColor = pctColor(pct);

    // 重点事件：每条用小号字展示，截断超长标题
    var newsHtml = '';
    if (news.length > 0) {{
      newsHtml = '<div style="margin-top:4px;">';
      news.forEach(function(t) {{
        var short = t.length > 28 ? t.slice(0,28)+'…' : t;
        newsHtml += '<div title="' + t.replace(/"/g,'&quot;') + '" ' +
          'style="font-size:10.5px;color:#94a3b8;line-height:1.5;white-space:nowrap;overflow:hidden;' +
          'text-overflow:ellipsis;max-width:200px;cursor:default;">📌 ' + short + '</div>';
      }});
      newsHtml += '</div>';
    }}

    return '<tr data-stage="' + STAGE_ORDER[stage] + '" data-score="' + score + '"' +
           ' data-hist="' + pct + '" data-mom="' + mom + '" data-dur="' + dur + '">' +
      // 阶段徽章
      '<td><span class="lc-badge lc-badge-' + stage + '">' + emoji + ' ' + stage + '</span></td>' +
      // 叙事名称 + 重点事件
      '<td style="font-weight:600;color:#1e293b;">' + name + newsHtml + '</td>' +
      // 对应资产
      '<td style="color:#64748b;">' + assets + '</td>' +
      // 今日热度 + 命中条数（原始舆情强度）
      '<td style="text-align:center;">' +
        '<span style="font-weight:600;">' + score.toFixed(0) + '/10</span>' +
        (cnt != null ? '<br><span style="font-size:10px;color:#94a3b8;" title="今日命中' + cnt + '条（共' + (total||'?') + '条去重新闻）">n=' + cnt + '</span>' : '') +
      '</td>' +
      // MA7
      '<td style="text-align:center;color:#475569;">' + ma7.toFixed(1) + '</td>' +
      // 历史分位（进度条）
      '<td>' +
        '<div class="lc-pct-bar">' +
          '<div class="lc-pct-track"><div class="lc-pct-fill" style="width:' + pct + '%;background:' + fillColor + ';"></div></div>' +
          '<span style="color:' + fillColor + ';font-weight:600;font-size:11px;width:34px;text-align:right;">' + pct.toFixed(0) + '%</span>' +
        '</div>' +
      '</td>' +
      // 动量
      '<td style="text-align:center;color:' + momColor + ';font-weight:600;">' + momSign + mom.toFixed(2) + '</td>' +
      // 持续天数
      '<td style="text-align:center;color:#64748b;">' + dur + '天</td>' +
      // 信号建议
      '<td style="font-size:11.5px;color:#475569;">' + action + '</td>' +
    '</tr>';
  }}

  // ─── 主加载函数 ───
  fetch('../lifecycle_output.json')
    .then(function(r) {{ return r.ok ? r.json() : Promise.reject(r.status); }})
    .then(function(data) {{
      var results = data.results || {{}};
      var updated = data.latest_date || '';
      document.getElementById('lc-updated').textContent = '数据日期：' + updated;

      // 资产映射（补充到 results 里）
      var assetMap = {{
        'AI_CapEx'  : '纳指/半导体ETF/铜',
        '去美元化'   : '黄金/BTC',
        '全球再武装' : '国防股/稀有金属',
        '财政主导'   : '黄金/实物资产',
        '地缘风险'   : '黄金/原油',
        '美国衰退'   : '美债/黄金',
        '中国刺激'   : 'A股/港股/铜',
        '通胀通缩'   : '黄金/大宗商品',
      }};

      // 按阶段权重默认排序
      var keys = Object.keys(results).sort(function(a, b) {{
        var sa = STAGE_ORDER[results[a].stage] || 5;
        var sb = STAGE_ORDER[results[b].stage] || 5;
        if (sa !== sb) return sa - sb;
        return (results[b].score || 0) - (results[a].score || 0);
      }});

      var html = '';
      keys.forEach(function(k) {{
        var r = results[k];
        r.assets = assetMap[k] || '-';
        html += renderRow(k, r);
      }});
      document.getElementById('lc-tbody').innerHTML = html;

      // ─── 表头排序逻辑 ───
      var sortCol = 'stage', sortDir = 1;
      document.querySelectorAll('.lc-th').forEach(function(th) {{
        th.addEventListener('click', function() {{
          var col = this.getAttribute('data-col');
          if (col === sortCol) {{ sortDir *= -1; }}
          else {{ sortCol = col; sortDir = 1; }}
          document.querySelectorAll('.lc-th').forEach(function(t) {{
            t.classList.remove('sorted-asc','sorted-desc');
          }});
          this.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');

          var tbody = document.getElementById('lc-tbody');
          var rows  = Array.from(tbody.querySelectorAll('tr'));
          rows.sort(function(a, b) {{
            var av, bv;
            if (col === 'stage')    {{ av = +a.dataset.stage; bv = +b.dataset.stage; }}
            else if (col === 'score')   {{ av = +a.dataset.score; bv = +b.dataset.score; }}
            else if (col === 'hist_pct'){{ av = +a.dataset.hist;  bv = +b.dataset.hist;  }}
            else if (col === 'momentum'){{ av = +a.dataset.mom;   bv = +b.dataset.mom;   }}
            else if (col === 'duration'){{ av = +a.dataset.dur;   bv = +b.dataset.dur;   }}
            else {{
              // 文字列按文本排序
              av = a.cells[col === 'name' ? 1 : col === 'assets' ? 2 : 8].textContent;
              bv = b.cells[col === 'name' ? 1 : col === 'assets' ? 2 : 8].textContent;
              return av.localeCompare(bv) * sortDir;
            }}
            return (av - bv) * sortDir;
          }});
          rows.forEach(function(r) {{ tbody.appendChild(r); }});
        }});
      }});
    }})
    .catch(function(e) {{
      console.warn('lifecycle_output.json 加载失败:', e);
      document.getElementById('lc-error').style.display = 'block';
    }});

}})();
</script>
</body></html>"""

    with open('antifragile.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("✅ HTML已生成: antifragile.html")


if __name__ == '__main__':
    render_html()
