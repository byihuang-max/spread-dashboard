#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMT Dashboard - FOF组合管理模块 v2
多组合卡片列表 + 点击弹出详情分析
"""
import json, re, os, hashlib, time, math, requests
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

COMBIS = [
    ('f3a5298b3ec32ce7', '飞虹路-鑫益大方向1号'),
    ('bb24bad1d31a4173', '长盛71号'),
    ('ea21daabf8d35fd6', '飞虹路-长盛65号'),
    ('63983e4cd5cdda5f', '君宜安鑫'),
    ('52b8287b5c62e21b', '宁涌富春分8号（凌总）组合'),
]

def api_sign(params):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    s = '&'.join([f'{k}={params[k]}' for k in sorted_keys]) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()

def fetch_combi_nav(combi_id):
    tm = str(int(time.time()))
    params = {'app_id': APP_ID, 'id': combi_id, 'tm': tm}
    params['sign'] = api_sign(params)
    r = requests.get(f'{BASE_URL}/combi/price', params=params, timeout=15, verify=False)
    data = r.json().get('data', [])
    if data:
        data.sort(key=lambda x: x['price_date'])
    return data

def compute_metrics(data, name, combi_id):
    navs = [d['cumulative_nav'] for d in data]
    dates = [d['price_date'] for d in data]
    latest = data[-1]
    first = data[0]
    total_ret = latest['cumulative_nav'] / first['cumulative_nav'] - 1
    d0 = datetime.strptime(first['price_date'], '%Y-%m-%d')
    d1 = datetime.strptime(latest['price_date'], '%Y-%m-%d')
    days = (d1 - d0).days
    ann_ret = (latest['cumulative_nav'] / first['cumulative_nav']) ** (365/max(days,1)) - 1
    returns = [(navs[i]/navs[i-1]-1) for i in range(1, len(navs))]
    avg_ret = sum(returns)/len(returns) if returns else 0
    var = sum((r-avg_ret)**2 for r in returns) / max(len(returns)-1, 1)
    ann_vol = math.sqrt(var) * math.sqrt(252)
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    peak = navs[0]; max_dd = 0; dd_start = dd_end = dates[0]; dd_peak_date = dates[0]
    for i, v in enumerate(navs):
        if v > peak: peak = v; dd_peak_date = dates[i]
        dd = (peak - v) / peak
        if dd > max_dd: max_dd = dd; dd_start = dd_peak_date; dd_end = dates[i]
    calmar = ann_ret / max_dd if max_dd > 0 else 0
    current_dd = (max(navs) - navs[-1]) / max(navs)
    pos_days = sum(1 for r in returns if r > 0)
    neg_days = sum(1 for r in returns if r < 0)
    win_rate = pos_days / len(returns) if returns else 0
    max_up = max(returns) if returns else 0
    max_down = min(returns) if returns else 0
    max_up_date = dates[returns.index(max_up)+1] if returns else '-'
    max_down_date = dates[returns.index(max_down)+1] if returns else '-'
    ytd_base = None
    for d in data:
        if d['price_date'] <= '2025-12-31': ytd_base = d['cumulative_nav']
    ytd_ret = (latest['cumulative_nav'] / ytd_base - 1) if ytd_base else None
    stat_end = stat_prev = month_base = None
    for d in data:
        if d['price_date'] <= '2026-04-10': stat_end = d
    for d in data:
        if d['price_date'] <= '2026-04-03': stat_prev = d
    for d in data:
        if d['price_date'] <= '2026-03-31': month_base = d
    week_ret = (stat_end['cumulative_nav']/stat_prev['cumulative_nav']-1) if stat_end and stat_prev else None
    month_ret = (stat_end['cumulative_nav']/month_base['cumulative_nav']-1) if stat_end and month_base else None
    # monthly returns
    monthly = {}
    for d in data:
        ym = d['price_date'][:7]; monthly[ym] = d['cumulative_nav']
    months = sorted(monthly.keys())
    monthly_returns = [{'month': months[i], 'return': monthly[months[i]]/monthly[months[i-1]]-1} for i in range(1, len(months))]
    # drawdown series
    dd_series = []; pk = navs[0]
    for i, v in enumerate(navs):
        if v > pk: pk = v
        dd_series.append([dates[i], -(pk-v)/pk])
    return {
        'name': name, 'combi_id': combi_id,
        'start_date': first['price_date'], 'end_date': latest['price_date'],
        'latest_nav': latest['cumulative_nav'], 'run_days': days,
        'total_ret': total_ret, 'ann_ret': ann_ret, 'ann_vol': ann_vol,
        'sharpe': sharpe, 'max_dd': max_dd, 'dd_period': f'{dd_start} ~ {dd_end}',
        'current_dd': current_dd, 'calmar': calmar,
        'win_rate': win_rate, 'pos_days': pos_days, 'neg_days': neg_days,
        'max_up': max_up, 'max_up_date': max_up_date,
        'max_down': max_down, 'max_down_date': max_down_date,
        'ytd_ret': ytd_ret, 'week_ret': week_ret, 'month_ret': month_ret,
        'monthly_returns': monthly_returns,
        'nav_data': [[d['price_date'], d['cumulative_nav']] for d in data],
        'dd_data': dd_series,
    }

def build_fof_html():
    return '''
    <div class="card">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h1>FOF组合管理</h1>
          <div class="sub">统计截至 2026-04-10 ｜ 最新净值至 2026-04-15 ｜ 点击组合卡片查看详细分析报告</div>
        </div>
        <div class="topbar-tag">组合分析</div>
      </div>
      <div class="section">
        <div class="section-title">组合总览</div>
        <div class="fof-card-grid" id="fofCardGrid"></div>
      </div>
      <div class="section">
        <div class="section-title">组合对比</div>
        <div class="fof-compare-wrap"><table class="mkt-table"><thead><tr>
          <th>组合</th><th>运行天数</th><th>最新净值</th><th>近一周</th><th>近一月</th><th>今年以来</th><th>成立以来</th><th>年化收益</th><th>夏普</th><th>最大回撤</th><th>卡玛</th><th>波动率</th>
        </tr></thead><tbody id="fofCompareBody"></tbody></table></div>
      </div>
      <div class="section"><div class="note">说明：数据来源火富牛模拟组合 /combi/price API。近一周：2026-04-03~2026-04-10 ｜ 近一月：2026-03-31~2026-04-10 ｜ 今年以来：2025-12-31~2026-04-10。夏普无风险利率取2%，年化波动率=日波动率×√252。</div></div>
    </div>
    <div id="fofDetailModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,23,42,.5);backdrop-filter:blur(4px);z-index:1001;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:16px;width:92%;max-width:920px;max-height:92vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.15);">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid #e2e8f0;">
          <h2 id="fofModalTitle" style="margin:0;font-size:20px;font-weight:800;color:#0f172a;"></h2>
          <button id="fofModalClose" style="border:none;background:#f1f5f9;color:#64748b;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;">✕</button>
        </div>
        <div style="padding:20px 24px;" id="fofModalBody"></div>
      </div>
    </div>
'''

def build_fof_js(all_metrics):
    data_json = json.dumps(all_metrics, ensure_ascii=False)
    return f'''
const fofCombis = {data_json};
function fmtP(v,d){{if(v===null||v===undefined)return'-';return(v*100).toFixed(d||2)+'%';}}
function fmtN(v,d){{if(v===null||v===undefined)return'-';return v.toFixed(d||2);}}
function pcls(v){{return v>0?'pos':v<0?'neg':'';}}
function renderFofCards(){{
  const grid=document.getElementById('fofCardGrid');if(!grid)return;
  grid.innerHTML=fofCombis.map((c,idx)=>`<div class="fof-summary-card" onclick="showFofDetail(${{idx}})">
    <div class="fof-card-header"><div class="fof-card-name">${{c.name}}</div><div class="fof-card-badge">${{c.run_days}}天</div></div>
    <div class="fof-card-nav">${{c.latest_nav.toFixed(4)}}</div>
    <div class="fof-card-kpis">
      <div class="fof-card-kpi"><span>近一周</span><span class="${{pcls(c.week_ret)}}">${{fmtP(c.week_ret)}}</span></div>
      <div class="fof-card-kpi"><span>YTD</span><span class="${{pcls(c.ytd_ret)}}">${{fmtP(c.ytd_ret)}}</span></div>
      <div class="fof-card-kpi"><span>年化</span><span class="${{pcls(c.ann_ret)}}">${{fmtP(c.ann_ret)}}</span></div>
      <div class="fof-card-kpi"><span>夏普</span><span>${{fmtN(c.sharpe)}}</span></div>
      <div class="fof-card-kpi"><span>回撤</span><span class="neg">${{fmtP(c.max_dd)}}</span></div>
      <div class="fof-card-kpi"><span>卡玛</span><span>${{fmtN(c.calmar)}}</span></div>
    </div></div>`).join('');
  const body=document.getElementById('fofCompareBody');
  body.innerHTML=fofCombis.map((c,idx)=>`<tr onclick="showFofDetail(${{idx}})" style="cursor:pointer">
    <td style="font-weight:600">${{c.name}}</td><td>${{c.run_days}}</td><td>${{c.latest_nav.toFixed(4)}}</td>
    <td class="${{pcls(c.week_ret)}}">${{fmtP(c.week_ret)}}</td><td class="${{pcls(c.month_ret)}}">${{fmtP(c.month_ret)}}</td>
    <td class="${{pcls(c.ytd_ret)}}">${{fmtP(c.ytd_ret)}}</td><td class="${{pcls(c.total_ret)}}">${{fmtP(c.total_ret)}}</td>
    <td class="${{pcls(c.ann_ret)}}">${{fmtP(c.ann_ret)}}</td><td>${{fmtN(c.sharpe)}}</td>
    <td class="neg">${{fmtP(c.max_dd)}}</td><td>${{fmtN(c.calmar)}}</td><td>${{fmtP(c.ann_vol)}}</td></tr>`).join('');
}}
function showFofDetail(idx){{
  const c=fofCombis[idx],modal=document.getElementById('fofDetailModal');
  document.getElementById('fofModalTitle').textContent=c.name;modal.style.display='flex';
  document.getElementById('fofModalBody').innerHTML=`
    <div class="stats" style="margin-bottom:16px">
      <div class="stat"><div class="label">最新净值</div><div class="value">${{c.latest_nav.toFixed(4)}}</div></div>
      <div class="stat"><div class="label">今年以来</div><div class="value ${{pcls(c.ytd_ret)}}">${{fmtP(c.ytd_ret)}}</div></div>
      <div class="stat"><div class="label">近一周</div><div class="value ${{pcls(c.week_ret)}}">${{fmtP(c.week_ret)}}</div></div>
      <div class="stat"><div class="label">近一月</div><div class="value ${{pcls(c.month_ret)}}">${{fmtP(c.month_ret)}}</div></div>
      <div class="stat"><div class="label">成立以来</div><div class="value ${{pcls(c.total_ret)}}">${{fmtP(c.total_ret)}}</div></div>
      <div class="stat"><div class="label">年化收益</div><div class="value ${{pcls(c.ann_ret)}}">${{fmtP(c.ann_ret)}}</div></div>
    </div>
    <div style="font-size:14px;font-weight:700;margin:12px 0 8px">📈 累计净值走势</div>
    <canvas id="fofModalNav" style="width:100%;border:1px solid #e2e8f0;border-radius:10px"></canvas>
    <div style="font-size:14px;font-weight:700;margin:16px 0 8px">📉 回撤走势</div>
    <canvas id="fofModalDd" style="width:100%;border:1px solid #e2e8f0;border-radius:10px"></canvas>
    <div style="font-size:14px;font-weight:700;margin:16px 0 8px">风险收益指标</div>
    <div class="fof-metrics-grid">
      <div class="fof-metric-card"><div class="fof-metric-icon">📊</div><div class="fof-metric-label">年化波动率</div><div class="fof-metric-val">${{fmtP(c.ann_vol)}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">⚡</div><div class="fof-metric-label">夏普比率</div><div class="fof-metric-val">${{fmtN(c.sharpe)}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">🛡️</div><div class="fof-metric-label">最大回撤</div><div class="fof-metric-val neg">${{fmtP(c.max_dd)}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">🎯</div><div class="fof-metric-label">卡玛比率</div><div class="fof-metric-val">${{fmtN(c.calmar)}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">📅</div><div class="fof-metric-label">当前回撤</div><div class="fof-metric-val neg">${{fmtP(c.current_dd)}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">🏆</div><div class="fof-metric-label">日胜率</div><div class="fof-metric-val">${{fmtP(c.win_rate,1)}}</div><div class="fof-metric-sub">涨${{c.pos_days}}天/跌${{c.neg_days}}天</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">🔺</div><div class="fof-metric-label">最大单日涨</div><div class="fof-metric-val pos">${{fmtP(c.max_up)}}</div><div class="fof-metric-sub">${{c.max_up_date}}</div></div>
      <div class="fof-metric-card"><div class="fof-metric-icon">🔻</div><div class="fof-metric-label">最大单日跌</div><div class="fof-metric-val neg">${{fmtP(c.max_down)}}</div><div class="fof-metric-sub">${{c.max_down_date}}</div></div>
    </div>
    <div style="font-size:14px;font-weight:700;margin:16px 0 8px">📅 月度收益</div>
    <div class="fof-monthly-grid" id="fofModalMonthly"></div>
    <div class="note" style="margin-top:12px">运行${{c.run_days}}天 ｜ ${{c.start_date}}~${{c.end_date}} ｜ 最大回撤区间：${{c.dd_period}}</div>`;
  setTimeout(()=>{{
    drawFofLine('fofModalNav',c.nav_data,'#2563eb','rgba(37,99,235,0.1)',v=>v.toFixed(4),false);
    drawFofLine('fofModalDd',c.dd_data,'#ef4444','rgba(239,68,68,0.08)',v=>(v*100).toFixed(1)+'%',true);
    const mg=document.getElementById('fofModalMonthly');
    if(mg){{mg.innerHTML=c.monthly_returns.map(m=>{{const v=m['return'],cls=v>0?'pos':v<0?'neg':'',barH=Math.min(Math.abs(v)/0.07*100,100),barColor=v>0?'var(--primary)':'var(--up)';return`<div class="fof-month-item"><div class="fof-month-bar-wrap"><div class="fof-month-bar" style="height:${{barH}}%;background:${{barColor}}"></div></div><div class="fof-month-val ${{cls}}">${{(v*100).toFixed(2)}}%</div><div class="fof-month-label">${{m.month.slice(5)}}月</div></div>`;}}).join('');}}
  }},50);
}}
function drawFofLine(id,data,color,fill,yFmt,inv){{
  const cv=document.getElementById(id);if(!cv)return;
  const dpr=window.devicePixelRatio||1,w=cv.parentElement.clientWidth||800,h=260;
  cv.width=w*dpr;cv.height=h*dpr;cv.style.width=w+'px';cv.style.height=h+'px';
  const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);
  const p={{top:16,right:16,bottom:36,left:60}},cw=w-p.left-p.right,ch=h-p.top-p.bottom;
  const vals=data.map(d=>d[1]),dates=data.map(d=>d[0]);
  let mn=Math.min(...vals),mx=Math.max(...vals);
  if(inv){{mn*=1.05;mx=Math.max(mx,0);}}else{{mn*=0.998;mx*=1.002;}}
  const rng=mx-mn||0.01;
  ctx.strokeStyle='#e2e8f0';ctx.lineWidth=0.5;
  for(let i=0;i<=4;i++){{const y=p.top+ch*(1-i/4);ctx.beginPath();ctx.moveTo(p.left,y);ctx.lineTo(p.left+cw,y);ctx.stroke();ctx.fillStyle='#94a3b8';ctx.font='11px sans-serif';ctx.textAlign='right';ctx.fillText(yFmt(mn+rng*i/4),p.left-8,y+4);}}
  ctx.fillStyle='#94a3b8';ctx.font='10px sans-serif';ctx.textAlign='center';
  const st=Math.max(1,Math.floor(dates.length/6));
  for(let i=0;i<dates.length;i+=st){{const x=p.left+(i/(dates.length-1))*cw;ctx.fillText(dates[i].slice(5),x,h-p.bottom+18);}}
  ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineJoin='round';
  for(let i=0;i<vals.length;i++){{const x=p.left+(i/(vals.length-1))*cw,y=p.top+ch*(1-(vals[i]-mn)/rng);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}}
  ctx.stroke();
  const g=ctx.createLinearGradient(0,p.top,0,p.top+ch);g.addColorStop(0,fill);g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.lineTo(p.left+cw,p.top+ch);ctx.lineTo(p.left,p.top+ch);ctx.closePath();ctx.fillStyle=g;ctx.fill();
}}
document.getElementById('fofModalClose').onclick=()=>document.getElementById('fofDetailModal').style.display='none';
document.getElementById('fofDetailModal').onclick=(e)=>{{if(e.target.id==='fofDetailModal')e.target.style.display='none';}};
'''

FOF_CSS = """
/* FOF Module */
.fof-card-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }
.fof-summary-card { background:var(--panel-soft); border:1px solid var(--line); border-radius:14px; padding:18px; cursor:pointer; transition:all .2s; }
.fof-summary-card:hover { border-color:#94a3b8; box-shadow:var(--shadow-md); transform:translateY(-1px); }
.fof-card-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.fof-card-name { font-size:15px; font-weight:700; color:#0f172a; }
.fof-card-badge { font-size:10px; background:var(--primary-soft); color:var(--primary); padding:3px 10px; border-radius:999px; font-weight:600; }
.fof-card-nav { font-size:28px; font-weight:800; color:#0f172a; margin-bottom:10px; }
.fof-card-kpis { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }
.fof-card-kpi { display:flex; justify-content:space-between; font-size:11px; padding:4px 0; border-bottom:1px dashed var(--line-soft); }
.fof-card-kpi span:first-child { color:var(--muted); }
.fof-card-kpi span:last-child { font-weight:600; }
.fof-compare-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:#fff; }
.fof-metrics-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
.fof-metric-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:center; }
.fof-metric-icon { font-size:22px; margin-bottom:4px; }
.fof-metric-label { font-size:11px; color:#64748b; margin-bottom:3px; }
.fof-metric-val { font-size:18px; font-weight:800; color:#0f172a; }
.fof-metric-sub { font-size:10px; color:#94a3b8; margin-top:2px; }
.fof-monthly-grid { display:flex; gap:6px; align-items:flex-end; height:120px; padding:8px 0; }
.fof-month-item { flex:1; display:flex; flex-direction:column; align-items:center; }
.fof-month-bar-wrap { flex:1; width:100%; display:flex; align-items:flex-end; justify-content:center; }
.fof-month-bar { width:65%; border-radius:4px 4px 0 0; min-height:2px; }
.fof-month-val { font-size:10px; font-weight:700; margin-top:3px; }
.fof-month-label { font-size:9px; color:#94a3b8; }
@media(max-width:900px){.fof-metrics-grid{grid-template-columns:repeat(2,1fr);}.fof-card-grid{grid-template-columns:1fr;}}
"""

def main():
    all_metrics = []
    for cid, name in COMBIS:
        print(f'📡 {name}...', end=' ', flush=True)
        data = fetch_combi_nav(cid)
        if data:
            m = compute_metrics(data, name, cid)
            all_metrics.append(m)
            print(f'✅ {len(data)}条, 年化{m["ann_ret"]*100:.1f}%, 夏普{m["sharpe"]:.2f}')
        else:
            print('❌')
        time.sleep(0.3)
    src = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(src, 'r', encoding='utf-8') as f:
        html = f.read()
    fof_html = build_fof_html()
    old_fof = re.search(r'(<section class="module-panel" id="module-fof">)(.*?)(</section>)', html, re.DOTALL)
    if old_fof:
        html = html[:old_fof.start(2)] + '\n' + fof_html + '\n' + html[old_fof.end(2):]
        print('✅ 替换了module-fof')
    # Remove old fof JS
    for pat in [r'const fofNavData = .*?;\n', r'const fofDdData = .*?;\n', r'const fofMonthly = .*?;\n',
                r'const fofCombis = .*?;\n']:
        html = re.sub(pat, '', html)
    html = re.sub(r'function drawFofChart\(.*?\}\n', '', html, flags=re.DOTALL)
    html = re.sub(r'function renderFofCharts\(.*?\}\n', '', html, flags=re.DOTALL)
    fof_js = build_fof_js(all_metrics)
    ra_pos = html.index('function renderAll()')
    html = html[:ra_pos] + fof_js + '\n' + html[ra_pos:]
    for old in ['renderFofCharts();', 'renderFofCards();']:
        html = html.replace(old, '')
    html = html.replace(
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket();  }',
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); renderFofCards(); }'
    )
    html = html.replace(
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); }',
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); renderFofCards(); }'
    )
    html = re.sub(r'/\* FOF Module \*/.*?(?=</style>)', '', html, flags=re.DOTALL)
    style_end = html.index('</style>')
    html = html[:style_end] + FOF_CSS + html[style_end:]
    html = html.replace('三模块均已接入', '三模块均已接入')
    html = html.replace('已接入：GAMT核心资产', '三模块均已接入')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = re.sub(r'生成时间 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', f'生成时间 {now}', html)
    out = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ 已更新: {out}')
    print(f'   file://{out}')

if __name__ == '__main__':
    main()

