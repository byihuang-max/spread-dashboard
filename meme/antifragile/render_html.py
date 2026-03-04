#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反脆弱交易看板 - HTML生成（Chart.js版，风格与其他模块完全一致）
"""

import json
import pandas as pd
import numpy as np
from datetime import timedelta

EQUITY_INDICES = ['纳斯达克100', '恒生科技ETF', '科创50ETF', '日经225', '韩国KOSPI', '道琼斯']
COMPARISON_ASSETS = ['COMEX黄金', 'WTI原油', 'BTC']
MAIN_ASSETS = ['纳斯达克100', '恒生科技ETF', '科创50ETF', 'BTC', '日经225', '韩国KOSPI', '道琼斯', 'COMEX黄金']

COLORS = {
    '纳斯达克100': '#2563eb', '恒生科技ETF': '#10b981', '科创50ETF': '#f59e0b',
    'BTC': '#F7931A',        '日经225': '#ef4444',    '韩国KOSPI': '#8b5cf6',
    '道琼斯': '#06b6d4',     'COMEX黄金': '#eab308',
    'WTI原油': '#0ea5e9',    '股票中位数': '#475569',
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
    color = '#16a34a' if v > 0 else '#dc2626' if v < 0 else '#6b7280'
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
    nav_data   = nav_data_file['nav_data']
    update_time = nav_data_file['update_time']

    with open('rolling_corr.json', 'r', encoding='utf-8') as f:
        corr_data = json.load(f)
    assets_corr  = corr_data['assets']
    corr_matrices = corr_data['corr_matrices']
    latest_date  = sorted(corr_matrices.keys())[-1]
    latest_corr  = corr_matrices[latest_date]

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

    # 4条主线
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
    corr_header = '<tr><th style="padding:4px 6px"></th>' + ''.join(
        f'<th style="padding:4px 6px;font-size:10px;color:#64748b;font-weight:600;'
        f'text-align:center;white-space:nowrap;writing-mode:vertical-rl;'
        f'transform:rotate(180deg);height:70px;vertical-align:bottom">{a}</th>'
        for a in assets_corr
    ) + '</tr>'
    # 行
    corr_rows = ''
    for a1 in assets_corr:
        corr_rows += f'<tr><td style="padding:6px 10px;font-size:11px;font-weight:600;color:#374151;white-space:nowrap">{a1}</td>'
        for a2 in assets_corr:
            v = latest_corr[a1][a2]
            bg = val_to_color(v)
            fc = '#fff' if abs(v) > 0.55 else '#374151'
            corr_rows += (
                f'<td style="padding:7px 6px;text-align:center;background:{bg};'
                f'color:{fc};font-size:11px;font-weight:600;border:1px solid #f5f5f5;'
                f'min-width:52px">{v:.2f}</td>'
            )
        corr_rows += '</tr>'

    corr_table_html = (
        '<div style="overflow-x:auto">'
        '<table style="border-collapse:collapse;font-size:12px">'
        f'<thead>{corr_header}</thead><tbody>{corr_rows}</tbody>'
        '</table></div>'
    )

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
  </div>
  <div style="margin-left:auto;font-size:11px;color:#7c8598">更新: {update_time}</div>
</div>

<div class="section">
  <div class="chart-box">
    <h3>📈 全球8大资产归一净值曲线（起点=1）</h3>
    <div class="chart-wrap"><canvas id="navChart"></canvas></div>
    <div class="chart-note">
      <b>怎么看：</b>全部资产以各自最早数据日期归一为1，便于跨资产涨跌幅对比。<br>
      <b>包含：</b>纳斯达克100、恒生科技ETF、科创50ETF、BTC、日经225、韩国KOSPI、道琼斯、COMEX黄金。
    </div>
  </div>
</div>

<div class="section">
  <div class="chart-box">
    <h3>📊 股票指数中位数 vs 黄金 / 原油 / BTC <span style="font-weight:400;color:#8b92a5;font-size:11px">（近一年，灰线=6只股指参考）</span></h3>
    <div class="chart-wrap-sm"><canvas id="medianChart"></canvas></div>
  </div>
  <div class="chart-box">
    <h3>涨跌幅汇总</h3>
    <div style="overflow-x:auto">{table_html}</div>
    <div class="chart-note"><b>股票中位数</b>为纳斯达克100/恒生科技ETF/科创50ETF/日经225/韩国KOSPI/道琼斯共6只指数各周期涨跌幅的中位数。</div>
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
      callbacks:{{label:pctLabel}},
      filter:function(item){{ return item.datasetIndex >= {len(EQUITY_INDICES)} && item.parsed.y !== null; }}
    }}
  }},
  scales:{{
    y:{{
      grid:{{color:'#f0f0f0'}},
      ticks:{{callback:function(v){{return v.toFixed(2);}}}}
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
</body></html>"""

    with open('antifragile.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("✅ HTML已生成: antifragile.html")


if __name__ == '__main__':
    render_html()
