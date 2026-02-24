#!/usr/bin/env python3
"""从 style_spread.json 生成静态 HTML 看板"""
import json, sys, os

json_path = os.path.expanduser('~/Desktop/gamt-dashboard/data/style_spread.json')
out_en = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/style_spread.html')
out_cn = os.path.expanduser('~/Desktop/gamt-dashboard/size_spread/风格轧差看板.html')

if not os.path.exists(json_path):
    print("❌ style_spread.json 不存在，请先运行 compute_spreads.py")
    sys.exit(1)

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

update_time = data["update_time"]

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
# top/bot names: 最新一天的，可能是列表或逗号分隔字符串
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
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{{font-family:'PingFang SC',sans-serif;max-width:1100px;margin:30px auto;padding:0 20px;background:#fafafa}}
h2{{text-align:center;color:#333;margin-bottom:5px}}
p.sub{{text-align:center;color:#888;font-size:13px;margin-top:0}}
.cards{{display:flex;justify-content:center;gap:20px;margin:15px 0;flex-wrap:wrap}}
.card{{background:#fff;padding:12px 18px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);min-width:140px;text-align:center}}
.card .label{{color:#888;font-size:11px}}
.card .value{{font-size:18px;font-weight:bold;margin-top:3px}}
.card .detail{{font-size:11px;color:#999;margin-top:2px}}
.pos{{color:#e74c3c}} .neg{{color:#2ecc71}}
.section{{margin-top:35px}}
.section h3{{color:#555;font-size:15px;border-bottom:1px solid #eee;padding-bottom:5px}}
.row{{display:flex;gap:15px;margin-top:10px}}
.row canvas{{flex:1;background:#fff;border-radius:8px;padding:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
.tag-row{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}}
.tag{{background:#fff3e0;color:#e65100;padding:3px 10px;border-radius:12px;font-size:12px}}
.tag.cool{{background:#e3f2fd;color:#1565c0}}
</style>
</head><body>

<h2>风格轧差看板</h2>
<p class="sub">数据来源: Tushare 申万行业指数 | 最后更新: {update_time}</p>

<!-- 经济敏感轧差 -->
<div class="section">
<h3>📊 经济敏感轧差（有色+煤炭+钢铁 vs 食品饮料+医药）</h3>
<div class="cards">
  <div class="card"><div class="label">轧差净值</div><div class="value {eco_cls}">{eco_final:.4f}</div></div>
  <div class="card"><div class="label">累计收益</div><div class="value {eco_cls}">{(eco_final-1)*100:+.2f}%</div></div>
  <div class="card"><div class="label">观察天数</div><div class="value">{eco_days}</div></div>
</div>
<div class="row">
  <canvas id="ecoNavChart" height="120"></canvas>
  <canvas id="ecoSpreadChart" height="120"></canvas>
</div>
</div>

<!-- 拥挤-反身性轧差 -->
<div class="section">
<h3>🔥 拥挤-反身性轧差（高拥挤Top6 vs 低拥挤Bot6，20日滚动）</h3>
<div class="cards">
  <div class="card"><div class="label">轧差净值</div><div class="value {cr_cls}">{cr_final:.4f}</div></div>
  <div class="card"><div class="label">累计收益</div><div class="value {cr_cls}">{(cr_final-1)*100:+.2f}%</div></div>
  <div class="card"><div class="label">观察天数</div><div class="value">{cr_days}</div></div>
</div>
<p style="font-size:12px;color:#666;margin:5px 0 0 0">最新高拥挤 Top6：</p>
<div class="tag-row">{top_tags}</div>
<p style="font-size:12px;color:#666;margin:5px 0 0 0">最新低拥挤 Bot6：</p>
<div class="tag-row">{bot_tags}</div>
<div class="row">
  <canvas id="crowdNavChart" height="120"></canvas>
  <canvas id="crowdSpreadChart" height="120"></canvas>
</div>
</div>

<!-- 风格轧差净值 -->
<div class="section">
<h3>📈 风格轧差净值（归1）</h3>
<div class="row">
  <canvas id="styleNavChart" height="140"></canvas>
</div>
</div>

<!-- 双创等权 -->
<div class="section">
<h3>🚀 双创等权净值（创业板指+科创50 等权）</h3>
<div class="row">
  <canvas id="dualChart" height="120"></canvas>
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

const lineOpts = (title) => ({{
  plugins:{{title:{{display:true,text:title,font:{{size:13}}}},legend:{{display:false}}}},
  scales:{{x:{{ticks:{{maxTicksLimit:10}}}},y:{{title:{{display:true,text:'净值'}}}}}}
}});
const barOpts = (title) => ({{
  plugins:{{title:{{display:true,text:title,font:{{size:13}}}},legend:{{display:false}}}},
  scales:{{x:{{ticks:{{maxTicksLimit:10}}}},y:{{title:{{display:true,text:'%'}}}}}}
}});

// 经济敏感
new Chart(document.getElementById('ecoNavChart'),{{type:'line',data:{{labels:eco_dates,datasets:[{{
  data:eco_navs,borderColor:'#e67e22',backgroundColor:'rgba(230,126,34,0.08)',fill:true,tension:0.3,pointRadius:1,borderWidth:2
}}]}},options:lineOpts('周期-防御 净值')}});

new Chart(document.getElementById('ecoSpreadChart'),{{type:'bar',data:{{labels:eco_dates,datasets:[{{
  data:eco_spreads,backgroundColor:eco_spreads.map(v=>v>=0?'rgba(231,76,60,0.6)':'rgba(52,152,219,0.6)'),borderRadius:2
}}]}},options:barOpts('周期-防御 每日轧差%')}});

// 拥挤度
new Chart(document.getElementById('crowdNavChart'),{{type:'line',data:{{labels:cr_dates,datasets:[{{
  data:cr_navs,borderColor:'#c0392b',backgroundColor:'rgba(192,57,43,0.08)',fill:true,tension:0.3,pointRadius:1,borderWidth:2
}}]}},options:lineOpts('高拥挤-低拥挤 净值')}});

new Chart(document.getElementById('crowdSpreadChart'),{{type:'bar',data:{{labels:cr_dates,datasets:[{{
  data:cr_spreads,backgroundColor:cr_spreads.map(v=>v>=0?'rgba(192,57,43,0.6)':'rgba(41,128,185,0.6)'),borderRadius:2
}}]}},options:barOpts('高拥挤-低拥挤 每日轧差%')}});

// 风格轧差（多线）
const colors = ['#e74c3c','#3498db','#2ecc71'];
const styleDs = [];
let ci = 0;
for (const label in style_data) {{
  styleDs.push({{label:label,data:style_data[label].navs,borderColor:colors[ci%3],backgroundColor:'transparent',tension:0.3,pointRadius:1,borderWidth:2}});
  ci++;
}}
const firstKey = Object.keys(style_data)[0];
new Chart(document.getElementById('styleNavChart'),{{type:'line',data:{{labels:style_data[firstKey].dates,datasets:styleDs}},options:{{
  plugins:{{title:{{display:false}},legend:{{display:true,position:'top'}}}},
  scales:{{x:{{ticks:{{maxTicksLimit:10}}}},y:{{title:{{display:true,text:'净值'}}}}}}
}}}});

// 双创等权
new Chart(document.getElementById('dualChart'),{{type:'line',data:{{labels:di_dates,datasets:[{{
  data:di_navs,borderColor:'#9b59b6',backgroundColor:'rgba(155,89,182,0.08)',fill:true,tension:0.3,pointRadius:1,borderWidth:2
}}]}},options:lineOpts('双创等权净值')}});
</script>
</body></html>'''

for path in [out_en, out_cn]:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

size = os.path.getsize(out_en)
print(f"✅ HTML 生成完成: {size/1024:.1f} KB")
print(f"   {out_en}")
print(f"   {out_cn}")
