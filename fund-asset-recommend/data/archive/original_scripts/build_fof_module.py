#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMT Dashboard - 填充FOF组合管理模块
基于v3，将module-fof的空壳替换为飞虹路-鑫益大方向1号的组合分析
"""
import json, re, os, hashlib, time, math, requests
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

COMBI_ID = 'f3a5298b3ec32ce7'
COMBI_NAME = '飞虹路-鑫益大方向1号'

def api_sign(params):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    s = '&'.join([f'{k}={params[k]}' for k in sorted_keys]) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()

def fetch_combi_nav():
    tm = str(int(time.time()))
    params = {'app_id': APP_ID, 'id': COMBI_ID, 'tm': tm}
    params['sign'] = api_sign(params)
    r = requests.get(f'{BASE_URL}/combi/price', params=params, timeout=15, verify=False)
    data = r.json().get('data', [])
    data.sort(key=lambda x: x['price_date'])
    return data

def compute_metrics(data):
    """计算组合的各项指标"""
    navs = [d['cumulative_nav'] for d in data]
    dates = [d['price_date'] for d in data]
    
    latest = data[-1]
    first = data[0]
    
    # 总收益
    total_ret = latest['cumulative_nav'] / first['cumulative_nav'] - 1
    
    # 年化收益
    d0 = datetime.strptime(first['price_date'], '%Y-%m-%d')
    d1 = datetime.strptime(latest['price_date'], '%Y-%m-%d')
    days = (d1 - d0).days
    ann_ret = (latest['cumulative_nav'] / first['cumulative_nav']) ** (365/max(days,1)) - 1
    
    # 日收益率序列
    returns = [(navs[i]/navs[i-1]-1) for i in range(1, len(navs))]
    
    # 年化波动率
    avg_ret = sum(returns)/len(returns)
    var = sum((r-avg_ret)**2 for r in returns) / (len(returns)-1)
    ann_vol = math.sqrt(var) * math.sqrt(252)
    
    # 夏普比率
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    
    # 最大回撤
    peak = navs[0]
    max_dd = 0
    dd_start = dd_end = dates[0]
    dd_peak_date = dates[0]
    for i, v in enumerate(navs):
        if v > peak:
            peak = v
            dd_peak_date = dates[i]
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
            dd_start = dd_peak_date
            dd_end = dates[i]
    
    # 卡玛比率
    calmar = ann_ret / max_dd if max_dd > 0 else 0
    
    # 当前回撤
    current_dd = (max(navs) - navs[-1]) / max(navs)
    
    # 胜率
    pos_days = sum(1 for r in returns if r > 0)
    neg_days = sum(1 for r in returns if r < 0)
    win_rate = pos_days / len(returns) if returns else 0
    
    # 最大单日涨跌
    max_up = max(returns) if returns else 0
    max_down = min(returns) if returns else 0
    max_up_date = dates[returns.index(max_up)+1] if returns else '-'
    max_down_date = dates[returns.index(max_down)+1] if returns else '-'
    
    # YTD
    ytd_base = None
    for d in data:
        if d['price_date'] <= '2025-12-31':
            ytd_base = d['cumulative_nav']
    ytd_ret = (latest['cumulative_nav'] / ytd_base - 1) if ytd_base else None
    
    # 近一周 (截止4月10日)
    stat_end = None
    stat_end_prev = None
    for d in data:
        if d['price_date'] <= '2026-04-10':
            stat_end = d
    for d in data:
        if d['price_date'] <= '2026-04-03':
            stat_end_prev = d
    week_ret = (stat_end['cumulative_nav'] / stat_end_prev['cumulative_nav'] - 1) if stat_end and stat_end_prev else None
    
    # 近一月
    month_base = None
    for d in data:
        if d['price_date'] <= '2026-03-31':
            month_base = d
    month_ret = (stat_end['cumulative_nav'] / month_base['cumulative_nav'] - 1) if stat_end and month_base else None
    
    # 月度收益
    monthly = {}
    for d in data:
        ym = d['price_date'][:7]
        monthly[ym] = d['cumulative_nav']
    months = sorted(monthly.keys())
    monthly_returns = []
    for i in range(1, len(months)):
        ret = monthly[months[i]] / monthly[months[i-1]] - 1
        monthly_returns.append({'month': months[i], 'return': ret})
    
    return {
        'name': COMBI_NAME,
        'combi_id': COMBI_ID,
        'start_date': first['price_date'],
        'end_date': latest['price_date'],
        'latest_nav': latest['cumulative_nav'],
        'run_days': days,
        'total_ret': total_ret,
        'ann_ret': ann_ret,
        'ann_vol': ann_vol,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'dd_period': f'{dd_start} ~ {dd_end}',
        'current_dd': current_dd,
        'calmar': calmar,
        'win_rate': win_rate,
        'pos_days': pos_days,
        'neg_days': neg_days,
        'max_up': max_up,
        'max_up_date': max_up_date,
        'max_down': max_down,
        'max_down_date': max_down_date,
        'ytd_ret': ytd_ret,
        'week_ret': week_ret,
        'month_ret': month_ret,
        'monthly_returns': monthly_returns,
        'nav_data': [[d['price_date'], d['cumulative_nav']] for d in data],
        'dd_data': compute_drawdown_series(data),
    }

def compute_drawdown_series(data):
    """计算回撤序列"""
    navs = [d['cumulative_nav'] for d in data]
    dates = [d['price_date'] for d in data]
    peak = navs[0]
    result = []
    for i, v in enumerate(navs):
        if v > peak: peak = v
        dd = (peak - v) / peak
        result.append([dates[i], -dd])
    return result

def build_fof_html(metrics):
    m = metrics
    return f'''
    <div class="card">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h1>FOF组合管理</h1>
          <div class="sub">组合：{m['name']} ｜ 运行 {m['run_days']} 天 ｜ {m['start_date']} ~ {m['end_date']}<br/>统计截至 2026-04-10 ｜ 最新净值至 {m['end_date']}</div>
        </div>
        <div class="topbar-tag">组合分析报告</div>
      </div>

      <div class="section"><div class="stats">
        <div class="stat"><div class="label">最新累计净值</div><div class="value">{m['latest_nav']:.4f}</div></div>
        <div class="stat"><div class="label">今年以来</div><div class="value {"pos" if m['ytd_ret'] and m['ytd_ret']>0 else "neg"}">{m['ytd_ret']*100:+.2f}%</div></div>
        <div class="stat"><div class="label">近一周</div><div class="value {"pos" if m['week_ret'] and m['week_ret']>0 else "neg"}">{m['week_ret']*100:+.2f}%</div></div>
        <div class="stat"><div class="label">近一月</div><div class="value {"pos" if m['month_ret'] and m['month_ret']>0 else "neg"}">{m['month_ret']*100:+.2f}%</div></div>
        <div class="stat"><div class="label">成立以来</div><div class="value pos">{m['total_ret']*100:+.2f}%</div></div>
        <div class="stat"><div class="label">年化收益</div><div class="value pos">{m['ann_ret']*100:.2f}%</div></div>
      </div></div>

      <div class="section">
        <div class="section-title">📈 累计净值走势</div>
        <canvas id="fofNavChart" style="width:100%;border:1px solid var(--line);border-radius:10px;"></canvas>
      </div>

      <div class="section">
        <div class="section-title">📉 回撤走势</div>
        <canvas id="fofDdChart" style="width:100%;border:1px solid var(--line);border-radius:10px;"></canvas>
      </div>

      <div class="section">
        <div class="section-title">风险收益指标</div>
        <div class="fof-metrics-grid">
          <div class="fof-metric-card">
            <div class="fof-metric-icon">📊</div>
            <div class="fof-metric-label">年化波动率</div>
            <div class="fof-metric-val">{m['ann_vol']*100:.2f}%</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">⚡</div>
            <div class="fof-metric-label">夏普比率</div>
            <div class="fof-metric-val">{m['sharpe']:.2f}</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">🛡️</div>
            <div class="fof-metric-label">最大回撤</div>
            <div class="fof-metric-val neg">{m['max_dd']*100:.2f}%</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">🎯</div>
            <div class="fof-metric-label">卡玛比率</div>
            <div class="fof-metric-val">{m['calmar']:.2f}</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">📅</div>
            <div class="fof-metric-label">当前回撤</div>
            <div class="fof-metric-val neg">{m['current_dd']*100:.2f}%</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">🏆</div>
            <div class="fof-metric-label">日胜率</div>
            <div class="fof-metric-val">{m['win_rate']*100:.1f}%</div>
            <div class="fof-metric-sub">涨{m['pos_days']}天 / 跌{m['neg_days']}天</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">🔺</div>
            <div class="fof-metric-label">最大单日涨幅</div>
            <div class="fof-metric-val pos">{m['max_up']*100:+.2f}%</div>
            <div class="fof-metric-sub">{m['max_up_date']}</div>
          </div>
          <div class="fof-metric-card">
            <div class="fof-metric-icon">🔻</div>
            <div class="fof-metric-label">最大单日跌幅</div>
            <div class="fof-metric-val neg">{m['max_down']*100:.2f}%</div>
            <div class="fof-metric-sub">{m['max_down_date']}</div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">📅 月度收益</div>
        <div class="fof-monthly-grid" id="fofMonthlyGrid"></div>
      </div>

      <div class="section">
        <div class="section-title">最大回撤区间</div>
        <div class="note">最大回撤 {m['max_dd']*100:.2f}% 发生在 {m['dd_period']}。当前距离历史最高点回撤 {m['current_dd']*100:.2f}%。</div>
      </div>

      <div class="section"><div class="note">说明：本组合为火富牛模拟组合（ID: {m['combi_id']}），净值数据来源于 /combi/price API。<br/>近一周统计区间：2026-04-03 ~ 2026-04-10 ｜ 近一月：2026-03-31 ~ 2026-04-10 ｜ 今年以来：2025-12-31 ~ 2026-04-10<br/>风险指标基于日频净值计算，年化波动率 = 日波动率 × √252，夏普比率无风险利率取2%。</div></div>
    </div>
'''

def build_fof_js(metrics):
    nav_json = json.dumps(metrics['nav_data'], ensure_ascii=False)
    dd_json = json.dumps(metrics['dd_data'], ensure_ascii=False)
    monthly_json = json.dumps(metrics['monthly_returns'], ensure_ascii=False)
    return f'''
const fofNavData = {nav_json};
const fofDdData = {dd_json};
const fofMonthly = {monthly_json};

function drawFofChart(canvasId, data, color, fillColor, yFmt, invert) {{
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.parentElement.clientWidth || 800;
  const h = 280;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  
  const pad = {{top:20, right:20, bottom:40, left:65}};
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;
  
  const vals = data.map(d => d[1]);
  const dates = data.map(d => d[0]);
  let minV = Math.min(...vals);
  let maxV = Math.max(...vals);
  if (invert) {{ minV = minV * 1.05; maxV = Math.max(maxV, 0); }}
  else {{ minV = minV * 0.998; maxV = maxV * 1.002; }}
  const range = maxV - minV || 0.01;
  
  // Grid
  ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {{
    const y = pad.top + ch * (1 - i/4);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left+cw, y); ctx.stroke();
    ctx.fillStyle = '#94a3b8'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right';
    const v = minV + range * i/4;
    ctx.fillText(yFmt(v), pad.left - 8, y + 4);
  }}
  
  // X labels
  ctx.fillStyle = '#94a3b8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(dates.length / 6));
  for (let i = 0; i < dates.length; i += step) {{
    const x = pad.left + (i / (dates.length-1)) * cw;
    ctx.fillText(dates[i].slice(5), x, h - pad.bottom + 20);
  }}
  
  // Line
  ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = 'round';
  for (let i = 0; i < vals.length; i++) {{
    const x = pad.left + (i / (vals.length-1)) * cw;
    const y = pad.top + ch * (1 - (vals[i] - minV) / range);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }}
  ctx.stroke();
  
  // Fill
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
  grad.addColorStop(0, fillColor);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.lineTo(pad.left + cw, pad.top + ch);
  ctx.lineTo(pad.left, pad.top + ch);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
}}

function renderFofCharts() {{
  drawFofChart('fofNavChart', fofNavData, '#2563eb', 'rgba(37,99,235,0.1)', v => v.toFixed(4), false);
  drawFofChart('fofDdChart', fofDdData, '#ef4444', 'rgba(239,68,68,0.08)', v => (v*100).toFixed(1)+'%', true);
  
  // Monthly grid
  const grid = document.getElementById('fofMonthlyGrid');
  if (grid) {{
    grid.innerHTML = fofMonthly.map(m => {{
      const v = m['return'];
      const cls = v > 0 ? 'pos' : v < 0 ? 'neg' : '';
      const pct = (v * 100).toFixed(2);
      const barH = Math.min(Math.abs(v) / 0.07 * 100, 100);
      const barColor = v > 0 ? 'var(--primary)' : 'var(--up)';
      return `<div class="fof-month-item">
        <div class="fof-month-bar-wrap"><div class="fof-month-bar" style="height:${{barH}}%;background:${{barColor}}"></div></div>
        <div class="fof-month-val ${{cls}}">${{pct}}%</div>
        <div class="fof-month-label">${{m.month.slice(5)}}</div>
      </div>`;
    }}).join('');
  }}
}}
'''

FOF_CSS = """
/* FOF Module */
.fof-metrics-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.fof-metric-card { background:var(--panel-soft); border:1px solid var(--line); border-radius:12px; padding:16px; text-align:center; }
.fof-metric-icon { font-size:24px; margin-bottom:6px; }
.fof-metric-label { font-size:11px; color:var(--muted); margin-bottom:4px; }
.fof-metric-val { font-size:20px; font-weight:800; color:var(--text); }
.fof-metric-sub { font-size:10px; color:var(--muted); margin-top:2px; }
.fof-monthly-grid { display:flex; gap:6px; align-items:flex-end; height:140px; padding:10px 0; }
.fof-month-item { flex:1; display:flex; flex-direction:column; align-items:center; }
.fof-month-bar-wrap { flex:1; width:100%; display:flex; align-items:flex-end; justify-content:center; }
.fof-month-bar { width:70%; border-radius:4px 4px 0 0; min-height:2px; transition:height .3s; }
.fof-month-val { font-size:10px; font-weight:700; margin-top:4px; }
.fof-month-label { font-size:10px; color:var(--muted); }
@media(max-width:900px) { .fof-metrics-grid { grid-template-columns:repeat(2,1fr); } }
"""

def main():
    print("📡 拉取飞虹路-鑫益大方向1号净值数据...")
    data = fetch_combi_nav()
    print(f"  {len(data)}条净值, {data[0]['price_date']} ~ {data[-1]['price_date']}")
    
    metrics = compute_metrics(data)
    print(f"  总收益: {metrics['total_ret']*100:.2f}%")
    print(f"  年化: {metrics['ann_ret']*100:.2f}%")
    print(f"  夏普: {metrics['sharpe']:.2f}")
    print(f"  最大回撤: {metrics['max_dd']*100:.2f}%")
    
    # 读取v3 HTML
    src = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(src, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 替换module-fof内容
    fof_html = build_fof_html(metrics)
    old_fof = re.search(
        r'(<section class="module-panel" id="module-fof">)(.*?)(</section>)',
        html, re.DOTALL
    )
    if old_fof:
        html = html[:old_fof.start(2)] + '\n' + fof_html + '\n' + html[old_fof.end(2):]
        print("✅ 替换了module-fof内容")
    
    # 注入JS
    fof_js = build_fof_js(metrics)
    # 在renderAll定义之前注入
    ra_pos = html.index('function renderAll()')
    html = html[:ra_pos] + fof_js + '\n' + html[ra_pos:]
    
    # 在renderAll中加入renderFofCharts
    html = html.replace(
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); }',
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); renderFofCharts(); }'
    )
    
    # 注入CSS
    style_end = html.index('</style>')
    html = html[:style_end] + FOF_CSS + html[style_end:]
    
    # 更新时间
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = re.sub(r'生成时间 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', f'生成时间 {now}', html)
    
    # 更新侧边栏
    html = html.replace(
        '已接入：GAMT核心资产<br/>\n      预留：市场策略看板 / FOF组合管理',
        '三模块均已接入<br/>\n      市场策略 / 核心资产 / FOF组合'
    )
    
    out = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ 已更新: {out}')
    print(f'   file://{out}')

if __name__ == '__main__':
    main()

