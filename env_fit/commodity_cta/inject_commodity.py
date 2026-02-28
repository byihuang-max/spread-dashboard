#!/usr/bin/env python3
"""
商品CTA策略环境注入脚本
读取 commodity_cta.json，生成 HTML/JS 代码注入到 index.html 的商品CTA tab
"""

import json
import os

BASE_DIR = '/Users/apple/Desktop/gamt-dashboard'
JSON_PATH = os.path.join(BASE_DIR, 'commodity_cta/commodity_cta.json')
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')


def load_data():
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def fmt_date(d):
    return f"{d[4:6]}/{d[6:8]}"


def trend_icon(d):
    if d == 'long': return '🔴'
    if d == 'short': return '🔵'
    return '⚪'


def vol_icon(v):
    if v == 'up': return '↑'
    if v == 'down': return '↓'
    return '→'


def signal_dots(n):
    return '🟢' * n + '⚫' * (3 - n)


def build_html(data):
    env = data['environment']
    scan = data['scan']
    ratios = data['ratios']
    latest = data['latest']
    meta = data['meta']

    # ═══ 模块一：CTA环境总览卡片 ═══
    cta_f = latest['cta_friendly']
    cta_label = latest['cta_label']
    cta_color = '#10b981' if cta_f >= 60 else ('#f59e0b' if cta_f >= 40 else '#3b82f6')

    avg_vol = latest['avg_vol']
    trend_count = latest['trend_count']
    total = latest['total_active']
    trend_pct = latest['trend_pct']
    sig_count = latest['signal_commodities']

    # 环境时序数据（最近60天展示）
    env_dates = env['dates'][-60:]
    env_cta = env['cta_friendly'][-60:]
    env_trend = env['trend_pct'][-60:]
    env_vol = env['avg_vol_20d'][-60:]
    env_vr = env['volume_ratio'][-60:]

    env_dates_js = json.dumps([fmt_date(d) for d in env_dates])
    env_cta_js = json.dumps(env_cta)
    env_trend_js = json.dumps(env_trend)
    env_vol_js = json.dumps(env_vol)
    env_vr_js = json.dumps(env_vr)

    # ═══ 模块二：品种扫描表格 ═══
    # 分为信号品种（signal_count>=2）和其他
    signal_items = [s for s in scan if s['signal_count'] >= 2]
    other_items = [s for s in scan if s['signal_count'] < 2]

    def scan_row(item):
        ti = trend_icon(item['trend_dir'])
        vi = vol_icon(item['vol_trend'])
        vs = '放量' if item['volume_signal'] == 'expand' else ('缩量' if item['volume_signal'] == 'shrink' else '平稳')
        vs_color = '#10b981' if item['volume_signal'] == 'expand' else ('#ef4444' if item['volume_signal'] == 'shrink' else '#94a3b8')
        chg_color = '#ef4444' if item['chg_20d'] > 0 else ('#10b981' if item['chg_20d'] < 0 else '#94a3b8')
        dots = signal_dots(item['signal_count'])
        drivers = item.get('drivers', '')

        row = f'''<tr>
          <td style="font-weight:600">{ti} {item['name']}</td>
          <td style="color:#94a3b8;font-size:10px">{item['sector']}</td>
          <td style="text-align:right">{item['close']:.0f}</td>
          <td style="text-align:right;color:{chg_color}">{item['chg_20d']:+.1f}%</td>
          <td style="text-align:right">{item['vol_20d']:.1f}%</td>
          <td style="text-align:center">{vi}</td>
          <td style="text-align:center;color:{vs_color};font-size:10px">{vs}</td>
          <td style="text-align:center;font-size:10px">{dots}</td>
          <td style="text-align:right;font-weight:600">{item['trend_score']:.0f}</td>
        </tr>'''

        if drivers and item['signal_count'] >= 2:
            row += f'''<tr><td colspan="9" style="padding:2px 8px 6px 24px;font-size:10px;color:#64748b;border-top:none">💡 {drivers}</td></tr>'''
        return row

    signal_rows = '\n'.join(scan_row(s) for s in signal_items)
    other_rows = '\n'.join(scan_row(s) for s in other_items[:15])

    # ═══ 模块三：宏观比价 ═══
    ratio_cards = ''
    ratio_charts_data = {}
    for key in ['copper_gold', 'oil_gold', 'industrial_agri']:
        if key not in ratios:
            continue
        r = ratios[key]
        t_color = '#10b981' if r['trend'] == 'up' else ('#ef4444' if r['trend'] == 'down' else '#94a3b8')
        t_arrow = '↑' if r['trend'] == 'up' else ('↓' if r['trend'] == 'down' else '→')
        chg_color = '#ef4444' if r['chg_20d'] > 0 else ('#10b981' if r['chg_20d'] < 0 else '#94a3b8')

        ratio_cards += f'''
        <div class="ov-card" style="border-left-color:{t_color}">
          <div class="ov-label">{r['name']}</div>
          <div class="ov-value" style="font-size:18px">{r['current']:.4f} <span style="font-size:12px;color:{t_color}">{t_arrow}</span></div>
          <div class="ov-sub">20日 <span style="color:{chg_color}">{r['chg_20d']:+.1f}%</span> · 60日分位 {r['percentile_60d']:.0f}%</div>
          <div style="margin-top:4px;font-size:10px;color:#64748b">{r['interpretation']}</div>
        </div>'''

        ratio_charts_data[key] = {
            'dates': json.dumps([fmt_date(d) for d in r['dates'][-60:]]),
            'values': json.dumps(r['values'][-60:]),
            'name': r['name'],
        }

    # ═══ 模块四：Top品种价格走势 ═══
    # 从 scan 中取 top 5 趋势品种的 symbol
    top5 = [s['symbol'] for s in scan[:5]]
    top5_names = [s['name'] for s in scan[:5]]
    top5_js = json.dumps(top5)
    top5_names_js = json.dumps(top5_names)

    # ═══ 组装 HTML ═══
    html = f'''
      <!-- 商品CTA策略环境 -->
      <div class="overview-grid">
        <div class="ov-card" style="border-left-color:{cta_color}">
          <div class="ov-label">CTA友好度</div>
          <div class="ov-value" style="color:{cta_color}">{cta_f:.1f}</div>
          <div class="ov-sub">{cta_label} · 0-100综合评分</div>
        </div>
        <div class="ov-card blue">
          <div class="ov-label">全市场平均波动率</div>
          <div class="ov-value">{avg_vol:.1f}%</div>
          <div class="ov-sub">20日年化</div>
        </div>
        <div class="ov-card green">
          <div class="ov-label">趋势品种</div>
          <div class="ov-value">{trend_count} / {total}</div>
          <div class="ov-sub">占比 {trend_pct:.1f}%</div>
        </div>
        <div class="ov-card amber">
          <div class="ov-label">三重信号品种</div>
          <div class="ov-value">{sig_count}</div>
          <div class="ov-sub">趋势+波动率放大+放量</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:{cta_color}"></span> CTA友好度 & 趋势品种占比</div>
        <div style="position:relative;height:280px"><canvas id="cta-c1"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> 全市场波动率 & 成交量比</div>
        <div style="position:relative;height:260px"><canvas id="cta-c2"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 品种趋势扫描 — 三重信号 ({len(signal_items)})</div>
        <div style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-size:11px;line-height:1.6">
            <thead><tr style="border-bottom:2px solid var(--border);color:#94a3b8;font-size:10px">
              <th style="text-align:left;padding:4px 8px">品种</th>
              <th style="text-align:left">板块</th>
              <th style="text-align:right">价格</th>
              <th style="text-align:right">20日%</th>
              <th style="text-align:right">波动率</th>
              <th style="text-align:center">波动</th>
              <th style="text-align:center">量能</th>
              <th style="text-align:center">信号</th>
              <th style="text-align:right">评分</th>
            </tr></thead>
            <tbody>{signal_rows}</tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#94a3b8"></span> 其他活跃品种（按评分排序，前15）</div>
        <details>
          <summary style="cursor:pointer;font-size:11px;color:#64748b;padding:4px 0">点击展开</summary>
          <div style="overflow-x:auto;margin-top:8px">
            <table style="width:100%;border-collapse:collapse;font-size:11px;line-height:1.6">
              <thead><tr style="border-bottom:2px solid var(--border);color:#94a3b8;font-size:10px">
                <th style="text-align:left;padding:4px 8px">品种</th>
                <th style="text-align:left">板块</th>
                <th style="text-align:right">价格</th>
                <th style="text-align:right">20日%</th>
                <th style="text-align:right">波动率</th>
                <th style="text-align:center">波动</th>
                <th style="text-align:center">量能</th>
                <th style="text-align:center">信号</th>
                <th style="text-align:right">评分</th>
              </tr></thead>
              <tbody>{other_rows}</tbody>
            </table>
          </div>
        </details>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#f59e0b"></span> 宏观比价信号</div>
        <div class="overview-grid">{ratio_cards}</div>
      </div>'''

    # 比价图表
    for key, rd in ratio_charts_data.items():
        html += f'''
      <div class="card">
        <div class="card-title"><span class="dot" style="background:#64748b"></span> {rd['name']}走势（近60日）</div>
        <div style="position:relative;height:220px"><canvas id="cta-ratio-{key}"></canvas></div>
      </div>'''

    # 指标说明
    html += f'''
      <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
        <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 指标说明</div>
        <p>① CTA友好度 = 0.40×趋势品种占比 + 0.30×波动率分位 + 0.30×成交量比，≥60偏友好，40-60中性，&lt;40偏冷淡</p>
        <p>② 趋势判定：收盘价在MA20之上且MA20斜率&gt;0.5%为多头，反之为空头</p>
        <p>③ 波动率：20日年化波动率 = std(ln收益率,20日)×√252×100</p>
        <p>④ 三重信号：同时满足有趋势+波动率放大+成交放量的品种</p>
        <p>⑤ 铜金比上行=经济扩张预期，油金比上行=通胀预期，工业品/农产品上行=需求驱动</p>
        <p>⑥ 活跃品种筛选：日均成交额&gt;500万，数据回溯120个交易日</p>
        <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare fut_daily（连续合约） · 更新：{meta['generated']} · 区间：{meta['date_range']}</p>
      </div>

      <script>
      function initCtaCharts(){{
        if(window._ctaChartsInited) return;
        window._ctaChartsInited=true;

        var ctaB={{
          responsive:true,maintainAspectRatio:false,
          interaction:{{mode:'index',intersect:false}},
          plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}}}},
          scales:{{x:{{ticks:{{maxTicksToShow:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}}}}}}
        }};

        var ctaL={env_dates_js};
        var ctaF={env_cta_js};
        var ctaT={env_trend_js};
        var ctaV={env_vol_js};
        var ctaVR={env_vr_js};

        new Chart(document.getElementById('cta-c1'),{{
          type:'line',
          data:{{labels:ctaL,datasets:[
            {{label:'CTA友好度',data:ctaF,borderColor:'#10b981',backgroundColor:'rgba(16,185,129,0.08)',fill:true,borderWidth:2,pointRadius:1.5,tension:.2,yAxisID:'y'}},
            {{label:'趋势品种占比(%)',data:ctaT,borderColor:'#f59e0b',borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:.2,yAxisID:'y1'}}
          ]}},
          options:Object.assign({{}},ctaB,{{scales:{{
            x:ctaB.scales.x,
            y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8',stepSize:20}},grid:{{color:'#f1f5f9'}},min:0,max:100,title:{{display:true,text:'CTA友好度',font:{{size:9}},color:'#94a3b8'}}}},
            y1:{{position:'right',ticks:{{font:{{size:9}},color:'#94a3b8',callback:function(v){{return v+'%'}}}},grid:{{display:false}},min:0,max:80,title:{{display:true,text:'趋势占比',font:{{size:9}},color:'#94a3b8'}}}}
          }}}})
        }});

        new Chart(document.getElementById('cta-c2'),{{
          type:'line',
          data:{{labels:ctaL,datasets:[
            {{label:'平均波动率(%)',data:ctaV,borderColor:'#8b5cf6',borderWidth:2,pointRadius:1,tension:.2,yAxisID:'y'}},
            {{label:'成交量比(MA20/MA60)',data:ctaVR,borderColor:'#3b82f6',borderWidth:1.5,borderDash:[3,2],pointRadius:0,tension:.2,yAxisID:'y1'}}
          ]}},
          options:Object.assign({{}},ctaB,{{scales:{{
            x:ctaB.scales.x,
            y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}},title:{{display:true,text:'波动率(%)',font:{{size:9}},color:'#94a3b8'}}}},
            y1:{{position:'right',ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}},title:{{display:true,text:'成交量比',font:{{size:9}},color:'#94a3b8'}}}}
          }}}})
        }});'''

    # 比价图表 JS
    for key, rd in ratio_charts_data.items():
        color = '#ef4444' if key == 'copper_gold' else ('#f59e0b' if key == 'oil_gold' else '#10b981')
        html += f'''
        new Chart(document.getElementById('cta-ratio-{key}'),{{
          type:'line',
          data:{{labels:{rd['dates']},datasets:[
            {{label:'{rd['name']}',data:{rd['values']},borderColor:'{color}',backgroundColor:'{color}11',fill:true,borderWidth:2,pointRadius:1,tension:.2}}
          ]}},
          options:ctaB
        }});'''

    html += '''
      }
      </script>'''

    return html


