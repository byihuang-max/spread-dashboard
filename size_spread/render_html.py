#!/usr/bin/env python3
"""从 style_spread.json 生成静态 HTML 看板（v2 card格式 + MA20）"""
import json, sys, os

_BASE = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(_BASE, 'data', 'style_spread.json')
out_en = os.path.join(_BASE, 'style_spread.html')
out_cn = os.path.join(_BASE, '风格轧差看板.html')

if not os.path.exists(json_path):
    print(" style_spread.json 不存在，请先运行 compute_spreads.py")
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

# --- 双创 vs 杠铃 ---
di = data["dual_innovation"]
di_d = json.dumps(di["dates"])
di_n = json.dumps(di["navs"])
# 杠铃数据（如果有）
if "barbell" in di:
    bb = di["barbell"]
    bb_d = json.dumps(bb["dates"])
    bb_n = json.dumps(bb["navs"])
    bb_dual_n = json.dumps(bb["dual_navs"])
else:
    bb_d = "[]"
    bb_n = "[]"
    bb_dual_n = "[]"

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

.barra-time-btn{{padding:4px 10px;border-radius:4px;font-size:11px;font-weight:500;cursor:pointer;
  background:#f8fafc;border:1px solid #e5e7eb;color:#6b7280;transition:all .12s}}
.barra-time-btn:hover{{color:#333;border-color:#cbd5e1}}
.barra-time-btn.barra-time-active{{background:#6366f1;color:#fff;border-color:#6366f1}}

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
  <div class="ss-tab active" data-tab="barra"> Barra风格因子</div>
  <div class="ss-tab" data-tab="eco"> 经济敏感轧差</div>
  <div class="ss-tab" data-tab="crowd"> 拥挤-反身性</div>
  <div class="ss-tab" data-tab="style"> 风格轧差净值</div>
  <div class="ss-tab" data-tab="dual"> 双创 vs 杠铃</div>
</div>

<!-- Tab 0: Barra 风格因子 -->
<div class="ss-page active" id="page-barra">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888" id="barra-header"> Barra CNE6 风格因子</span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280"> 刷新当前</button>
  </div>
  <div class="overview-grid" id="barra-cards"></div>
  <div class="card" id="barra-time-controls" style="padding:12px 16px"></div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#6366f1"></span> 风格因子累计净值（区间归一化）</div>
    <div style="position:relative;height:360px"><canvas id="barraNavChart"></canvas></div>
  </div>
  <div class="card" id="barra-checkbox-card">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#6366f1"></span> 因子选择（勾选叠加到图上）</div>
    <div id="barra-checkboxes" style="display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px"></div>
  </div>
  <div class="card" id="barra-status-panel">
    <div class="card-title"><span class="dot" style="background:#f59e0b"></span> 风格状态面板（多时间窗口）</div>
  </div>
</div>

<!-- Tab 1: 经济敏感轧差 -->
<div class="ss-page" id="page-eco">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888"> 经济敏感轧差 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280"> 刷新当前</button>
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
    <span style="font-size:13px;color:#888"> 拥挤-反身性 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280"> 刷新当前</button>
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
    <span style="font-size:13px;color:#888"> 风格轧差净值 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280"> 刷新当前</button>
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

<!-- Tab 4: 双创 vs 杠铃 -->
<div class="ss-page" id="page-dual">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
    <span style="font-size:13px;color:#888"> 双创 vs 杠铃 · 数据截至 <b style="color:#2d3142">{update_date}</b></span>
    <button onclick="refreshData('style_spread')" style="padding:6px 12px;border-radius:6px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-size:12px;color:#6b7280"> 刷新当前</button>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot" style="background:#9b59b6"></span> 双创等权 vs 杠铃组合（归1净值）</div>
    <div style="position:relative;height:320px"><canvas id="dualChart"></canvas></div>
  </div>
  <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
    <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 策略说明</div>
    <p><b>双创等权：</b>创业板指(399006) + 科创50(000688) 各50%等权，代表成长/科技风格。</p>
    <p><b>杠铃组合：</b>中证红利(000922) + 同花顺微盘股(884143.TI) 各50%等权，代表"高股息+微盘"的防御+弹性组合。</p>
    <p><b>背对逻辑：</b>两条线呈现跷跷板效应。双创强势期（成交量>3万亿、科技虹吸）杠铃跑输；流动性退潮期（成交量<2.5万亿）杠铃回归。2025年以来轮动周期约1.5-3个月。</p>
    <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare（双创/红利） + iFinD（同花顺微盘股指数） · 最后更新: {update_time}</p>
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
const bb_dates = {bb_d};
const bb_navs = {bb_n};
const bb_dual_navs = {bb_dual_n};

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
  scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}}}}
}};
function lineOpts() {{ return JSON.parse(JSON.stringify(chartBase)); }}
function barOpts() {{ var o = JSON.parse(JSON.stringify(chartBase)); o.plugins.legend.display = false; return o; }}

