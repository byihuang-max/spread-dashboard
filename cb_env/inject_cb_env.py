#!/usr/bin/env python3
"""
转债指增策略环境 — 注入脚本
读取 cb_env.json，生成 HTML/JS 注入到 index.html 的转债 tab
"""

import json, os, re

BASE_DIR = '/Users/apple/Desktop/gamt-dashboard/cb_env'
ENV_JSON = os.path.join(BASE_DIR, 'cb_env.json')
INDEX_HTML = '/Users/apple/Desktop/gamt-dashboard/index.html'

def log(msg):
    print(msg, flush=True)

def load_env():
    with open(ENV_JSON) as f:
        return json.load(f)

def fmt(v, suffix='', digits=1):
    if v is None:
        return '--'
    if isinstance(v, float):
        return f"{v:.{digits}f}{suffix}"
    return f"{v}{suffix}"

def score_color(score):
    if score >= 70: return '#22c55e'  # green
    if score >= 40: return '#f59e0b'  # amber
    return '#ef4444'  # red

def build_html(env):
    score = env["score"]
    details = env["score_details"]
    mod1 = env["mod1_activity"]
    mod2 = env["mod2_valuation"]
    mod3 = env["mod3_delta"]
    mod4 = env["mod4_floor"]
    last_date = env["meta"]["last_date"]
    last_date_fmt = f"{last_date[:4]}-{last_date[4:6]}-{last_date[6:]}"

    # 子分数
    detail_map = dict(details)

    # 日期格式化
    dates_raw = env["meta"]["dates"]
    dates_js = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates_raw]

    html = f'''
<!-- 转债指增策略环境 — 自动注入 -->
<div style="padding:0 4px">

<!-- 总览卡片 -->
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px">
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">转债友好度</div>
    <div style="font-size:28px;font-weight:700;color:{score_color(score)};margin:4px 0">{fmt(score, '', 1)}</div>
    <div style="font-size:10px;color:var(--text-sub)">0-100 综合评分</div>
  </div>
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">活跃转债</div>
    <div style="font-size:28px;font-weight:700;color:var(--text);margin:4px 0">{mod1['latest']['cb_active_count']}</div>
    <div style="font-size:10px;color:var(--text-sub)">只（有成交）</div>
  </div>
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">成交额</div>
    <div style="font-size:28px;font-weight:700;color:var(--text);margin:4px 0">{fmt(mod1['latest']['cb_amount'], '', 0)}</div>
    <div style="font-size:10px;color:var(--text-sub)">亿元</div>
  </div>
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">DELTA中位数</div>
    <div style="font-size:28px;font-weight:700;color:var(--text);margin:4px 0">{fmt(mod3['latest']['delta_median'], '', 2)}</div>
    <div style="font-size:10px;color:var(--text-sub)">股性指标(0~1)</div>
  </div>
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">均价分位</div>
    <div style="font-size:28px;font-weight:700;color:{"#ef4444" if (mod2['latest']['price_percentile'] or 0) > 70 else "#22c55e"};margin:4px 0">{fmt(mod2['latest']['price_percentile'], '%', 0)}</div>
    <div style="font-size:10px;color:var(--text-sub)">越低越便宜</div>
  </div>
  <div class="card" style="text-align:center;padding:14px 8px">
    <div style="font-size:11px;color:var(--text-sub)">数据日期</div>
    <div style="font-size:16px;font-weight:600;color:var(--text);margin:8px 0">{last_date_fmt}</div>
    <div style="font-size:10px;color:var(--text-sub)">{env['meta']['n_dates']}个交易日</div>
  </div>
</div>

<!-- 子分数卡片 -->
<div class="card" style="padding:14px;margin-bottom:16px">
  <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:10px">📊 分项评分</div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--text-sub)">活跃度</div>
      <div style="font-size:20px;font-weight:700;color:{score_color(detail_map.get('活跃度',50))}">{fmt(detail_map.get('活跃度'), '', 0)}</div>
      <div style="font-size:9px;color:var(--text-sub)">成交额×小盘相关</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--text-sub)">估值</div>
      <div style="font-size:20px;font-weight:700;color:{score_color(detail_map.get('估值',50))}">{fmt(detail_map.get('估值'), '', 0)}</div>
      <div style="font-size:9px;color:var(--text-sub)">价格分位+溢价率</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--text-sub)">DELTA</div>
      <div style="font-size:20px;font-weight:700;color:{score_color(detail_map.get('DELTA',50))}">{fmt(detail_map.get('DELTA'), '', 0)}</div>
      <div style="font-size:9px;color:var(--text-sub)">转债vs正股联动</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--text-sub)">债底</div>
      <div style="font-size:20px;font-weight:700;color:{score_color(detail_map.get('债底',50))}">{fmt(detail_map.get('债底'), '', 0)}</div>
      <div style="font-size:9px;color:var(--text-sub)">破面值占比</div>
    </div>
  </div>
</div>

<!-- 图表区域 -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
  <div class="card" style="padding:14px">
    <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">转债成交额 & 小盘相关性</div>
    <canvas id="cb-chart-activity" height="200"></canvas>
  </div>
  <div class="card" style="padding:14px">
    <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">活跃转债均价分位 & 转股溢价率</div>
    <canvas id="cb-chart-valuation" height="200"></canvas>
  </div>
  <div class="card" style="padding:14px">
    <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">DELTA中位数走势</div>
    <canvas id="cb-chart-delta" height="200"></canvas>
  </div>
  <div class="card" style="padding:14px">
    <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:8px">债底：价格中位数 & 破面值占比</div>
    <canvas id="cb-chart-floor" height="200"></canvas>
  </div>
</div>

<!-- 指标说明 -->
<div class="card" style="padding:14px;font-size:11px;color:var(--text-sub);line-height:1.7">
  <div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px">📖 指标说明</div>
  ① <b>转债友好度</b>：活跃度(25%) + 估值(25%) + DELTA(25%) + 债底(25%) 综合评分<br>
  ② <b>活跃度</b>：转债成交额变化与中证1000/2000涨跌幅的20日滚动相关系数，高相关=小盘活跃带动转债<br>
  ③ <b>估值水位</b>：成交量前50%转债的平均价格在历史窗口中的分位数 + 平均转股溢价率。低分位+低溢价=便宜且股性强<br>
  ④ <b>DELTA</b>：成交量前50%转债涨跌幅 vs 正股涨跌幅的20日回归斜率中位数。高DELTA=偏股性，策略空间大<br>
  ⑤ <b>债底</b>：全市场转债价格中位数 + 破面值(＜100元)占比。破面值少=安全垫厚<br>
  ⑥ <b>转股溢价率</b> = (转债价格 - 转股价值) / 转股价值 × 100%，转股价值 = 面值/转股价 × 正股价
</div>

</div>

<script>
var _cbChartsInited = false;
function initCbCharts() {{
  if (_cbChartsInited) return;
  _cbChartsInited = true;

  var dates = {json.dumps(dates_js)};
  var cbAmount = {json.dumps(mod1['series']['cb_amount'])};
  var corr1000 = {json.dumps(mod1['series']['corr_1000'])};
  var corr2000 = {json.dumps(mod1['series']['corr_2000'])};
  var avgPrice = {json.dumps(mod2['series']['avg_price'])};
  var avgPremium = {json.dumps(mod2['series']['avg_premium'])};
  var pricePct = {json.dumps(mod2['series']['price_percentile'])};
  var deltaMed = {json.dumps(mod3['series']['delta_median'])};
  var medianPrice = {json.dumps(mod4['series']['median_price'])};
  var belowPar = {json.dumps(mod4['series']['below_par_ratio'])};

  var baseOpts = {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color:'#94a3b8', font:{{size:10}} }} }} }},
    scales: {{
      x: {{ ticks: {{ color:'#64748b', font:{{size:9}}, maxRotation:45 }} }},
      y: {{ ticks: {{ color:'#64748b', font:{{size:9}} }}, grid:{{color:'rgba(148,163,184,0.1)'}} }}
    }}
  }};

  // 图1：成交额 + 相关系数
  new Chart(document.getElementById('cb-chart-activity'), {{
    type:'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label:'成交额(亿)', data:cbAmount, borderColor:'#3b82f6', backgroundColor:'rgba(59,130,246,0.1)', fill:true, tension:0.3, pointRadius:0, yAxisID:'y' }},
        {{ label:'相关系数(1000)', data:corr1000, borderColor:'#f59e0b', borderDash:[4,2], tension:0.3, pointRadius:0, yAxisID:'y1' }},
        {{ label:'相关系数(2000)', data:corr2000, borderColor:'#ef4444', borderDash:[4,2], tension:0.3, pointRadius:0, yAxisID:'y1' }}
      ]
    }},
    options: {{ ...baseOpts, scales: {{
      ...baseOpts.scales,
      y: {{ position:'left', ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{color:'rgba(148,163,184,0.1)'}} }},
      y1: {{ position:'right', min:-1, max:1, ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{drawOnChartArea:false}} }}
    }} }}
  }});

  // 图2：均价分位 + 溢价率
  new Chart(document.getElementById('cb-chart-valuation'), {{
    type:'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label:'价格分位(%)', data:pricePct, borderColor:'#3b82f6', tension:0.3, pointRadius:0, yAxisID:'y' }},
        {{ label:'转股溢价率(%)', data:avgPremium, borderColor:'#ef4444', tension:0.3, pointRadius:0, yAxisID:'y1' }}
      ]
    }},
    options: {{ ...baseOpts, scales: {{
      ...baseOpts.scales,
      y: {{ position:'left', min:0, max:100, ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{color:'rgba(148,163,184,0.1)'}} }},
      y1: {{ position:'right', ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{drawOnChartArea:false}} }}
    }} }}
  }});

  // 图3：DELTA中位数
  new Chart(document.getElementById('cb-chart-delta'), {{
    type:'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label:'DELTA中位数', data:deltaMed, borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,0.1)', fill:true, tension:0.3, pointRadius:0 }}
      ]
    }},
    options: {{ ...baseOpts, scales: {{
      ...baseOpts.scales,
      y: {{ min:0, max:1, ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{color:'rgba(148,163,184,0.1)'}} }}
    }} }}
  }});

  // 图4：价格中位数 + 破面值占比
  new Chart(document.getElementById('cb-chart-floor'), {{
    type:'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label:'价格中位数', data:medianPrice, borderColor:'#3b82f6', tension:0.3, pointRadius:0, yAxisID:'y' }},
        {{ label:'破面值占比(%)', data:belowPar, borderColor:'#ef4444', borderDash:[4,2], tension:0.3, pointRadius:0, yAxisID:'y1' }}
      ]
    }},
    options: {{ ...baseOpts, scales: {{
      ...baseOpts.scales,
      y: {{ position:'left', ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{color:'rgba(148,163,184,0.1)'}} }},
      y1: {{ position:'right', min:0, ticks:{{color:'#64748b',font:{{size:9}}}}, grid:{{drawOnChartArea:false}} }}
    }} }}
  }});
}}
</script>
'''
    return html


