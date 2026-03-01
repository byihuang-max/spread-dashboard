#!/usr/bin/env python3
"""
商品CTA策略环境 — 注入脚本（v2：含PCA模块）
读取 commodity_cta.json，生成 HTML/JS 注入到 index.html 的 CTA tab

展示顺序（Roni 2026-03-01 要求）：
  1. mod1b PCA核心引擎（默认展开，主角）
  2. mod1 CTA友好度（可折叠，默认收起）
  3. mod2b PCA Loading增强（默认展开，主角）
  4. mod2 品种趋势扫描（可折叠，默认收起）
  5. mod3 宏观比价（不动）
  6. 指标说明
"""

import json, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
JSON_PATH = os.path.join(BASE_DIR, 'commodity_cta.json')
INDEX_PATH = os.path.join(REPO_ROOT, 'index.html')


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

def env_type_color(t):
    if t == '单一趋势主导': return '#10b981'
    if t == '温和趋势': return '#3b82f6'
    if t == '双阵营对抗': return '#f59e0b'
    return '#ef4444'

def env_type_emoji(t):
    if t == '单一趋势主导': return '🟢'
    if t == '温和趋势': return '🔵'
    if t == '双阵营对抗': return '🟡'
    return '🔴'

def role_color(r):
    if r in ('核心驱动', '领涨/领跌核心'): return '#10b981'
    if r in ('显著参与', '趋势跟随主力'): return '#3b82f6'
    if r in ('分化主力', '板块分化旗手'): return '#f59e0b'
    if r == '独立行情': return '#8b5cf6'
    return '#94a3b8'


