#!/usr/bin/env python3
"""
商品CTA策略环境 — 注入脚本
读取 commodity_cta.json，生成 HTML/JS 注入到 index.html 的 CTA tab
"""

import json, os

BASE_DIR = '/Users/apple/Desktop/gamt-dashboard'
JSON_PATH = os.path.join(BASE_DIR, 'commodity_cta/commodity_cta.json')
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')


def load_data():
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def friendly_color(v):
    if v >= 60: return '#10b981'
    if v >= 40: return '#f59e0b'
    return '#ef4444'


def friendly_label(v):
    if v >= 70: return '极佳'
    if v >= 60: return '良好'
    if v >= 40: return '一般'
    if v >= 25: return '偏弱'
    return '低迷'


def trend_color(t):
    if t in ('多头', '上升'): return '#10b981'
    if t in ('空头', '下降'): return '#ef4444'
    return '#94a3b8'


def signal_badge(n):
    if n >= 3: return '<span style="background:#10b981;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600">★★★</span>'
    if n >= 2: return '<span style="background:#f59e0b;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600">★★</span>'
    if n >= 1: return '<span style="background:#3b82f6;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600">★</span>'
    return '<span style="color:#94a3b8;font-size:10px">—</span>'


def fmt_date(d):
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def build_html(data):
    env = data.get('mod1_cta_env', {})
    scan = data.get('mod2_trend_scan', {})
    macro = data.get('mod3_macro_ratio', {})

    summary = env.get('summary', {})
    per_symbol = env.get('per_symbol', {})
    symbols_list = scan.get('symbols', [])
    
    cta_f = summary.get('cta_friendly', 0)
    cta_color = friendly_color(cta_f)
    cta_label = friendly_label(cta_f)
    n_active = summary.get('n_active', 0)
    trend_pct = summary.get('trend_pct', 0)
    trend_count = summary.get('trend_count', 0)
    avg_vol = summary.get('avg_vol_20d', 0)
    avg_vr = summary.get('avg_volume_ratio', 0)
    date_str = fmt_date(summary.get('date', ''))

    # 宏观比价
    cu_au = macro.get('cu_au', {})
    sc_au = macro.get('sc_au', {})
    ind_agri = macro.get('ind_agri', {})

    # 比价时间序列 → JS 数据
    def series_to_js(r):
        s = r.get('series', [])
        dates = [f"{p['date'][4:6]}/{p['date'][6:8]}" for p in s]
        vals = [p['value'] for p in s]
        return json.dumps(dates), json.dumps(vals)

    cu_au_dates_js, cu_au_vals_js = series_to_js(cu_au)
    sc_au_dates_js, sc_au_vals_js = series_to_js(sc_au)
    ind_agri_dates_js, ind_agri_vals_js = series_to_js(ind_agri)

    # 篮子净值序列
    basket = macro.get('_basket_nav', {})
    ind_nav = basket.get('industrial', [])
    agri_nav = basket.get('agricultural', [])
    basket_dates_js = json.dumps([f"{p[0][4:6]}/{p[0][6:8]}" for p in ind_nav])
    ind_nav_js = json.dumps([p[1] for p in ind_nav])
    agri_nav_js = json.dumps([p[1] for p in agri_nav])

    # 品种扫描 top 15
    top_symbols = symbols_list[:15]

    # 按板块统计趋势品种
    sector_stats = {}
    for s in per_symbol.values():
        sec = s.get('sector', '其他')
        if sec not in sector_stats:
            sector_stats[sec] = {'total': 0, 'trend': 0}
        if s.get('avg_daily_amt', 0) > 500:
            sector_stats[sec]['total'] += 1
            if s.get('has_trend'):
                sector_stats[sec]['trend'] += 1

    # ── HTML ──
    html = f'''
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
        <span style="font-size:13px;color:#888">📦 商品CTA · 数据截至 <b style="color:#2d3142">{date_str}</b></span>
      </div>
      <!-- CTA策略环境总览 -->
      <div class="overview-grid">
        <div class="ov-card" style="border-left-color:{cta_color}">
          <div class="ov-label">CTA友好度</div>
          <div class="ov-value" style="color:{cta_color}">{cta_f}</div>
          <div class="ov-sub">{cta_label} · 0-100综合评分</div>
        </div>
        <div class="ov-card blue">
          <div class="ov-label">活跃品种</div>
          <div class="ov-value">{n_active}</div>
          <div class="ov-sub">日均成交额 &gt; 500万</div>
        </div>
        <div class="ov-card" style="border-left-color:{"#10b981" if trend_pct > 0.3 else "#f59e0b" if trend_pct > 0.1 else "#ef4444"}">
          <div class="ov-label">趋势品种占比</div>
          <div class="ov-value">{trend_pct:.1%}</div>
          <div class="ov-sub">{trend_count}/{n_active} 有明显趋势</div>
        </div>
        <div class="ov-card amber">
          <div class="ov-label">平均20日波动率</div>
          <div class="ov-value">{avg_vol:.1%}</div>
          <div class="ov-sub">活跃品种年化波动率均值</div>
        </div>
        <div class="ov-card slate">
          <div class="ov-label">成交量比</div>
          <div class="ov-value">{avg_vr:.2f}</div>
          <div class="ov-sub">MA20/MA60，&gt;1.2为放量</div>
        </div>
        <div class="ov-card green">
          <div class="ov-label">数据日期</div>
          <div class="ov-value" style="font-size:18px">{date_str}</div>
          <div class="ov-sub">最新交易日</div>
        </div>
      </div>

      <!-- 宏观比价 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> 宏观比价信号</div>
        <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="border-bottom:1px solid #e2e8f0;color:#64748b;text-align:left">
              <th style="padding:8px 6px">比价</th>
              <th style="padding:8px 6px">最新值</th>
              <th style="padding:8px 6px">20日变化</th>
              <th style="padding:8px 6px">分位数</th>
              <th style="padding:8px 6px">趋势</th>
              <th style="padding:8px 6px">含义</th>
            </tr>
          </thead>
          <tbody>'''

    for key, label in [('cu_au', '铜金比'), ('sc_au', '油金比'), ('ind_agri', '工业品/农产品')]:
        r = macro.get(key, {})
        if not r:
            continue
        chg = r.get('chg_20d_pct', 0)
        chg_color = '#10b981' if chg > 0 else '#ef4444' if chg < 0 else '#94a3b8'
        pctile = r.get('pctile_60d', 0)
        trend = r.get('trend', '—')
        tc = trend_color(trend)
        meaning = r.get('meaning', '')
        latest = r.get('latest', 0)
        
        html += f'''
            <tr style="border-bottom:1px solid #f1f5f9">
              <td style="padding:8px 6px;font-weight:600">{label}</td>
              <td style="padding:8px 6px">{latest:.4f}</td>
              <td style="padding:8px 6px;color:{chg_color};font-weight:600">{chg:+.2f}%</td>
              <td style="padding:8px 6px">{pctile:.0%}</td>
              <td style="padding:8px 6px;color:{tc};font-weight:600">{trend}</td>
              <td style="padding:8px 6px;color:#94a3b8;font-size:11px">{meaning}</td>
            </tr>'''

    html += '''
          </tbody>
        </table>
        </div>
      </div>

      <!-- 宏观比价走势图 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 铜金比走势（CU/AU）</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">上升=经济预期改善，下降=避险升温</div>
        <div style="position:relative;height:220px"><canvas id="cta-cu-au"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#f59e0b"></span> 油金比走势（SC/AU）</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">上升=通胀预期/需求强，下降=衰退预期</div>
        <div style="position:relative;height:220px"><canvas id="cta-sc-au"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#10b981"></span> 工业品 vs 农产品篮子</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">工业篮子(RB,CU,AL,MA,TA,EG) vs 农产品篮子(M,P,SR,C,OI,CF) 等权归1复利</div>
        <div style="position:relative;height:220px"><canvas id="cta-ind-agri"></canvas></div>
      </div>

      <script>
      var _ctaChartsInited=false;
      function initCtaCharts(){
        if(_ctaChartsInited)return;
        _ctaChartsInited=true;
        var ctaB={responsive:true,maintainAspectRatio:false,
          interaction:{mode:'index',intersect:false},
          plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10},padding:12}},
            tooltip:{callbacks:{label:function(c){return c.dataset.label+': '+c.parsed.y.toFixed(4)}}}},
          scales:{x:{ticks:{maxTicksToShow:10,font:{size:9},color:'#94a3b8'},grid:{display:false}},
            y:{ticks:{font:{size:9},color:'#94a3b8'},grid:{color:'#f1f5f9'}}}
        };
        new Chart(document.getElementById('cta-cu-au'),{
          type:'line',
          data:{labels:''' + cu_au_dates_js + ''',datasets:[
            {label:'铜金比',data:''' + cu_au_vals_js + ''',borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,0.06)',fill:true,borderWidth:2,pointRadius:2,pointBackgroundColor:'#ef4444',tension:.3}
          ]},
          options:ctaB
        });
        new Chart(document.getElementById('cta-sc-au'),{
          type:'line',
          data:{labels:''' + sc_au_dates_js + ''',datasets:[
            {label:'油金比',data:''' + sc_au_vals_js + ''',borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,0.06)',fill:true,borderWidth:2,pointRadius:2,pointBackgroundColor:'#f59e0b',tension:.3}
          ]},
          options:ctaB
        });
        new Chart(document.getElementById('cta-ind-agri'),{
          type:'line',
          data:{labels:''' + basket_dates_js + ''',datasets:[
            {label:'工业品篮子',data:''' + ind_nav_js + ''',borderColor:'#ef4444',borderWidth:2,pointRadius:1.5,tension:.3},
            {label:'农产品篮子',data:''' + agri_nav_js + ''',borderColor:'#10b981',borderWidth:2,pointRadius:1.5,tension:.3}
          ]},
          options:Object.assign({},ctaB,{scales:{x:ctaB.scales.x,y:{ticks:{font:{size:9},color:'#94a3b8',callback:function(v){return v.toFixed(3)}},grid:{color:'#f1f5f9'}}}})
        });
      }
      </script>

      <!-- 品种趋势扫描 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 品种趋势扫描 Top 15</div>
        <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="border-bottom:1px solid #e2e8f0;color:#64748b;text-align:left">
              <th style="padding:8px 4px">#</th>
              <th style="padding:8px 4px">品种</th>
              <th style="padding:8px 4px">板块</th>
              <th style="padding:8px 4px">收盘</th>
              <th style="padding:8px 4px">涨跌幅</th>
              <th style="padding:8px 4px">趋势</th>
              <th style="padding:8px 4px">波动率</th>
              <th style="padding:8px 4px">量比</th>
              <th style="padding:8px 4px">评分</th>
              <th style="padding:8px 4px">信号</th>
            </tr>
          </thead>
          <tbody>'''

    for i, s in enumerate(top_symbols):
        sym = s.get('symbol', '?')
        sec = s.get('sector', '?')
        close = s.get('close', 0)
        chg = s.get('chg_20d', s.get('chg_pct', 0))
        chg_color = '#10b981' if chg > 0 else '#ef4444' if chg < 0 else '#94a3b8'
        td = s.get('trend_dir', '?')
        tc = trend_color(td)
        vol = s.get('vol_20d', 0)
        vr = s.get('volume_ratio', 0)
        score = s.get('trend_score', 0)
        sig = s.get('signal_count', 0)
        badge = signal_badge(sig)
        drivers = s.get('drivers', [])
        driver_str = '，'.join(drivers) if drivers else '—'

        # 评分颜色
        if score >= 0.7: sc_color = '#10b981'
        elif score >= 0.5: sc_color = '#f59e0b'
        else: sc_color = '#94a3b8'

        html += f'''
            <tr style="border-bottom:1px solid #f1f5f9" title="{driver_str}">
              <td style="padding:6px 4px;color:#94a3b8">{i+1}</td>
              <td style="padding:6px 4px;font-weight:700">{sym}</td>
              <td style="padding:6px 4px;color:#64748b;font-size:11px">{sec}</td>
              <td style="padding:6px 4px">{close:,.1f}</td>
              <td style="padding:6px 4px;color:{chg_color};font-weight:600">{chg:+.1f}%</td>
              <td style="padding:6px 4px;color:{tc};font-weight:600">{td}</td>
              <td style="padding:6px 4px">{vol:.1%}</td>
              <td style="padding:6px 4px">{vr:.2f}</td>
              <td style="padding:6px 4px;color:{sc_color};font-weight:700">{score:.3f}</td>
              <td style="padding:6px 4px">{badge}</td>
            </tr>'''

    html += '''
          </tbody>
        </table>
        </div>
      </div>

      <!-- 板块趋势分布 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#3b82f6"></span> 板块趋势分布</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">'''

    sector_colors = {
        '黑色系': '#374151', '有色金属': '#f59e0b', '贵金属': '#eab308',
        '能源化工': '#8b5cf6', '农产品': '#10b981',
    }
    for sec in ['黑色系', '有色金属', '贵金属', '能源化工', '农产品']:
        st = sector_stats.get(sec, {'total': 0, 'trend': 0})
        sc = sector_colors.get(sec, '#94a3b8')
        pct = st['trend'] / st['total'] * 100 if st['total'] > 0 else 0
        html += f'''
          <div style="flex:1;min-width:140px;background:#f8fafc;border-radius:8px;padding:12px;border-left:3px solid {sc}">
            <div style="font-size:11px;color:#64748b;margin-bottom:4px">{sec}</div>
            <div style="font-size:18px;font-weight:700;color:#1e293b">{st["trend"]}/{st["total"]}</div>
            <div style="font-size:10px;color:#94a3b8">趋势占比 {pct:.0f}%</div>
          </div>'''

    html += '''
        </div>
      </div>

      <!-- 指标说明 -->
      <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
        <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 指标说明</div>
        <p>① CTA友好度 = 0.40×趋势占比 + 0.30×波动率分位 + 0.30×成交量比，标准化到0-100</p>
        <p>② 趋势判定：MA20斜率 &gt; 0.5%为多头，&lt; -0.5%为空头</p>
        <p>③ 品种评分 = 0.40×|涨跌幅标准化| + 0.30×波动率分位 + 0.30×成交量比标准化</p>
        <p>④ 信号：趋势确认(多头/空头) + 波动放大(vol↑) + 放量(量比&gt;1.2)，满足越多越强</p>
        <p>⑤ 铜金比↑=经济预期改善，↓=避险升温；油金比↑=通胀/需求强，↓=衰退预期</p>
        <p>⑥ 工业品/农产品：工业篮子(RB,CU,AL,MA,TA,EG) vs 农产品篮子(M,P,SR,C,OI,CF) 等权归1复利比值</p>
        <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare fut_daily 连续合约 · 更新：''' + date_str + '''</p>
      </div>'''

    return html


def inject(html_content):
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()

    # 找到 CTA tab 的占位内容并替换
    start_marker = '<div class="strat-page" id="strat-cta">'
    end_marker = '<div class="strat-page" id="strat-convertible">'

    start_idx = index.find(start_marker)
    end_idx = index.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(f"❌ 找不到注入点 start={start_idx} end={end_idx}")
        return False

    new_div = start_marker + html_content + '\n      </div>\n      '
    new_index = index[:start_idx] + new_div + index[end_idx:]

    # 激活 CTA tab（去掉 opacity）
    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="cta" style="opacity:.4">',
        '<div class="strat-tab" data-strat="cta">'
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_index)
    return True


def main():
    print("📦 商品CTA策略环境 — 注入")

    if not os.path.exists(JSON_PATH):
        print(f"❌ 数据文件不存在: {JSON_PATH}")
        print("   请先运行: cd commodity_cta && python3 commodity_cta_main.py --run")
        return

    data = load_data()
    env = data.get('mod1_cta_env', {}).get('summary', {})
    print(f"📖 CTA友好度={env.get('cta_friendly')} 日期={env.get('date')}")

    html = build_html(data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        print(f"✅ 注入成功！CTA tab 已激活")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