// === Barra 风格因子动态加载 ===
var barraChart = null;
var barraData = null;
var barraTimeRange = [0, 0];
var barraColors = {{
  DIVYILD:'#e05555',RESVOL:'#3b82f6',MOMENTUM:'#10b981',BTOP:'#f59e0b',
  PROFIT:'#8b5cf6',LTREVRSL:'#14b8a6',STREVRSL:'#ec4899',EARNYILD:'#f97316',
  EARNQLTY:'#06b6d4',INVSQLTY:'#84cc16',SIZE:'#78716c',GROWTH:'#6366f1',
  BETA:'#ef4444',LIQUIDTY:'#64748b',MIDCAP:'#a3a328',LEVERAGE:'#9ca3af',
  EARNVAR:'#0891b2',ANALSENTI:'#db2777',INDMOM:'#16a34a',SEASON:'#ca8a04'
}};
var barraDefaultFactors = ['DIVYILD','RESVOL','MOMENTUM','BTOP','PROFIT','LTREVRSL'];

function loadBarraData() {{
  if (barraData) {{ renderBarraChart(); return; }}
  fetch('/size_spread/data/barra_style_nav.json?t=' + Date.now())
    .then(function(r){{ return r.json(); }})
    .then(function(data){{
      barraData = data;
      barraTimeRange = [0, data.all_dates.length - 1];
      document.getElementById('barra-header').innerHTML =
        ' Barra CNE6 风格因子 \\u00b7 数据截至 <b style="color:#2d3142">' + data.update_date + '</b> \\u00b7 ' + data.total_days + '个交易日';
      renderBarraCards();
      renderBarraTimeControls();
      renderBarraCheckboxes();
      renderBarraStatusPanel();
      renderBarraChart();
    }})
    .catch(function(e){{ document.getElementById('barra-header').textContent = '加载失败: ' + e.message; }});
}}

function renderBarraCards() {{
  var core = ['DIVYILD','RESVOL','MOMENTUM','BTOP','PROFIT','LTREVRSL'];
  var html = '';
  core.forEach(function(code){{
    var nav = barraData.all_navs[code][barraData.all_navs[code].length-1];
    var r20 = barraData.recent_20[code];
    var dir = r20 >= 0 ? '\\u25b2' : '\\u25bc';
    var cls = r20 >= 0 ? 'pos' : 'neg';
    html += '<div class="ov-card" style="border-left-color:'+barraColors[code]+'">' +
      '<div class="ov-label">'+barraData.names[code]+'</div>' +
      '<div class="ov-value '+cls+'">'+nav.toFixed(4)+'</div>' +
      '<div class="ov-sub">近20日 '+dir+Math.abs(r20).toFixed(2)+'%</div></div>';
  }});
  document.getElementById('barra-cards').innerHTML = html;
}}

function renderBarraTimeControls() {{
  var container = document.getElementById('barra-time-controls');
  if (!container) return;
  var total = barraData.all_dates.length;
  var html = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">';
  html += '<span style="font-size:11px;color:#64748b;font-weight:600">时间范围:</span>';
  var presets = [
    {{label:'近1月',days:20}},{{label:'近3月',days:60}},{{label:'近半年',days:120}},
    {{label:'近1年',days:250}},{{label:'近2年',days:500}},{{label:'全部',days:0}}
  ];
  presets.forEach(function(p){{
    var active = (p.days === 0) ? ' barra-time-active' : '';
    html += '<button class="barra-time-btn'+active+'" onclick="setBarraTimePreset('+p.days+',this)">'+p.label+'</button>';
  }});
  html += '</div>';
  html += '<div style="display:flex;align-items:center;gap:10px;margin-top:8px">';
  html += '<span style="font-size:11px;color:#94a3b8" id="barra-range-start">'+barraData.all_dates[0]+'</span>';
  html += '<input type="range" id="barra-slider" min="0" max="'+(total-1)+'" value="0" ' +
    'style="flex:1;height:4px;accent-color:#6366f1;cursor:pointer" oninput="onBarraSlider(this.value)">';
  html += '<span style="font-size:11px;color:#94a3b8" id="barra-range-end">'+barraData.all_dates[total-1]+'</span>';
  html += '</div>';
  container.innerHTML = html;
}}

function setBarraTimePreset(days, btn) {{
  var total = barraData.all_dates.length;
  if (days === 0) {{ barraTimeRange = [0, total - 1]; }}
  else {{ barraTimeRange = [Math.max(0, total - days), total - 1]; }}
  document.getElementById('barra-slider').value = barraTimeRange[0];
  document.getElementById('barra-range-start').textContent = barraData.all_dates[barraTimeRange[0]];
  document.querySelectorAll('.barra-time-btn').forEach(function(b){{ b.classList.remove('barra-time-active'); }});
  if (btn) btn.classList.add('barra-time-active');
  renderBarraChart();
}}

