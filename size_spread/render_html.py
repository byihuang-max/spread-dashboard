#!/usr/bin/env python3
"""从 style_spread.json 生成静态 HTML 看板（v2 card格式 + MA20）"""
import json, sys, os

_BASE = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(_BASE, 'data', 'style_spread.json')
out_en = os.path.join(_BASE, 'style_spread.html')
out_cn = os.path.join(_BASE, '风格轧差看板.html')

if not os.path.exists(json_path):
    print("❌ style_spread.json 不存在，请先运行 compute_spreads.py")
    sys.exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

update_time = data["update_time"]
# formatted date: 20260227 → 2026-02-27
update_date = f"{update_time[:4]}-{update_time[4:6]}-{update_time[6:8]}" if len(update_time) == 8 else update_time

# --- 经济敏感 ---
eco = data["eco_sensitive"]
eco_d = json.dumps(eco["dates"])
eco_n = json.dumps(eco["navs"])
eco_s = json.dumps(eco["spreads"])
eco_final = eco["navs"][-1] if eco["navs"] else 1.0
eco_cls = "pos" if eco_final >= 1 else "neg"
eco_days = len(eco["dates"])

# --- 拥挤度 ---
cr = data["crowding"]
cr_d = json.dumps(cr["dates"])
cr_n = json.dumps(cr["navs"])
cr_s = json.dumps(cr["spreads"])
cr_final = cr["navs"][-1] if cr["navs"] else 1.0
cr_cls = "pos" if cr_final >= 1 else "neg"
cr_days = len(cr["dates"])
last_top = cr["top_names"][-1] if cr["top_names"] else ""
last_bot = cr["bot_names"][-1] if cr["bot_names"] else ""
if isinstance(last_top, list):
    last_top = ','.join(last_top)
if isinstance(last_bot, list):
    last_bot = ','.join(last_bot)
top_tags = ''.join(f'<span class="tag">{n}</span>' for n in last_top.split(',') if n)
bot_tags = ''.join(f'<span class="tag cool">{n}</span>' for n in last_bot.split(',') if n)

# --- 风格轧差 ---
style = data["style_spread"]["data"]
style_json = json.dumps(style, ensure_ascii=False)

# --- 双创等权 ---
di = data["dual_innovation"]
di_d = json.dumps(di["dates"])
di_n = json.dumps(di["navs"])

html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>风格轧差看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#f5f6f8;
  --card-bg:#fff;
  --text:#2d3142;
  --text-sub:#8b92a5;
  --border:#e8eaef;
  --accent:#2563eb;
}}
body{{font-family:-apple-system,'PingFang SC','Helvetica Neue','Microsoft YaHei',sans-serif;max-width:1100px;margin:0 auto;padding:20px;background:var(--bg);color:var(--text);font-size:14px}}