def build_html(data):
    env = data.get('mod1_cta_env', {})
    pca = data.get('mod1b_pca_engine', {})
    scan = data.get('mod2_trend_scan', {})
    pca_ld = data.get('mod2b_pca_loading', {})
    macro = data.get('mod3_macro_ratio', {})

    summary = env.get('summary', {})
    per_symbol = env.get('per_symbol', {})
    symbols_list = scan.get('symbols', [])
    rolling = pca.get('rolling', [])
    latest_pca = rolling[-1] if rolling else {}
    pca_loadings = pca_ld.get('symbols', [])
    pca_sectors = pca_ld.get('sectors', {})

    date_str = fmt_date(latest_pca.get('date', summary.get('date', '')))

    # ═══════════════════════════════════════════
    # 开始构建 HTML
    # ═══════════════════════════════════════════
    html = f'''
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
        <span style="font-size:13px;color:#888">📦 商品CTA · 数据截至 <b style="color:#2d3142">{date_str}</b></span>
      </div>
'''

    # ─── Section 1: mod1b PCA核心引擎（主角，默认展开）───
    if latest_pca:
        pc1_r = latest_pca.get('pc1_ratio', 0)
        pc2_r = latest_pca.get('pc2_ratio', 0)
        combined_r = latest_pca.get('combined_ratio', 0)
        env_type = latest_pca.get('env_type', '—')
        momentum = latest_pca.get('momentum_signal', '—')
        pca_f = latest_pca.get('pca_friendly', 0)
        pca_color = friendly_color(pca_f)
        pca_label = friendly_label(pca_f)
        et_color = env_type_color(env_type)
        et_emoji = env_type_emoji(env_type)
        pc1_cum = latest_pca.get('pc1_cumsum', 0)

        # PCA时序数据 for charts
        pca_dates_js = json.dumps([fmt_date(r['date'])[5:] for r in rolling])
        pc1_ratio_js = json.dumps([round(r['pc1_ratio'] * 100, 1) for r in rolling])
        pc2_ratio_js = json.dumps([round(r['pc2_ratio'] * 100, 1) for r in rolling])
        pca_friendly_js = json.dumps([r['pca_friendly'] for r in rolling])
        pc1_cum_js = json.dumps([round(r['pc1_cumsum'], 2) for r in rolling])

        n_syms = pca.get('meta', {}).get('n_symbols', 0)

        html += f'''
      <!-- ═══ PCA核心引擎（主角） ═══ -->
      <div class="overview-grid">
        <div class="ov-card" style="border-left-color:{pca_color}">
          <div class="ov-label">PCA友好度</div>
          <div class="ov-value" style="color:{pca_color}">{pca_f}</div>
          <div class="ov-sub">{pca_label} · 基于品种共振强度</div>
        </div>
        <div class="ov-card" style="border-left-color:{et_color}">
          <div class="ov-label">环境类型</div>
          <div class="ov-value" style="font-size:16px;color:{et_color}">{et_emoji} {env_type}</div>
          <div class="ov-sub">PC1+PC2联合判定</div>
        </div>
        <div class="ov-card blue">
          <div class="ov-label">PC1 解释比</div>
          <div class="ov-value">{pc1_r:.1%}</div>
          <div class="ov-sub">全市场共振强度</div>
        </div>
        <div class="ov-card slate">
          <div class="ov-label">PC2 解释比</div>
          <div class="ov-value">{pc2_r:.1%}</div>
          <div class="ov-sub">板块分化程度</div>
        </div>
        <div class="ov-card amber">
          <div class="ov-label">动量信号</div>
          <div class="ov-value" style="font-size:16px">{momentum}</div>
          <div class="ov-sub">PC1近5日方向</div>
        </div>
        <div class="ov-card green">
          <div class="ov-label">活跃品种</div>
          <div class="ov-value">{n_syms}</div>
          <div class="ov-sub">参与PCA计算</div>
        </div>
      </div>

      <!-- PCA方差解释比走势 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> PCA方差解释比走势</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">PC1高=品种共振强=趋势跟踪友好 | 虚线: PC1=35%为"强共振"阈值</div>
        <div style="position:relative;height:240px"><canvas id="pca-explained"></canvas></div>
      </div>

      <!-- PCA友好度走势 -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#3b82f6"></span> PCA友好度走势</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">综合评分0-100，核心由PC1方差解释比驱动</div>
        <div style="position:relative;height:220px"><canvas id="pca-friendly-chart"></canvas></div>
      </div>

      <!-- PC1累计值（动量/反转）-->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> PC1累计值 — 动量 vs 反转</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">持续同方向=动量主导（趋势跟踪有利）| 频繁翻转=反转主导</div>
        <div style="position:relative;height:220px"><canvas id="pca-momentum"></canvas></div>
      </div>

      <script>
      var _pcaChartsInited=false;
      function initPcaCharts(){{
        if(_pcaChartsInited)return;
        _pcaChartsInited=true;
        var pcaBase={{responsive:true,maintainAspectRatio:false,
          interaction:{{mode:'index',intersect:false}},
          plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}},
            tooltip:{{callbacks:{{label:function(c){{return c.dataset.label+': '+c.parsed.y.toFixed(1)}}}}}}}},
          scales:{{x:{{ticks:{{maxTicksToShow:10,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},
            y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}}}}}}
        }};

        // 方差解释比
        new Chart(document.getElementById('pca-explained'),{{
          type:'line',
          data:{{labels:{pca_dates_js},datasets:[
            {{label:'PC1解释比(%)',data:{pc1_ratio_js},borderColor:'#8b5cf6',backgroundColor:'rgba(139,92,246,0.08)',fill:true,borderWidth:2,pointRadius:1.5,tension:.3}},
            {{label:'PC2解释比(%)',data:{pc2_ratio_js},borderColor:'#f59e0b',borderWidth:1.5,pointRadius:1,borderDash:[4,3],tension:.3}}
          ]}},
          options:Object.assign({{}},pcaBase,{{plugins:Object.assign({{}},pcaBase.plugins,{{
            annotation:{{annotations:{{threshold:{{type:'line',yMin:35,yMax:35,borderColor:'rgba(139,92,246,0.3)',borderWidth:1,borderDash:[6,3],
              label:{{content:'强共振阈值(35%)',enabled:true,position:'start',font:{{size:9}},color:'#8b5cf6'}}}}}}}}
          }})}})
        }});

        // 友好度
        new Chart(document.getElementById('pca-friendly-chart'),{{
          type:'line',
          data:{{labels:{pca_dates_js},datasets:[
            {{label:'PCA友好度',data:{pca_friendly_js},borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,0.08)',fill:true,borderWidth:2,pointRadius:1.5,tension:.3}}
          ]}},
          options:pcaBase
        }});

        // 动量/反转
        new Chart(document.getElementById('pca-momentum'),{{
          type:'line',
          data:{{labels:{pca_dates_js},datasets:[
            {{label:'PC1累计值',data:{pc1_cum_js},borderColor:'#ef4444',backgroundColor:function(ctx){{
              var v=ctx.raw||0; return v>=0?'rgba(16,185,129,0.1)':'rgba(239,68,68,0.1)';
            }},fill:true,borderWidth:2,pointRadius:1.5,tension:.3}}
          ]}},
          options:pcaBase
        }});
      }}
      </script>
'''

    # ─── Section 2: mod1 传统CTA友好度（可折叠，默认收起）───
    cta_f_old = summary.get('cta_friendly', 0)
    n_active = summary.get('n_active', 0)
    trend_pct = summary.get('trend_pct', 0)
    trend_count = summary.get('trend_count', 0)
    avg_vol = summary.get('avg_vol_20d', 0)
    avg_vr = summary.get('avg_volume_ratio', 0)

    html += f'''
      <!-- ═══ 传统CTA友好度（可折叠） ═══ -->
      <div class="card" style="padding:0;overflow:hidden">
        <div onclick="this.parentElement.classList.toggle('collapsed-section')" 
             style="padding:14px 16px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;background:#f8fafc;border-bottom:1px solid #f1f5f9">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="dot" style="background:#94a3b8"></span>
            <span style="font-size:13px;font-weight:600;color:#64748b">传统CTA友好度（规则驱动）</span>
            <span style="font-size:11px;color:#94a3b8">点击展开</span>
          </div>
          <span style="font-size:18px;font-weight:700;color:{friendly_color(cta_f_old)}">{cta_f_old}</span>
        </div>
        <div class="collapsible-content" style="display:none;padding:16px">
          <div class="overview-grid">
            <div class="ov-card" style="border-left-color:{friendly_color(cta_f_old)}">
              <div class="ov-label">CTA友好度</div>
              <div class="ov-value" style="color:{friendly_color(cta_f_old)}">{cta_f_old}</div>
              <div class="ov-sub">{friendly_label(cta_f_old)} · 0.4×趋势+0.3×波动+0.3×量比</div>
            </div>
            <div class="ov-card blue">
              <div class="ov-label">趋势品种占比</div>
              <div class="ov-value">{trend_pct:.1%}</div>
              <div class="ov-sub">{trend_count}/{n_active} 有明显趋势</div>
            </div>
            <div class="ov-card amber">
              <div class="ov-label">平均20日波动率</div>
              <div class="ov-value">{avg_vol:.1%}</div>
              <div class="ov-sub">年化波动率均值</div>
            </div>
            <div class="ov-card slate">
              <div class="ov-label">成交量比</div>
              <div class="ov-value">{avg_vr:.2f}</div>
              <div class="ov-sub">MA20/MA60</div>
            </div>
          </div>
        </div>
      </div>
'''

    # ─── Section 3: mod2b PCA Loading增强（主角，默认展开）───
    if pca_loadings:
        divergence = pca_ld.get('divergence_axis', '—')
        pc1_exp = pca_ld.get('pc1_explained', 0)
        pc2_exp = pca_ld.get('pc2_explained', 0)

        html += f'''
      <!-- ═══ PCA Loading品种扫描（主角） ═══ -->
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> PCA品种结构分析</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:12px">
          PC1解释{pc1_exp:.1%} · PC2解释{pc2_exp:.1%} · 分化轴: <b style="color:#64748b">{divergence}</b>
        </div>

        <!-- 板块一致性卡片 -->
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">'''

        sector_colors_map = {
            '黑色系': '#374151', '有色金属': '#f59e0b', '贵金属': '#eab308',
            '能源化工': '#8b5cf6', '农产品': '#10b981',
        }
        for sec_name in ['能源化工', '有色金属', '黑色系', '贵金属', '农产品']:
            sec = pca_sectors.get(sec_name, {})
            if not sec:
                continue
            sc = sector_colors_map.get(sec_name, '#94a3b8')
            avg_pc1 = sec.get('avg_pc1_loading', 0)
            coherence = sec.get('coherence', 0)
            coh_color = '#10b981' if coherence > 0.8 else '#f59e0b' if coherence > 0.5 else '#ef4444'
            pc1_sign = '+' if avg_pc1 > 0 else ''

            html += f'''
          <div style="flex:1;min-width:140px;background:#f8fafc;border-radius:8px;padding:12px;border-left:3px solid {sc}">
            <div style="font-size:11px;color:#64748b;margin-bottom:4px">{sec_name}</div>
            <div style="font-size:14px;font-weight:700;color:#1e293b">PC1: {pc1_sign}{avg_pc1:.3f}</div>
            <div style="font-size:10px;color:{coh_color}">一致性 {coherence:.0%} · {sec.get("n_symbols",0)}品种</div>
          </div>'''

        html += '''
        </div>

        <!-- Loading排名表 -->
        <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="border-bottom:1px solid #e2e8f0;color:#64748b;text-align:left">
              <th style="padding:8px 4px">#</th>
              <th style="padding:8px 4px">品种</th>
              <th style="padding:8px 4px">板块</th>
              <th style="padding:8px 4px">PC1</th>
              <th style="padding:8px 4px">PC2</th>
              <th style="padding:8px 4px">20日涨跌</th>
              <th style="padding:8px 4px">角色</th>
              <th style="padding:8px 4px">产业驱动</th>
            </tr>
          </thead>
          <tbody>'''

        for i, s in enumerate(pca_loadings[:20]):
            sym = s['symbol']
            sec = s['sector']
            pc1 = s['pc1_loading']
            pc2 = s['pc2_loading']
            chg = s.get('chg_20d', 0)
            role = s['combined_role']
            rc = role_color(role)
            chg_c = '#10b981' if chg > 0 else '#ef4444' if chg < 0 else '#94a3b8'
            pc1_c = '#10b981' if pc1 > 0 else '#ef4444'
            pc2_c = '#10b981' if pc2 > 0 else '#ef4444'
            drivers = s.get('industry_drivers', '')

            # PC1 bar width (visual)
            bar_w = min(abs(pc1) / 0.20 * 100, 100)

            html += f'''
            <tr style="border-bottom:1px solid #f1f5f9">
              <td style="padding:6px 4px;color:#94a3b8">{i+1}</td>
              <td style="padding:6px 4px;font-weight:700">{sym}</td>
              <td style="padding:6px 4px;color:#64748b;font-size:11px">{sec}</td>
              <td style="padding:6px 4px">
                <div style="display:flex;align-items:center;gap:4px">
                  <span style="color:{pc1_c};font-weight:600;min-width:48px">{pc1:+.3f}</span>
                  <div style="width:60px;height:6px;background:#f1f5f9;border-radius:3px;overflow:hidden">
                    <div style="width:{bar_w}%;height:100%;background:{pc1_c};border-radius:3px"></div>
                  </div>
                </div>
              </td>
              <td style="padding:6px 4px;color:{pc2_c};font-weight:600">{pc2:+.3f}</td>
              <td style="padding:6px 4px;color:{chg_c};font-weight:600">{chg:+.1f}%</td>
              <td style="padding:6px 4px"><span style="color:{rc};font-size:11px;font-weight:600">{role}</span></td>
              <td style="padding:6px 4px;color:#94a3b8;font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{drivers}">{drivers}</td>
            </tr>'''

        html += '''
          </tbody>
        </table>
        </div>
      </div>
'''

    # ─── Section 4: mod2 传统品种扫描（可折叠，默认收起）───
    top_symbols = symbols_list[:15]

    html += '''
      <!-- ═══ 传统品种趋势扫描（可折叠） ═══ -->
      <div class="card" style="padding:0;overflow:hidden">
        <div onclick="this.parentElement.classList.toggle('collapsed-section')" 
             style="padding:14px 16px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;background:#f8fafc;border-bottom:1px solid #f1f5f9">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="dot" style="background:#94a3b8"></span>
            <span style="font-size:13px;font-weight:600;color:#64748b">传统品种趋势扫描（涨跌幅驱动）</span>
            <span style="font-size:11px;color:#94a3b8">点击展开</span>
          </div>
          <span style="font-size:12px;color:#94a3b8">''' + str(len(symbols_list)) + ''' 品种</span>
        </div>
        <div class="collapsible-content" style="display:none;padding:16px">
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
              <th style="padding:8px 4px">R²</th>
              <th style="padding:8px 4px">OI(5d)</th>
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
        r2 = s.get('r2', 0)
        oi_5d = s.get('oi_chg_5d', 0)
        score = s.get('trend_score', 0)
        sig = s.get('signal_count', 0)
        badge = signal_badge(sig)
        drivers = s.get('drivers', [])
        driver_str = '，'.join(drivers) if drivers else '—'

        sc_color = '#10b981' if score >= 0.7 else '#f59e0b' if score >= 0.5 else '#94a3b8'
        r2_color = '#10b981' if r2 > 0.8 else '#f59e0b' if r2 > 0.5 else '#94a3b8'
        oi_color = '#10b981' if oi_5d > 3 else '#ef4444' if oi_5d < -3 else '#94a3b8'

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
              <td style="padding:6px 4px;color:{r2_color};font-weight:600">{r2:.2f}</td>
              <td style="padding:6px 4px;color:{oi_color}">{oi_5d:+.1f}%</td>
              <td style="padding:6px 4px;color:{sc_color};font-weight:700">{score:.3f}</td>
              <td style="padding:6px 4px">{badge}</td>
            </tr>'''

    html += '''
          </tbody>
        </table>
        </div>
        </div>
      </div>
'''

    # ─── Section 5: mod3 宏观比价（不动）───
    cu_au = macro.get('cu_au', {})
    sc_au = macro.get('sc_au', {})
    ind_agri = macro.get('ind_agri', {})

    def series_to_js(r):
        s = r.get('series', [])
        dates = [f"{p['date'][4:6]}/{p['date'][6:8]}" for p in s]
        vals = [p['value'] for p in s]
        return json.dumps(dates), json.dumps(vals)

    cu_au_dates_js, cu_au_vals_js = series_to_js(cu_au)
    sc_au_dates_js, sc_au_vals_js = series_to_js(sc_au)
    ind_agri_dates_js, ind_agri_vals_js = series_to_js(ind_agri)

    basket = macro.get('_basket_nav', {})
    ind_nav = basket.get('industrial', [])
    agri_nav = basket.get('agricultural', [])
    basket_dates_js = json.dumps([f"{p[0][4:6]}/{p[0][6:8]}" for p in ind_nav])
    ind_nav_js = json.dumps([p[1] for p in ind_nav])
    agri_nav_js = json.dumps([p[1] for p in agri_nav])

    html += '''
      <!-- ═══ 宏观比价（不动） ═══ -->
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
        chg_c = '#10b981' if chg > 0 else '#ef4444' if chg < 0 else '#94a3b8'
        pctile = r.get('pctile_60d', 0)
        trend = r.get('trend', '—')
        tc = trend_color(trend)
        meaning = r.get('meaning', '')
        latest = r.get('latest', 0)

        html += f'''
            <tr style="border-bottom:1px solid #f1f5f9">
              <td style="padding:8px 6px;font-weight:600">{label}</td>
              <td style="padding:8px 6px">{latest:.4f}</td>
              <td style="padding:8px 6px;color:{chg_c};font-weight:600">{chg:+.2f}%</td>
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
        <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">工业篮子(RB,CU,AL,MA,TA,EG) vs 农产品篮子(M,P,SR,C,OI,CF)</div>
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
          ]},options:ctaB
        });
        new Chart(document.getElementById('cta-sc-au'),{
          type:'line',
          data:{labels:''' + sc_au_dates_js + ''',datasets:[
            {label:'油金比',data:''' + sc_au_vals_js + ''',borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,0.06)',fill:true,borderWidth:2,pointRadius:2,pointBackgroundColor:'#f59e0b',tension:.3}
          ]},options:ctaB
        });
        new Chart(document.getElementById('cta-ind-agri'),{
          type:'line',
          data:{labels:''' + basket_dates_js + ''',datasets:[
            {label:'工业品篮子',data:''' + ind_nav_js + ''',borderColor:'#ef4444',borderWidth:2,pointRadius:1.5,tension:.3},
            {label:'农产品篮子',data:''' + agri_nav_js + ''',borderColor:'#10b981',borderWidth:2,pointRadius:1.5,tension:.3}
          ]},options:Object.assign({},ctaB,{scales:{x:ctaB.scales.x,y:{ticks:{font:{size:9},color:'#94a3b8',callback:function(v){return v.toFixed(3)}},grid:{color:'#f1f5f9'}}}})
        });
      }
      </script>