function onBarraSlider(val) {{
  var startIdx = parseInt(val);
  barraTimeRange[0] = startIdx;
  document.getElementById('barra-range-start').textContent = barraData.all_dates[startIdx];
  document.querySelectorAll('.barra-time-btn').forEach(function(b){{ b.classList.remove('barra-time-active'); }});
  renderBarraChart();
}}

function renderBarraCheckboxes() {{
  var container = document.getElementById('barra-checkboxes');
  var html = '';
  var groups = barraData.groups;
  for (var gname in groups) {{
    html += '<div style="margin-bottom:4px;width:100%"><span style="font-size:11px;color:#94a3b8">'+gname+'</span></div>';
    groups[gname].forEach(function(code){{
      var checked = barraDefaultFactors.indexOf(code) >= 0 ? ' checked' : '';
      html += '<label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;min-width:110px;padding:2px 0;color:#4b5563;font-size:12px">' +
        '<input type="checkbox" class="barra-cb" value="'+code+'"'+checked+' onchange="renderBarraChart()" style="accent-color:'+barraColors[code]+'">' +
        '<span style="width:8px;height:8px;border-radius:2px;background:'+barraColors[code]+';display:inline-block"></span> ' +
        barraData.names[code] + '</label>';
    }});
  }}
  container.innerHTML = html;
}}

function renderBarraStatusPanel() {{
  var container = document.getElementById('barra-status-panel');
  if (!container) return;
  var windows = [
    {{key:'recent_5',label:'5日'}},{{key:'recent_20',label:'20日'}},
    {{key:'recent_60',label:'近1月'}},{{key:'recent_120',label:'近半年'}},
    {{key:'recent_250',label:'近1年'}}
  ];
  var groups = barraData.groups;
  var html = '<div class="card-title"><span class="dot" style="background:#f59e0b"></span> 风格状态面板（多时间窗口）</div>';
  html += '<div style="margin-bottom:14px;display:flex;gap:20px;flex-wrap:wrap">';
  var sorted20 = Object.keys(barraData.recent_20).sort(function(a,b){{ return barraData.recent_20[b]-barraData.recent_20[a]; }});
  var winners = sorted20.filter(function(c){{ return barraData.recent_20[c] > 0; }});
  var losers = sorted20.filter(function(c){{ return barraData.recent_20[c] < 0; }}).reverse();
  html += '<div style="flex:1;min-width:200px"><div style="font-size:11px;font-weight:600;color:#e05555;margin-bottom:4px">\\u25b2 近20日赚钱风格</div>';
  winners.slice(0,6).forEach(function(c){{
    html += '<div style="font-size:11px;color:#4b5563;padding:1px 0"><span style="color:'+barraColors[c]+'">\\u25cf</span> '+barraData.names[c]+' <span style="color:#e05555;font-weight:500">+'+barraData.recent_20[c].toFixed(2)+'%</span></div>';
  }});
  html += '</div>';
  html += '<div style="flex:1;min-width:200px"><div style="font-size:11px;font-weight:600;color:#2ecc71;margin-bottom:4px">\\u25bc 近20日亏钱风格</div>';
  losers.slice(0,6).forEach(function(c){{
    html += '<div style="font-size:11px;color:#4b5563;padding:1px 0"><span style="color:'+barraColors[c]+'">\\u25cf</span> '+barraData.names[c]+' <span style="color:#2ecc71;font-weight:500">'+barraData.recent_20[c].toFixed(2)+'%</span></div>';
  }});
  html += '</div></div>';
  for (var gname in groups) {{
    html += '<div style="margin-bottom:12px">';
    html += '<div style="font-size:11px;font-weight:600;color:#2d3142;margin-bottom:4px;border-bottom:1px solid #f1f5f9;padding-bottom:3px">'+gname+'</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr><th style="text-align:left;padding:3px 4px;color:#94a3b8;font-weight:500">因子</th>';
    windows.forEach(function(w){{ html += '<th style="text-align:right;padding:3px 4px;color:#94a3b8;font-weight:500">'+w.label+'</th>'; }});
    html += '<th style="text-align:left;padding:3px 4px;color:#94a3b8;font-weight:500;min-width:160px">状态含义</th></tr></thead><tbody>';
    groups[gname].forEach(function(code){{
      html += '<tr style="border-bottom:1px solid #f8fafc"><td style="padding:3px 4px;color:#4b5563;font-weight:500"><span style="color:'+barraColors[code]+'">\\u25cf</span> '+barraData.names[code]+'</td>';
      windows.forEach(function(w){{
        var val = barraData[w.key] ? barraData[w.key][code] : 0;
        var cls = val >= 0 ? 'color:#e05555' : 'color:#2ecc71';
        var arrow = val >= 0 ? '\\u25b2' : '\\u25bc';
        html += '<td style="text-align:right;padding:3px 4px;'+cls+';font-weight:500">'+arrow+Math.abs(val).toFixed(2)+'%</td>';
      }});
      var meaning = (barraData.meanings && barraData.meanings[code]) || '';
      var r20 = barraData.recent_20[code] || 0;
      if (r20 < 0) {{ meaning = meaning.replace(/跑赢/g,'跑输').replace(/有效/g,'失效').replace(/占优/g,'承压').replace(/上升/g,'下降').replace(/延续/g,'衰减'); }}
      html += '<td style="padding:3px 4px;color:#94a3b8;font-size:10px">'+meaning+'</td></tr>';
    }});
    html += '</tbody></table></div>';
  }}
  container.innerHTML = html;
}}