.ss-tabs{{display:flex;gap:6px;margin:0 0 16px;flex-wrap:wrap}}
.ss-tab{{padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;
  background:#fff;border:1px solid #e5e7eb;transition:all .12s;color:#6b7280}}
.ss-tab:hover{{color:#333;border-color:#cbd5e1}}
.ss-tab.active{{background:#6366f1;color:#fff;border-color:#6366f1}}

.ss-page{{display:none}}
.ss-page.active{{display:block}}

.card{{background:var(--card-bg);border-radius:10px;padding:18px;margin-bottom:16px;border:1px solid var(--border)}}
.card-title{{font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:7px;color:var(--text)}}
.card-title .dot{{width:7px;height:7px;border-radius:50%;display:inline-block}}

.overview-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:16px}}
.ov-card{{background:var(--card-bg);border-radius:10px;padding:14px 16px;border:1px solid var(--border);border-left:3px solid var(--accent)}}
.ov-card .ov-label{{font-size:11px;color:var(--text-sub)}}
.ov-card .ov-value{{font-size:20px;font-weight:700;margin:4px 0 2px;color:var(--text)}}
.ov-card .ov-sub{{font-size:10px;color:var(--text-sub)}}
.pos{{color:#e74c3c}} .neg{{color:#2ecc71}}

.tag-row{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}}
.tag{{background:#fff3e0;color:#e65100;padding:3px 10px;border-radius:12px;font-size:12px}}
.tag.cool{{background:#e3f2fd;color:#1565c0}}

@media(max-width:768px){{
  .ss-tabs{{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;gap:4px;padding-bottom:4px}}
  .ss-tab{{white-space:nowrap;flex-shrink:0;padding:6px 10px;font-size:11px}}
  .card{{padding:12px}}
}}
</style>
</head><body>

<div class="ss-tabs">
  <div class="ss-tab active" data-tab="eco">📊 经济敏感轧差</div>
  <div class="ss-tab" data-tab="crowd">🔥 拥挤-反身性</div>
  <div class="ss-tab" data-tab="style">📈 风格轧差净值</div>
  <div class="ss-tab" data-tab="dual">🚀 双创等权</div>
</div>

<!-- Tab 1: 经济敏感轧差 -->
<div class="ss-page active" id="page-eco">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888">📊 经济敏感轧差 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280">🔄 刷新当前</button>
  </div>
  <div class="overview-grid">
    <div class="ov-card" style="border-left-color:#e67e22">
      <div class="ov-label">轧差净值</div>
      <div class="ov-value {eco_cls}">{eco_final:.4f}</div>
      <div class="ov-sub">周期-防御多空净值</div>
    </div>
    <div class="ov-card" style="border-left-color:#e74c3c">
      <div class="ov-label">累计收益</div>
      <div class="ov-value {eco_cls}">{(eco_final-1)*100:+.2f}%</div>
      <div class="ov-sub">起始日归一化</div>
    </div>
    <div class="ov-card" style="border-left-color:var(--accent)">
      <div class="ov-label">观察天数</div>
      <div class="ov-value">{eco_days}</div>
      <div class="ov-sub">交易日</div>
    </div>
  </div>

  <div class="card">
    <div class="card-title"><span class="dot" style="background:#e67e22"></span> 周期-防御 净值</div>
    <div style="position:relative;height:280px"><canvas id="ecoNavChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#e74c3c"></span> 周期-防御 每日轧差%</div>
    <div style="position:relative;height:260px"><canvas id="ecoSpreadChart"></canvas></div>
  </div>
  <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 策略说明</div>
    <p><b>策略逻辑：</b>做多周期板块（有色金属+煤炭+钢铁），做空防御板块（食品饮料+医药生物），等权构建多空组合。净值上行表示经济复苏预期增强、周期跑赢防御；下行表示市场偏好防御。</p>
    <p><b>信号意义：</b>净值持续走高 → 经济景气上行周期；急涨后回落 → 周期股拥挤，注意风格切换。</p>
    <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare 申万行业指数 · 最后更新: {update_time}</p>
  </div>
</div>

<!-- Tab 2: 拥挤-反身性轧差 -->
<div class="ss-page" id="page-crowd">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888">🔥 拥挤-反身性 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280">🔄 刷新当前</button>
  </div>
  <div class="overview-grid">
    <div class="ov-card" style="border-left-color:#c0392b">
      <div class="ov-label">轧差净值</div>
      <div class="ov-value {cr_cls}">{cr_final:.4f}</div>
      <div class="ov-sub">高拥挤-低拥挤多空净值</div>
    </div>
    <div class="ov-card" style="border-left-color:#e74c3c">
      <div class="ov-label">累计收益</div>
      <div class="ov-value {cr_cls}">{(cr_final-1)*100:+.2f}%</div>
      <div class="ov-sub">起始日归一化</div>
    </div>
    <div class="ov-card" style="border-left-color:var(--accent)">
      <div class="ov-label">观察天数</div>
      <div class="ov-value">{cr_days}</div>
      <div class="ov-sub">交易日</div>
    </div>
  </div>

  <div class="card">
    <div class="card-title"><span class="dot" style="background:#e65100"></span> 最新拥挤度</div>
    <p style="font-size:12px;color:var(--text-sub);margin-bottom:8px">最新高拥挤 Top6：</p>
    <div class="tag-row">{top_tags}</div>
    <p style="font-size:12px;color:var(--text-sub);margin:8px 0">最新低拥挤 Bot6：</p>
    <div class="tag-row">{bot_tags}</div>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#c0392b"></span> 高拥挤-低拥挤 净值</div>
    <div style="position:relative;height:280px"><canvas id="crowdNavChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#2980b9"></span> 高拥挤-低拥挤 每日轧差%</div>
    <div style="position:relative;height:260px"><canvas id="crowdSpreadChart"></canvas></div>
  </div>
  <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 策略说明</div>
    <p><b>策略逻辑：</b>每20个交易日统计申万31个行业的拥挤度（涨幅排名），选出最拥挤的 Top6 做空、最冷门的 Bot6 做多，捕捉行业轮动中的反身性效应。</p>
    <p><b>信号意义：</b>净值上行 → 低拥挤反转有效，市场存在均值回归；净值下行 → 趋势延续性强，动量策略占优。</p>
    <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare 申万行业指数 · 最后更新: {update_time}</p>
  </div>
</div>

<!-- Tab 3: 风格轧差净值 -->
<div class="ss-page" id="page-style">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888">📈 风格轧差净值 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280">🔄 刷新当前</button>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#e74c3c"></span> 风格轧差多线对比</div>
    <div style="position:relative;height:280px"><canvas id="styleNavChart"></canvas></div>
  </div>
  <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 策略说明</div>
    <p><b>策略逻辑：</b>三组经典风格对冲的净值曲线，均从1开始归一化。</p>
    <p>🔴 <b>中证红利-科创50</b>：价值 vs 成长，净值下行 = 成长股跑赢。</p>
    <p>🔵 <b>微盘股-中证全指</b>：小盘超额，净值上行 = 微盘股跑赢大盘。</p>
    <p>🟢 <b>中证2000-沪深300</b>：大小盘轧差，净值上行 = 小盘跑赢大盘。</p>
    <p><b>信号意义：</b>三线同向上行 → 市场偏好小盘成长；三线同向下行 → 大盘价值占优。分化时关注风格切换拐点。</p>
    <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare 申万行业指数 · 最后更新: {update_time}</p>
  </div>
</div>

<!-- Tab 4: 双创等权 -->
<div class="ss-page" id="page-dual">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888">🚀 双创等权 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280">🔄 刷新当前</button>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#9b59b6"></span> 双创等权净值</div>
    <div style="position:relative;height:280px"><canvas id="dualChart"></canvas></div>
  </div>
  <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 策略说明</div>
    <p><b>策略逻辑：</b>创业板指 + 科创50 各50%等权配置，跟踪双创板块整体走势。</p>
    <p><b>信号意义：</b>净值趋势性上行 → 成长风格占优，科技板块资金流入；急跌后企稳 → 关注成长股反弹机会。可作为成长风格的β基准。</p>
    <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare 申万行业指数 · 最后更新: {update_time}</p>
  </div>
</div>

<script>
const eco_dates = {eco_d};
const eco_navs = {eco_n};
const eco_spreads = {eco_s};
const cr_dates = {cr_d};
const cr_navs = {cr_n};
const cr_spreads = {cr_s};
const style_data = {style_json};
const di_dates = {di_d};
const di_navs = {di_n};

// MA20 计算
function calcMA(arr, n) {{
  var r = [];
  for (var i = 0; i < arr.length; i++) {{
    if (i < n - 1) {{ r.push(null); }}
    else {{ var s = 0; for (var j = i - n + 1; j <= i; j++) s += arr[j]; r.push(s / n); }}
  }}
  return r;
}}

var chartBase = {{
  responsive:true,maintainAspectRatio:false,
  interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}}}},
  scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}}}}}}
}};
function lineOpts() {{ return JSON.parse(JSON.stringify(chartBase)); }}
function barOpts() {{ var o = JSON.parse(JSON.stringify(chartBase)); o.plugins.legend.display = false; return o; }}