def inject(html_content):
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()

    start_marker = '<div class="strat-page" id="strat-cta">'
    end_marker = '<div class="strat-page" id="strat-arbitrage">'

    start_idx = index.find(start_marker)
    end_idx = index.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("❌ 找不到注入点")
        return False

    new_div = start_marker + html_content + '\n      </div>\n      '
    new_index = index[:start_idx] + new_div + index[end_idx:]

    # 激活 tab（去掉 opacity）
    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="cta" style="opacity:.4">',
        '<div class="strat-tab" data-strat="cta">'
    )

    # 添加延迟初始化（跟强势股一样的模式）
    if 'initCtaCharts' not in new_index or "data-strat==='cta'" not in new_index:
        # 在 strat-tab 点击事件里加 CTA 图表初始化
        old_ms = "if(ds==='momentum-stock')setTimeout(initMsCharts,50)"
        new_ms = "if(ds==='momentum-stock')setTimeout(initMsCharts,50);if(ds==='cta')setTimeout(initCtaCharts,50)"
        if old_ms in new_index:
            new_index = new_index.replace(old_ms, new_ms)
        else:
            # 备选：找 strat-tab click 事件
            click_marker = "document.querySelectorAll('.strat-tab').forEach"
            if click_marker in new_index and "ds==='cta'" not in new_index:
                # 在 forEach 回调末尾加
                new_index = new_index.replace(
                    "if(ds==='momentum-stock')setTimeout(initMsCharts,50)",
                    "if(ds==='momentum-stock')setTimeout(initMsCharts,50);if(ds==='cta')setTimeout(initCtaCharts,50)"
                )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_index)
    return True


def main():
    print("🔥 商品CTA策略环境注入")

    if not os.path.exists(JSON_PATH):
        print(f"❌ 数据文件不存在: {JSON_PATH}")
        return

    data = load_data()
    print(f"📖 {data['meta']['active_commodities']}个品种, {data['meta']['date_range']}")

    html = build_html(data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        latest = data['latest']
        print(f"✅ 注入成功！CTA友好度={latest['cta_friendly']:.1f} ({latest['cta_label']})")
        print(f"   趋势品种: {latest['trend_count']}/{latest['total_active']}")
        print(f"   三重信号: {latest['signal_commodities']}")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