function renderBarraChart() {{
  var selected = [];
  document.querySelectorAll('.barra-cb:checked').forEach(function(cb){{ selected.push(cb.value); }});
  if (selected.length === 0) selected = barraDefaultFactors;
  var startIdx = barraTimeRange[0];
  var endIdx = barraTimeRange[1];
  var totalPts = endIdx - startIdx + 1;
  var step = totalPts > 300 ? Math.floor(totalPts / 250) : 1;
  var sampledIndices = [];
  for (var i = 0; i < totalPts; i += step) sampledIndices.push(i);
  if (sampledIndices[sampledIndices.length-1] !== totalPts-1) sampledIndices.push(totalPts-1);
  var dates = barraData.all_dates.slice(startIdx, endIdx + 1);
  var sampledDates = sampledIndices.map(function(i){{ return dates[i]; }});
  var datasets = selected.map(function(code){{
    var fullNav = barraData.all_navs[code];
    var baseNav = fullNav[startIdx];
    var sliced = sampledIndices.map(function(i){{ return fullNav[startIdx + i] / baseNav; }});
    return {{
      label: barraData.names[code],
      data: sliced,
      borderColor: barraColors[code],
      backgroundColor: 'transparent',
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2
    }};
  }});
  if (barraChart) {{ barraChart.destroy(); }}
  var opts = lineOpts();
  opts.plugins.legend.display = true;
  opts.plugins.legend.labels = {{boxWidth:10,font:{{size:10}},padding:8}};
  opts.scales.y.ticks.callback = function(v){{return v.toFixed(2)}};
  barraChart = new Chart(document.getElementById('barraNavChart'), {{
    type: 'line',
    data: {{ labels: sampledDates, datasets: datasets }},
    options: opts
  }});
}}

var inited = {{}};
function initTab(tab) {{
  if (inited[tab]) return;
  inited[tab] = true;

  switch(tab) {{
    case 'barra':
      loadBarraData();
      break;
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
      var dualDates = bb_dates.length > 0 ? bb_dates : di_dates;
      var dualNavs = bb_dual_navs.length > 0 ? bb_dual_navs : di_navs;
      var dOpts = lineOpts();
      dOpts.plugins.legend.display = true;
      var dualDs = [
        {{label:'双创等权',data:dualNavs,borderColor:'#9b59b6',backgroundColor:'rgba(155,89,182,0.06)',fill:true,tension:0.3,pointRadius:0,borderWidth:2.5}}
      ];
      if (bb_navs.length > 0) {{
        dualDs.push({{label:'杠铃组合(红利+微盘)',data:bb_navs,borderColor:'#e67e22',backgroundColor:'rgba(230,126,34,0.06)',fill:true,tension:0.3,pointRadius:0,borderWidth:2.5}});
      }}
      new Chart(document.getElementById('dualChart'),{{type:'line',data:{{labels:dualDates,datasets:dualDs}},options:dOpts}});
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

initTab('barra');

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
      btn.textContent = ' 刷新当前';
    }}
  }})
  .catch(err => {{
    alert('刷新失败: ' + err.message);
    btn.disabled = false;
    btn.textContent = ' 刷新当前';
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
        btn.textContent = ' 完成';
        setTimeout(() => location.reload(), 1000);
      }} else {{
        btn.textContent = ' 失败';
        setTimeout(() => {{
          btn.disabled = false;
          btn.textContent = ' 刷新当前';
        }}, 2000);
      }}
    }}
  }})
  .catch(() => {{
    btn.disabled = false;
    btn.textContent = ' 刷新当前';
  }});
}}
</script>
</body></html>'''

for path in [out_en, out_cn]:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

size = os.path.getsize(out_en)
print(f" HTML 生成完成: {size/1024:.1f} KB")
print(f"   {out_en}")
print(f"   {out_cn}")