var inited = {{}};
function initTab(tab) {{
  if (inited[tab]) return;
  inited[tab] = true;

  switch(tab) {{
    case 'eco':
      new Chart(document.getElementById('ecoNavChart'),{{type:'line',data:{{labels:eco_dates,datasets:[
        {{label:'净值',data:eco_navs,borderColor:'#e67e22',backgroundColor:'rgba(230,126,34,0.08)',fill:true,tension:0.3,pointRadius:1.5,pointBackgroundColor:'#e67e22',borderWidth:2}},
        {{label:'MA20',data:calcMA(eco_navs,20),borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:0.3}}
      ]}},options:lineOpts()}});
      new Chart(document.getElementById('ecoSpreadChart'),{{type:'bar',data:{{labels:eco_dates,datasets:[{{
        data:eco_spreads,backgroundColor:eco_spreads.map(function(v){{return v>=0?'rgba(231,76,60,0.6)':'rgba(52,152,219,0.6)'}}),borderRadius:2
      }}]}},options:barOpts()}});
      break;

    case 'crowd':
      new Chart(document.getElementById('crowdNavChart'),{{type:'line',data:{{labels:cr_dates,datasets:[
        {{label:'净值',data:cr_navs,borderColor:'#c0392b',backgroundColor:'rgba(192,57,43,0.08)',fill:true,tension:0.3,pointRadius:1.5,pointBackgroundColor:'#c0392b',borderWidth:2}},
        {{label:'MA20',data:calcMA(cr_navs,20),borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:0.3}}
      ]}},options:lineOpts()}});
      new Chart(document.getElementById('crowdSpreadChart'),{{type:'bar',data:{{labels:cr_dates,datasets:[{{
        data:cr_spreads,backgroundColor:cr_spreads.map(function(v){{return v>=0?'rgba(192,57,43,0.6)':'rgba(41,128,185,0.6)'}}),borderRadius:2
      }}]}},options:barOpts()}});
      break;

    case 'style':
      var colors = ['#e74c3c','#3498db','#2ecc71'];
      var styleDs = [];
      var ci = 0;
      for (var label in style_data) {{
        styleDs.push({{label:label,data:style_data[label].navs,borderColor:colors[ci%3],backgroundColor:'transparent',tension:0.3,pointRadius:1,borderWidth:2}});
        ci++;
      }}
      var firstKey = Object.keys(style_data)[0];
      var sOpts = lineOpts();
      sOpts.plugins.legend.display = true;
      new Chart(document.getElementById('styleNavChart'),{{type:'line',data:{{labels:style_data[firstKey].dates,datasets:styleDs}},options:sOpts}});
      break;

    case 'dual':
      new Chart(document.getElementById('dualChart'),{{type:'line',data:{{labels:di_dates,datasets:[
        {{label:'净值',data:di_navs,borderColor:'#9b59b6',backgroundColor:'rgba(155,89,182,0.08)',fill:true,tension:0.3,pointRadius:1.5,pointBackgroundColor:'#9b59b6',borderWidth:2}},
        {{label:'MA20',data:calcMA(di_navs,20),borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:0.3}}
      ]}},options:lineOpts()}});
      break;
  }}
}}

