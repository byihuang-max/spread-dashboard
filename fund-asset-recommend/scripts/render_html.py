#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
团队基金优选模块 - HTML 渲染
读取 fund_asset_latest.json，生成独立 HTML 页面
"""

import json, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_PATH = os.path.join(MODULE_DIR, 'data', 'fund_asset_latest.json')
OUTPUT_PATH = os.path.join(MODULE_DIR, 'fund_asset.html')


def render():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    update_time = data.get('update_time', '')
    strategy_summary = data.get('strategy_summary', [])
    market_data = data.get('market_data', {})

    # 序列化给 JS
    js_strategy = json.dumps(strategy_summary, ensure_ascii=False)
    js_market_annual = json.dumps(market_data.get('annual', []), ensure_ascii=False)
    js_market_monthly = json.dumps(market_data.get('monthly', []), ensure_ascii=False)
    js_market_quarterly = json.dumps(market_data.get('quarterly', []), ensure_ascii=False)

    html = _build_html(update_time, js_strategy, js_market_annual, js_market_monthly, js_market_quarterly)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ 生成: {OUTPUT_PATH}")


def _build_html(update_time, js_strategy, js_annual, js_monthly, js_quarterly):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>团队基金优选 · GAMT</title>
<style>
''' + CSS_BLOCK + f'''
</style>
</head>
<body>
<div class="page-header">
  <div class="header-left">
    <h1>团队基金优选</h1>
    <span class="badge">ADMIN ONLY</span>
  </div>
  <div class="header-right">
    <span class="update-time">数据更新: {update_time}</span>
    <a href="../index.html" class="back-link">← 返回看板</a>
  </div>
</div>

<div class="tab-bar">
  <div class="tab active" onclick="switchTab('overview')">策略总览</div>
  <div class="tab" onclick="switchTab('detail')">产品明细</div>
  <div class="tab" onclick="switchTab('market')">市场基准</div>
</div>

<div id="panelOverview" class="panel">
  <div class="filter-bar" id="strategyFilters"></div>
  <div class="card-grid" id="strategyGrid"></div>
</div>

<div id="panelDetail" class="panel" style="display:none">
  <div class="filter-bar">
    <input type="text" id="searchInput" placeholder="搜索产品名称..." oninput="renderTable()">
    <select id="sortSelect" onchange="renderTable()">
      <option value="ytd">按YTD排序</option>
      <option value="week">按周收益排序</option>
      <option value="month">按月收益排序</option>
      <option value="name">按名称排序</option>
    </select>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>产品名称</th><th>策略组</th><th>策略细分</th>
        <th>近一周</th><th>近一月</th><th>今年以来</th>
        <th>最新净值</th><th>净值日期</th><th>状态</th>
      </tr></thead>
      <tbody id="detailBody"></tbody>
    </table>
  </div>
</div>

<div id="panelMarket" class="panel" style="display:none">
  <div class="filter-bar">
    <div class="chip-group" id="mktPeriodChips"></div>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>策略分类</th><th>年化收益</th><th>夏普比率</th>
        <th>最大回撤</th><th>波动率</th><th>卡玛比率</th>
      </tr></thead>
      <tbody id="mktBody"></tbody>
    </table>
  </div>
</div>

<div id="navModal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="modalTitle"></h3>
      <button onclick="closeModal()" class="modal-close">&times;</button>
    </div>
    <div class="modal-body">
      <canvas id="navChart" height="300"></canvas>
      <div id="modalMetrics" class="modal-metrics"></div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
const strategySummary = {js_strategy};
const marketAnnual = {js_annual};
const marketMonthly = {js_monthly};
const marketQuarterly = {js_quarterly};
''' + JS_BLOCK + '''
</script>
</body>
</html>'''


# ========== CSS ==========
CSS_BLOCK = r'''
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh}
.page-header{display:flex;justify-content:space-between;align-items:center;padding:20px 28px;border-bottom:1px solid rgba(255,255,255,.06)}
.header-left{display:flex;align-items:center;gap:12px}
.header-left h1{font-size:20px;font-weight:700;background:linear-gradient(135deg,#60a5fa,#34d399);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.badge{font-size:10px;padding:3px 8px;border-radius:4px;background:rgba(239,68,68,.15);color:#f87171;font-weight:600;letter-spacing:1px}
.header-right{display:flex;align-items:center;gap:16px}
.update-time{font-size:12px;color:rgba(255,255,255,.35)}
.back-link{font-size:12px;color:#60a5fa;text-decoration:none}
.back-link:hover{text-decoration:underline}
.tab-bar{display:flex;gap:0;padding:0 28px;border-bottom:1px solid rgba(255,255,255,.06)}
.tab{padding:12px 20px;font-size:13px;color:rgba(255,255,255,.4);cursor:pointer;border-bottom:2px solid transparent;transition:all .2s}
.tab:hover{color:rgba(255,255,255,.7)}
.tab.active{color:#60a5fa;border-bottom-color:#60a5fa;font-weight:600}
.panel{padding:20px 28px}
.filter-bar{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.filter-bar input,.filter-bar select{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#e2e8f0;padding:7px 12px;border-radius:8px;font-size:13px;outline:none}
.filter-bar input:focus,.filter-bar select:focus{border-color:rgba(37,99,235,.5)}
.chip{padding:5px 14px;border-radius:16px;font-size:12px;cursor:pointer;background:rgba(255,255,255,.05);color:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.08);transition:all .2s}
.chip:hover{background:rgba(255,255,255,.1)}
.chip.active{background:rgba(37,99,235,.2);color:#60a5fa;border-color:rgba(37,99,235,.4)}
.chip-group{display:flex;gap:6px;flex-wrap:wrap}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
.strategy-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:18px;transition:all .2s}
.strategy-card:hover{border-color:rgba(37,99,235,.3);background:rgba(255,255,255,.05)}
.strategy-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px}
.strategy-title{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.strategy-desc{font-size:11px;color:rgba(255,255,255,.35);margin-top:3px}
.strategy-metrics{display:flex;gap:16px;margin-bottom:10px}
.metric{text-align:center;flex:1}
.metric-label{font-size:10px;color:rgba(255,255,255,.3);margin-bottom:2px}
.metric-value{font-size:14px;font-weight:600}
.strategy-leader{font-size:11px;color:rgba(255,255,255,.3);margin-bottom:10px}
.product-chip-grid{display:flex;flex-wrap:wrap;gap:6px}
.product-chip{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:8px 10px;cursor:pointer;transition:all .2s;flex:1;min-width:140px}
.product-chip:hover{border-color:rgba(37,99,235,.4);background:rgba(37,99,235,.06)}
.product-chip-name{font-size:11px;font-weight:500;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.product-chip-kpi{display:flex;gap:8px;font-size:11px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{text-align:left;padding:10px 12px;color:rgba(255,255,255,.4);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap}
tbody td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.04)}
tbody tr{cursor:pointer;transition:background .15s}
tbody tr:hover{background:rgba(37,99,235,.06)}
.up{color:#ef4444}.dn{color:#22c55e}
.status-ok{color:#34d399}.status-warn{color:#fbbf24}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal-box{background:#111827;border:1px solid rgba(255,255,255,.1);border-radius:16px;width:700px;max-width:92vw;max-height:85vh;overflow-y:auto}
.modal-header{display:flex;justify-content:space-between;align-items:center;padding:18px 22px;border-bottom:1px solid rgba(255,255,255,.06)}
.modal-header h3{font-size:16px;font-weight:600}
.modal-close{background:none;border:none;color:rgba(255,255,255,.4);font-size:24px;cursor:pointer}
.modal-close:hover{color:#fff}
.modal-body{padding:22px}
.modal-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
.modal-metric{text-align:center;padding:10px;background:rgba(255,255,255,.03);border-radius:8px}
.modal-metric .label{font-size:10px;color:rgba(255,255,255,.35)}
.modal-metric .value{font-size:16px;font-weight:600;margin-top:2px}
'''

# ========== JS ==========
JS_BLOCK = r'''
let currentStrategy = '全部';
let currentTab = 'overview';
let mktPeriod = 'annual';
let navChartInstance = null;

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['overview','detail','market'][i] === tab);
  });
  document.getElementById('panelOverview').style.display = tab === 'overview' ? '' : 'none';
  document.getElementById('panelDetail').style.display = tab === 'detail' ? '' : 'none';
  document.getElementById('panelMarket').style.display = tab === 'market' ? '' : 'none';
  if (tab === 'market') renderMarket();
}

function fmtPct(v) {
  if (v === null || v === undefined) return '-';
  return (v * 100).toFixed(2) + '%';
}
function cls(v) {
  if (v === null || v === undefined) return '';
  return v >= 0 ? 'up' : 'dn';
}

// ===== 策略总览 =====
function renderStrategyFilters() {
  const groups = ['全部', ...new Set(strategySummary.map(g => g.strategy))];
  document.getElementById('strategyFilters').innerHTML = groups.map(g =>
    `<div class="chip ${g === currentStrategy ? 'active' : ''}" onclick="currentStrategy='${g}';renderStrategyFilters();renderCards()">${g}</div>`
  ).join('');
}

function renderCards() {
  const data = currentStrategy === '全部' ? strategySummary : strategySummary.filter(x => x.strategy === currentStrategy);
  document.getElementById('strategyGrid').innerHTML = data.map(group => {
    const items = group.items.slice(0, 4);
    const chips = items.map(item => `
      <div class="product-chip" onclick="showDetail('${item.code}','${item.name.replace(/'/g,"\\'")}')">
        <div class="product-chip-name">${item.name}</div>
        <div class="product-chip-kpi">
          <span class="${cls(item.week_return)}">周 ${fmtPct(item.week_return)}</span>
          <span class="${cls(item.ytd_return)}">YTD ${fmtPct(item.ytd_return)}</span>
        </div>
      </div>`).join('');
    return `
      <div class="strategy-card">
        <div class="strategy-head">
          <div>
            <div class="strategy-title"><span class="dot" style="background:${group.color}"></span>${group.strategy}</div>
            <div class="strategy-desc">${group.description || ''}</div>
          </div>
        </div>
        <div class="strategy-metrics">
          <div class="metric"><div class="metric-label">数量</div><div class="metric-value">${group.count}</div></div>
          <div class="metric"><div class="metric-label">周均值</div><div class="metric-value ${cls(group.avg_week)}">${fmtPct(group.avg_week)}</div></div>
          <div class="metric"><div class="metric-label">YTD均值</div><div class="metric-value ${cls(group.avg_ytd)}">${fmtPct(group.avg_ytd)}</div></div>
        </div>
        <div class="strategy-leader">领先产品：${group.leader}</div>
        <div class="product-chip-grid">${chips}</div>
      </div>`;
  }).join('');
}

// ===== 产品明细 =====
function getAllItems() {
  let all = [];
  strategySummary.forEach(g => g.items.forEach(i => all.push(i)));
  return all;
}

function renderTable() {
  const kw = (document.getElementById('searchInput').value || '').toLowerCase();
  const sort = document.getElementById('sortSelect').value;
  let items = getAllItems();
  if (kw) items = items.filter(i => i.name.toLowerCase().includes(kw));
  if (sort === 'ytd') items.sort((a, b) => (b.ytd_return || 0) - (a.ytd_return || 0));
  else if (sort === 'week') items.sort((a, b) => (b.week_return || 0) - (a.week_return || 0));
  else if (sort === 'month') items.sort((a, b) => (b.month_return || 0) - (a.month_return || 0));
  else items.sort((a, b) => a.name.localeCompare(b.name, 'zh'));

  document.getElementById('detailBody').innerHTML = items.map(item => `
    <tr onclick="showDetail('${item.code}','${item.name.replace(/'/g,"\\'")}')">
      <td>${item.name}</td>
      <td>${item.strategy}</td>
      <td>${item.strategy_detail || '-'}</td>
      <td class="${cls(item.week_return)}">${fmtPct(item.week_return)}</td>
      <td class="${cls(item.month_return)}">${fmtPct(item.month_return)}</td>
      <td class="${cls(item.ytd_return)}">${fmtPct(item.ytd_return)}</td>
      <td>${item.latest_cum_nav ? item.latest_cum_nav.toFixed(4) : '-'}</td>
      <td>${item.latest_date || '-'}</td>
      <td class="${item.status === '正常' ? 'status-ok' : 'status-warn'}">${item.status}</td>
    </tr>`).join('');
}

// ===== 市场基准 =====
function renderMarket() {
  const chips = [['annual','年度'],['monthly','月度'],['quarterly','季度']];
  document.getElementById('mktPeriodChips').innerHTML = chips.map(([k,v]) =>
    `<div class="chip ${k === mktPeriod ? 'active' : ''}" onclick="mktPeriod='${k}';renderMarket()">${v}</div>`
  ).join('');

  const src = mktPeriod === 'annual' ? marketAnnual : mktPeriod === 'monthly' ? marketMonthly : marketQuarterly;
  document.getElementById('mktBody').innerHTML = (src || []).map(item => {
    const name = item.category_name || item.name || '-';
    const ret = item.annualized_return != null ? (item.annualized_return * 100).toFixed(2) + '%' : (item.return_rate != null ? (item.return_rate * 100).toFixed(2) + '%' : '-');
    const sharpe = item.sharpe_ratio != null ? item.sharpe_ratio.toFixed(2) : '-';
    const mdd = item.max_drawdown != null ? (item.max_drawdown * 100).toFixed(2) + '%' : '-';
    const vol = item.volatility != null ? (item.volatility * 100).toFixed(2) + '%' : '-';
    const calmar = item.calmar_ratio != null ? item.calmar_ratio.toFixed(2) : '-';
    return `<tr><td>${name}</td><td>${ret}</td><td>${sharpe}</td><td>${mdd}</td><td>${vol}</td><td>${calmar}</td></tr>`;
  }).join('');
}

// ===== 净值弹窗 =====
function showDetail(code, name) {
  document.getElementById('navModal').style.display = 'flex';
  document.getElementById('modalTitle').textContent = name;
  document.getElementById('modalMetrics').innerHTML = '<div style="color:rgba(255,255,255,.3);text-align:center;padding:20px">加载中...</div>';

  // 找到产品数据
  let item = null;
  strategySummary.forEach(g => g.items.forEach(i => { if (i.code === code) item = i; }));
  if (!item) { document.getElementById('modalMetrics').innerHTML = '未找到产品'; return; }

  // 显示指标
  const metrics = [
    {label: '近一周', value: fmtPct(item.week_return), cls: cls(item.week_return)},
    {label: '近一月', value: fmtPct(item.month_return), cls: cls(item.month_return)},
    {label: '今年以来', value: fmtPct(item.ytd_return), cls: cls(item.ytd_return)},
    {label: '最新净值', value: item.latest_cum_nav ? item.latest_cum_nav.toFixed(4) : '-', cls: ''},
  ];
  document.getElementById('modalMetrics').innerHTML = metrics.map(m =>
    `<div class="modal-metric"><div class="label">${m.label}</div><div class="value ${m.cls}">${m.value}</div></div>`
  ).join('');

  // 净值曲线暂用占位（后续可接 API 实时拉取）
  if (navChartInstance) navChartInstance.destroy();
  const ctx = document.getElementById('navChart').getContext('2d');
  navChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: [item.latest_date || '-'], datasets: [{ label: '累计净值', data: [item.latest_cum_nav], borderColor: '#60a5fa', borderWidth: 2, pointRadius: 4, fill: false }] },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        x: { ticks: { color: 'rgba(255,255,255,.3)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } },
        y: { ticks: { color: 'rgba(255,255,255,.3)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } }
      }
    }
  });
}

function closeModal() {
  document.getElementById('navModal').style.display = 'none';
  if (navChartInstance) { navChartInstance.destroy(); navChartInstance = null; }
}

// ===== 初始化 =====
renderStrategyFilters();
renderCards();
renderTable();
'''


if __name__ == '__main__':
    render()
