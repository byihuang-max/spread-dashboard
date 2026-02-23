#!/usr/bin/env python3
"""
强势股情绪指标注入脚本
读取 momentum_sentiment.json，生成 HTML/JS 代码注入到 index.html 的强势股 tab
"""

import json
import os

BASE_DIR = '/Users/apple/Desktop/gamt-dashboard'
JSON_PATH = os.path.join(BASE_DIR, 'momentum_stock/momentum_sentiment.json')
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')


def load_data():
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def fmt_date(d):
    return f"{d[4:6]}/{d[6:8]}"


def build_html(data):
    daily = data['daily']
    meta = data['meta']
    show = daily[-60:] if len(daily) > 60 else daily
    latest = show[-1]

    cycle_colors = {
        '冰点': '#3b82f6', '回暖': '#10b981', '加速': '#ef4444',
        '分歧': '#f59e0b', '退潮': '#8b5cf6', '震荡': '#94a3b8', '—': '#94a3b8'
    }

    def sentiment_color(v):
        if v >= 70: return '#ef4444'
        if v >= 50: return '#f59e0b'
        if v >= 30: return '#10b981'
        return '#3b82f6'

    dates_js = json.dumps([fmt_date(d['date']) for d in show])
    sentiment_js = json.dumps([d['sentiment'] for d in show])
    height_js = json.dumps([d['max_height'] for d in show])
    up_js = json.dumps([d['up_count'] for d in show])
    down_js = json.dumps([d['down_count'] for d in show])
    zha_js = json.dumps([d['zha_count'] for d in show])
    promo_js = json.dumps([d['promotion_rate'] for d in show])
    rate1to2_js = json.dumps([d['rate_1to2'] for d in show])
    zha_rate_js = json.dumps([d['zha_rate'] for d in show])
    ud_ratio_js = json.dumps([d['ud_ratio'] for d in show])
    seal_js = json.dumps([d['seal_quality'] for d in show])
    labels_js = json.dumps([d['cycle_label'] for d in show])
    h_norm_js = json.dumps([d['h_norm'] for d in show])
    p_norm_js = json.dumps([d['p_norm'] for d in show])
    z_norm_js = json.dumps([d['z_norm'] for d in show])
    u_norm_js = json.dumps([d['u_norm'] for d in show])
    s_norm_js = json.dumps([d['s_norm'] for d in show])

    lc = latest['cycle_label']
    lc_color = cycle_colors.get(lc, '#94a3b8')
    ls = latest['sentiment']
    ls_color = sentiment_color(ls)
    cycle_colors_js = json.dumps(cycle_colors, ensure_ascii=False)

    html = f'''
      <!-- 强势股情绪总览 -->
      <div class="overview-grid">
        <div class="ov-card" style="border-left-color:{ls_color}">
          <div class="ov-label">合成情绪指数</div>
          <div class="ov-value" style="color:{ls_color}">{ls}</div>
          <div class="ov-sub">0-100，60日滚动标准化</div>
        </div>
        <div class="ov-card" style="border-left-color:{lc_color}">
          <div class="ov-label">情绪周期</div>
          <div class="ov-value" style="color:{lc_color}">{lc}</div>
          <div class="ov-sub">基于指数水平+变化率自动判定</div>
        </div>
        <div class="ov-card blue">
          <div class="ov-label">最高连板</div>
          <div class="ov-value">{latest['max_height']}板</div>
          <div class="ov-sub">空间龙高度</div>
        </div>
        <div class="ov-card green">
          <div class="ov-label">涨停 / 跌停 / 炸板</div>
          <div class="ov-value">{latest['up_count']} / {latest['down_count']} / {latest['zha_count']}</div>
          <div class="ov-sub">涨跌停比 {latest['ud_ratio']}</div>
        </div>
        <div class="ov-card amber">
          <div class="ov-label">连板晋级率</div>
          <div class="ov-value">{latest['promotion_rate']}%</div>
          <div class="ov-sub">1进2: {latest['rate_1to2']}%</div>
        </div>
        <div class="ov-card slate">
          <div class="ov-label">炸板率 / 封板质量</div>
          <div class="ov-value">{latest['zha_rate']}% / {latest['seal_quality']}%</div>
          <div class="ov-sub">炸板率越低越好，封板质量越高越好</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:{ls_color}"></span> 合成情绪指数（0-100）</div>
        <div style="position:relative;height:280px"><canvas id="ms-c1"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:var(--accent)"></span> 子因子分解（标准化 0-100）</div>
        <div style="position:relative;height:280px"><canvas id="ms-c2"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 涨停 / 跌停 / 炸板数量</div>
        <div style="position:relative;height:260px"><canvas id="ms-c3"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#10b981"></span> 连板高度 & 晋级率</div>
        <div style="position:relative;height:260px"><canvas id="ms-c4"></canvas></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> 情绪周期标注</div>
        <div id="ms-timeline" style="display:flex;flex-wrap:wrap;gap:3px;font-size:10px;line-height:1"></div>
      </div>

      <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
        <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 指标说明</div>
        <p>① 合成情绪指数 = 0.25*空间高度 + 0.25*晋级率 + 0.20*(1-炸板率) + 0.15*涨跌停比 + 0.15*封板质量，各因子60日滚动min-max标准化</p>
        <p>② 空间高度：当日最高连板天数（limit_times最大值）</p>
        <p>③ 连板晋级率：今日涨停中昨日也涨停的占比；1进2：昨日首板今日晋级连板的占比</p>
        <p>④ 炸板率：曾触及涨停但未封住(Z) / (涨停(U)+炸板(Z))，越低越好</p>
        <p>⑤ 封板质量：涨停股中 open_times=0（一字/秒板）的占比，越高说明资金越坚决</p>
        <p>⑥ 情绪周期：冰点(&lt;20) - 回暖(突破30) - 加速(&gt;60) - 分歧(&gt;50下降) - 退潮(跌破40)</p>
        <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare limit_list_d · 更新：{meta['generated']} · 区间：{meta['date_range']}</p>
      </div>

      <script>
      (function(){{
        var msL={dates_js};
        var msS={sentiment_js};
        var msH={height_js};
        var msU={up_js};
        var msD={down_js};
        var msZ={zha_js};
        var msP={promo_js};
        var ms12={rate1to2_js};
        var msZR={zha_rate_js};
        var msUR={ud_ratio_js};
        var msSL={seal_js};
        var msCL={labels_js};
        var msHN={h_norm_js};
        var msPN={p_norm_js};
        var msZN={z_norm_js};
        var msUN={u_norm_js};
        var msSN={s_norm_js};

        var msB={{
          responsive:true,maintainAspectRatio:false,
          interaction:{{mode:'index',intersect:false}},
          plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}}}},
          scales:{{x:{{ticks:{{maxTicksToShow:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}}}}}}
        }};

        function msMA(a,n){{var r=[];for(var i=0;i<a.length;i++){{if(i<n-1){{r.push(null)}}else{{var s=0;for(var j=i-n+1;j<=i;j++)s+=a[j];r.push(s/n)}}}}return r;}}

        new Chart(document.getElementById('ms-c1'),{{
          type:'line',
          data:{{labels:msL,datasets:[
            {{label:'情绪指数',data:msS,borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,0.08)',fill:true,borderWidth:2,pointRadius:1.5,pointBackgroundColor:'#ef4444',tension:.2}},
            {{label:'MA5',data:msMA(msS,5),borderColor:'#f59e0b',borderWidth:1.2,borderDash:[4,3],pointRadius:0,tension:.2}},
            {{label:'MA20',data:msMA(msS,20),borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:.2}}
          ]}},
          options:Object.assign({{}},msB,{{scales:{{x:msB.scales.x,y:{{ticks:{{font:{{size:9}},color:'#94a3b8',stepSize:20}},grid:{{color:'#f1f5f9'}},min:0,max:100}}}}}})
        }});

        new Chart(document.getElementById('ms-c2'),{{
          type:'line',
          data:{{labels:msL,datasets:[
            {{label:'空间高度(0.25)',data:msHN,borderColor:'#ef4444',borderWidth:1.3,pointRadius:0,tension:.2}},
            {{label:'晋级率(0.25)',data:msPN,borderColor:'#2563eb',borderWidth:1.3,pointRadius:0,tension:.2}},
            {{label:'1-炸板率(0.20)',data:msZN,borderColor:'#10b981',borderWidth:1.3,pointRadius:0,tension:.2}},
            {{label:'涨跌停比(0.15)',data:msUN,borderColor:'#f59e0b',borderWidth:1.3,pointRadius:0,tension:.2}},
            {{label:'封板质量(0.15)',data:msSN,borderColor:'#8b5cf6',borderWidth:1.3,pointRadius:0,tension:.2}}
          ]}},
          options:Object.assign({{}},msB,{{scales:{{x:msB.scales.x,y:{{ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}},min:0,max:100}}}}}})
        }});

        new Chart(document.getElementById('ms-c3'),{{
          type:'bar',
          data:{{labels:msL,datasets:[
            {{label:'涨停',data:msU,backgroundColor:'rgba(239,68,68,0.7)',borderRadius:2,barPercentage:0.7}},
            {{label:'跌停',data:msD.map(function(v){{return -v}}),backgroundColor:'rgba(16,185,129,0.7)',borderRadius:2,barPercentage:0.7}},
            {{label:'炸板',data:msZ,backgroundColor:'rgba(245,158,11,0.5)',borderRadius:2,barPercentage:0.7}}
          ]}},
          options:msB
        }});

        new Chart(document.getElementById('ms-c4'),{{
          type:'bar',
          data:{{labels:msL,datasets:[
            {{label:'最高连板',data:msH,backgroundColor:'rgba(37,99,235,0.6)',borderRadius:2,barPercentage:0.5,yAxisID:'y'}},
            {{label:'晋级率(%)',data:msP,type:'line',borderColor:'#ef4444',borderWidth:1.5,pointRadius:1,tension:.2,yAxisID:'y1'}},
            {{label:'1进2(%)',data:ms12,type:'line',borderColor:'#f59e0b',borderWidth:1.2,borderDash:[3,2],pointRadius:0,tension:.2,yAxisID:'y1'}}
          ]}},
          options:Object.assign({{}},msB,{{scales:{{
            x:msB.scales.x,
            y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}},title:{{display:true,text:'连板高度',font:{{size:9}},color:'#94a3b8'}}}},
            y1:{{position:'right',ticks:{{font:{{size:9}},color:'#94a3b8',callback:function(v){{return v+'%'}}}},grid:{{display:false}},title:{{display:true,text:'晋级率',font:{{size:9}},color:'#94a3b8'}}}}
          }}}})
        }});

        var cycleColors={cycle_colors_js};
        var tl=document.getElementById('ms-timeline');
        if(tl){{msL.forEach(function(d,i){{
          var lb=msCL[i];var c=cycleColors[lb]||'#94a3b8';
          var el=document.createElement('div');
          el.style.cssText='padding:3px 6px;border-radius:3px;color:#fff;font-weight:600;background:'+c;
          el.title=d+' 情绪='+msS[i];
          el.textContent=d+' '+lb;
          tl.appendChild(el);
        }});}}
      }})();
      </script>'''
    return html


def inject(html_content):
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()

    # 精确字符串查找替换，不用正则
    start_marker = '<div class="strat-page" id="strat-momentum-stock">'
    end_marker = '<div class="strat-page" id="strat-cta">'

    start_idx = index.find(start_marker)
    end_idx = index.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("❌ 找不到注入点")
        return False

    new_div = start_marker + html_content + '\n      </div>\n      '
    new_index = index[:start_idx] + new_div + index[end_idx:]

    # 激活 tab
    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="momentum-stock" style="opacity:.4">',
        '<div class="strat-tab" data-strat="momentum-stock">'
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_index)
    return True


def main():
    print("🔥 强势股情绪指标注入")

    if not os.path.exists(JSON_PATH):
        print(f"❌ 数据文件不存在: {JSON_PATH}")
        return

    data = load_data()
    print(f"📖 {data['meta']['count']}天, {data['meta']['date_range']}")

    html = build_html(data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        print(f"✅ 注入成功！情绪={data['daily'][-1]['sentiment']} 周期={data['daily'][-1]['cycle_label']}")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