'''

    # ─── Section 6: 指标说明 ───
    html += '''
      <!-- ═══ 指标说明 ═══ -->
      <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
        <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 指标说明</div>
        <p><b style="color:#8b5cf6">PCA核心引擎</b></p>
        <p>① PCA友好度：基于60日滚动窗口，对全部活跃品种日收益率做主成分分析（PCA），PC1方差解释比为核心驱动</p>
        <p>② PC1方差解释比 = 品种共振强度。&gt;35%=强共振（趋势跟踪友好），&lt;20%=全市场震荡</p>
        <p>③ 环境类型：PC1高+PC2低=单一趋势主导 | PC1高+PC2高=双阵营对抗 | PC1低=震荡</p>
        <p>④ PC1累计值：持续正/负=动量主导，频繁翻转=反转主导</p>
        <p>⑤ Loading：品种在PC1/PC2上的权重，|loading|越大=对该成分影响越大</p>
        <p>⑥ 板块一致性：同板块品种loading标准差越小=越一致（同涨同跌）</p>
        <p style="margin-top:8px"><b style="color:#64748b">传统指标</b></p>
        <p>⑦ CTA友好度(传统) = 0.40×趋势占比 + 0.30×波动率分位 + 0.30×成交量比</p>
        <p>⑧ 品种评分 = 动量25% + MA排列20% + 波动率分位15% + 量比15% + R²15% + Donchian10%</p>
        <p>⑨ 铜金比↑=经济预期改善；油金比↑=通胀/需求强；工业品/农产品比↑=工业品相对强</p>
        <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare fut_daily 连续合约 · PCA窗口60日 · 更新：''' + date_str + '''</p>
      </div>

      <!-- 折叠功能CSS+JS -->
      <style>
      .collapsed-section .collapsible-content{display:none!important}
      .card:not(.collapsed-section) .collapsible-content{display:block!important}
      </style>
      <script>
      // 默认折叠：给所有含collapsible-content的card加上collapsed类
      document.querySelectorAll('#strat-cta .collapsible-content').forEach(function(el){
        el.parentElement.classList.add('collapsed-section');
      });
      </script>'''

    return html


def inject(html_content):
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()

    start_marker = '<div class="strat-page" id="strat-cta">'
    end_marker = '<div class="strat-page" id="strat-convertible">'

    start_idx = index.find(start_marker)
    end_idx = index.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print(f"❌ 找不到注入点 start={start_idx} end={end_idx}")
        return False

    new_div = start_marker + html_content + '\n      </div>\n      '
    new_index = index[:start_idx] + new_div + index[end_idx:]

    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="cta" style="opacity:.4">',
        '<div class="strat-tab" data-strat="cta">'
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_index)
    return True


def main():
    print("📦 商品CTA策略环境 — 注入（v2 含PCA模块）")

    if not os.path.exists(JSON_PATH):
        print(f"❌ 数据文件不存在: {JSON_PATH}")
        return

    data = load_data()

    # 显示数据概况
    rolling = data.get('mod1b_pca_engine', {}).get('rolling', [])
    if rolling:
        latest = rolling[-1]
        print(f"📊 PCA友好度={latest['pca_friendly']} | 环境={latest['env_type']} | 日期={latest['date']}")
    env = data.get('mod1_cta_env', {}).get('summary', {})
    if env:
        print(f"📊 传统友好度={env.get('cta_friendly')} | 日期={env.get('date')}")

    html = build_html(data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        print(f"✅ 注入成功！CTA tab 已更新（PCA模块已加入）")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