def inject(html_content):
    """注入到 index.html 的转债 tab"""
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        page = f.read()

    # 找到转债 tab 的占位内容并替换
    old_pattern = r'<div class="strat-page" id="strat-convertible">.*?</div>\s*</div>'
    # 替换为新内容
    new_content = f'<div class="strat-page" id="strat-convertible">{html_content}</div>'
    
    # 用正则替换（贪婪匹配到最后一个 </div>）
    # 更安全的方式：找到开始标签，然后找到下一个 strat-page
    start_marker = '<div class="strat-page" id="strat-convertible">'
    start_idx = page.find(start_marker)
    if start_idx == -1:
        log("ERROR: 找不到 strat-convertible")
        return False
    
    # 找到这个 div 的结束位置（下一个 strat-page 或 </main>）
    next_markers = ['<div class="strat-page" id="strat-arb">', '</main>']
    end_idx = len(page)
    for marker in next_markers:
        idx = page.find(marker, start_idx + len(start_marker))
        if idx != -1 and idx < end_idx:
            end_idx = idx
    
    # 替换
    page = page[:start_idx] + new_content + '\n      ' + page[end_idx:]

    # 确保 tab 切换事件里有转债图表的延迟初始化
    if 'initCbCharts' not in page:
        # 在 tab 切换事件里加入
        # 找到已有的 initCtaCharts 或 initMsCharts 的位置
        insert_patterns = [
            "if(s==='cta') setTimeout(initCtaCharts,50)",
            "if(s==='momentum-stock') setTimeout(initMsCharts,50)",
        ]
        cb_init_line = "if(s==='convertible') setTimeout(initCbCharts,50);"
        
        for pat in insert_patterns:
            if pat in page:
                page = page.replace(pat, pat + '\n          ' + cb_init_line)
                break
        else:
            # 如果找不到已有的，在 strat-tab click 事件里加
            log("WARNING: 未找到已有的图表初始化代码，手动添加")

    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(page)
    
    return True


def main():
    log("=" * 50)
    log("转债指增策略环境 — 注入脚本")
    log("=" * 50)

    env = load_env()
    log(f"数据: {env['meta']['last_date']}, 评分: {env['score']}")

    html = build_html(env)
    log(f"HTML: {len(html)} chars")

    ok = inject(html)
    if ok:
        log("✅ 注入成功")
    else:
        log("❌ 注入失败")


if __name__ == "__main__":
    main()