document.querySelectorAll('.ss-tab').forEach(function(tab) {{
  tab.addEventListener('click', function() {{
    var target = this.getAttribute('data-tab');
    document.querySelectorAll('.ss-tab').forEach(function(t){{ t.classList.remove('active'); }});
    document.querySelectorAll('.ss-page').forEach(function(p){{ p.classList.remove('active'); }});
    this.classList.add('active');
    document.getElementById('page-' + target).classList.add('active');
    initTab(target);
  }});
}});

initTab('eco');

function refreshData(module) {{
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '刷新中...';
  
  fetch('/api/refresh/' + module, {{
    method: 'POST',
    credentials: 'include'
  }})
  .then(res => res.json())
  .then(data => {{
    if(data.ok) {{
      pollProgress(btn);
    }} else {{
      alert('刷新失败: ' + (data.error || '未知错误'));
      btn.disabled = false;
      btn.textContent = '🔄 刷新当前';
    }}
  }})
  .catch(err => {{
    alert('刷新失败: ' + err.message);
    btn.disabled = false;
    btn.textContent = '🔄 刷新当前';
  }});
}}

function pollProgress(btn) {{
  fetch('/api/status', {{credentials: 'include'}})
  .then(res => res.json())
  .then(data => {{
    if(data.running) {{
      const prog = data.progress || {{}};
      const script = prog.current_script || '';
      const done = prog.completed_scripts || 0;
      const total = prog.total_scripts || 0;
      btn.textContent = `${{script}} (${{done}}/${{total}})`;
      setTimeout(() => pollProgress(btn), 800);
    }} else {{
      const result = data.last_result || {{}};
      if(result.ok) {{
        btn.textContent = '✅ 完成';
        setTimeout(() => location.reload(), 1000);
      }} else {{
        btn.textContent = '❌ 失败';
        setTimeout(() => {{
          btn.disabled = false;
          btn.textContent = '🔄 刷新当前';
        }}, 2000);
      }}
    }}
  }})
  .catch(() => {{
    btn.disabled = false;
    btn.textContent = '🔄 刷新当前';
  }});
}}
</script>
</body></html>'''

for path in [out_en, out_cn]:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

size = os.path.getsize(out_en)
print(f"✅ HTML 生成完成: {size/1024:.1f} KB")
print(f"   {out_en}")
print(f"   {out_cn}")
