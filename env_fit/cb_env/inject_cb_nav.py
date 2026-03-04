#!/usr/bin/env python3
"""
转债产品净值注入脚本 v3
在转债环境指标的 </script> 之后插入归因分析区块
"""
import json, re
from pathlib import Path

def inject_cb_nav():
    root = Path(__file__).parent.parent.parent
    nav_file = root / 'size_spread/fund_nav/fund_nav_convertible.json'
    html_file = root / 'index.html'
    
    with open(nav_file, 'r', encoding='utf-8') as f:
        nav_data = json.load(f)
    
    fund = nav_data['fund']
    chart = fund['chart']
    
    # 构造数据
    dates = json.dumps(chart['dates'])
    fund_nav = json.dumps([round(x*100-100, 2) for x in chart['fund_nav']])
    index_nav = json.dumps([round(x*100-100, 2) for x in chart['index_nav']])
    excess = json.dumps([round(x*100, 2) for x in chart['excess']])
    
    # 基准回撤
    bench_dd = []
    peak = chart['index_nav'][0]
    for nav in chart['index_nav']:
        if nav > peak: peak = nav
        dd = (nav / peak - 1) * 100
        bench_dd.append(round(dd, 2) if dd < -2 else None)
    bench_dd_str = json.dumps(bench_dd)
    
    activity = '[' + ','.join(['null'] * len(chart['dates'])) + ']'
    
    # 归因分析区块（添加到 initCbCharts 函数中）
    nav_chart_code = f'''
  // 转债策略 × 归因分析图表
  var cbDecompEl = document.getElementById('cb-decomp-chart');
  if(cbDecompEl) {{
    var cbDecompDates = {dates};
    var cbFund = {fund_nav};
    var cbIndex = {index_nav};
    var cbExcess = {excess};
    var cbBenchDD = {bench_dd_str};
    var cbActivity = {activity};
    
    var ctx = cbDecompEl.getContext('2d');
    var h = cbDecompEl.parentElement.offsetHeight || 380;
    var gradFund = ctx.createLinearGradient(0,0,0,h);
    gradFund.addColorStop(0,'rgba(8,145,178,0.25)');
    gradFund.addColorStop(0.5,'rgba(8,145,178,0.08)');
    gradFund.addColorStop(1,'rgba(8,145,178,0)');
    var gradExcess = ctx.createLinearGradient(0,0,0,h);
    gradExcess.addColorStop(0,'rgba(245,158,11,0.18)');
    gradExcess.addColorStop(1,'rgba(245,158,11,0)');
    
    new Chart(ctx, {{
      type:'line',
      data: {{
        labels: cbDecompDates,
        datasets: [
          {{ label:'基准回撤', data:cbBenchDD, type:'bar', backgroundColor:'rgba(239,68,68,0.15)', borderColor:'transparent', yAxisID:'yHidden', order:10 }},
          {{ label:'产品收益%', data:cbFund, borderColor:'#0891b2', backgroundColor:gradFund, fill:true, tension:0.3, pointRadius:0, borderWidth:2, yAxisID:'y' }},
          {{ label:'活跃度指数', data:cbActivity, borderColor:'#6366f1', borderDash:[4,2], backgroundColor:'transparent', fill:false, tension:0.3, pointRadius:0, borderWidth:1.5, yAxisID:'y2' }},
          {{ label:'中证转债%', data:cbIndex, borderColor:'#94a3b8', borderDash:[5,3], backgroundColor:'transparent', fill:false, tension:0.3, pointRadius:0, borderWidth:1.5, yAxisID:'y' }},
          {{ label:'超额%', data:cbExcess, borderColor:'#f59e0b', backgroundColor:gradExcess, fill:true, tension:0.3, pointRadius:0, borderWidth:2, yAxisID:'y1' }}
        ]
      }},
      options: {{
        responsive:true, maintainAspectRatio:false, interaction:{{ mode:'index', intersect:false }},
        plugins: {{
          legend: {{ labels: {{ color:'#94a3b8', font:{{size:10}}, filter:function(item){{ return item.text!=='基准回撤'; }} }} }},
          tooltip: {{ enabled:false, external:function(context) {{
            var tt = document.getElementById('cb-decomp-tooltip');
            if(context.tooltip.opacity===0){{ tt.style.display='none'; return; }}
            var idx = context.tooltip.dataPoints[0].dataIndex;
            var date = cbDecompDates[idx];
            var f = cbFund[idx], ix = cbIndex[idx], ex = cbExcess[idx], ac = cbActivity[idx];
            var h = '<b>'+date+'</b><br>';
            h += '产品收益: <span style="color:#0891b2">'+(f!=null?f.toFixed(2):'--')+'%</span><br>';
            h += '中证转债: <span style="color:#94a3b8">'+(ix!=null?ix.toFixed(2):'--')+'%</span><br>';
            h += '超额: <span style="color:#f59e0b">'+(ex!=null?ex.toFixed(2):'--')+'%</span><br>';
            h += '活跃度: <span style="color:#6366f1">'+(ac!=null?ac.toFixed(1):'--')+'</span>';
            tt.innerHTML = h;
            tt.style.display='block';
            tt.style.left = context.tooltip.caretX + 12 + 'px';
            tt.style.top = context.tooltip.caretY - 20 + 'px';
          }} }}
        }},
        scales: {{
          x: {{ ticks:{{ color:'#64748b', font:{{size:9}}, maxRotation:45, maxTicksLimit:12 }} }},
          y: {{ position:'left', ticks:{{ color:'#64748b', font:{{size:9}}, callback:function(v){{return v+'%'}} }}, grid:{{color:'rgba(148,163,184,0.1)'}} }},
          y1: {{ position:'right', ticks:{{ color:'#f59e0b', font:{{size:9}}, callback:function(v){{return v+'%'}} }}, grid:{{drawOnChartArea:false}} }},
          y2: {{ display:false, min:0, max:100 }},
          yHidden: {{ display:false }}
        }}
      }}
    }});
  }}
'''
    
    nav_html = f'''
<!-- 转债策略 × 归因分析（产品净值图表） -->
<div class="card" style="padding:14px;margin-bottom:16px;position:relative">
  <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:8px">转债策略 × 归因分析</div>
  <div style="font-size:10px;color:var(--text-sub);margin-bottom:8px">产品收益 {fund['total_return']:.2f}% · 基准 {fund['index_return']:.2f}% · 超额 {fund['excess_return']:.2f}% · {fund['date_range']}</div>
  <div id="cb-decomp-tooltip" style="display:none;position:fixed;background:rgba(30,30,40,0.95);color:#e2e8f0;padding:10px 14px;border-radius:8px;font-size:11px;pointer-events:none;z-index:9999;line-height:1.6;min-width:180px"></div>
  <div style="position:relative;height:380px"><canvas id="cb-decomp-chart"></canvas></div>
  <div style="font-size:10px;color:var(--text-sub);margin-top:6px;line-height:1.5">
    基准回撤＞2%时红色背景标记 · 活跃度指数=Top50转债成交额×平均波动标准化(0-100)
  </div>
</div>
'''
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 1. 删除旧的归因分析 HTML 区块
    html = re.sub(r'<!-- 转债策略 × 归因分析.*?</div>\s*</div>', '', html, flags=re.DOTALL)
    
    # 2. 删除旧的图表初始化代码（在 initCbCharts 函数中）
    html = re.sub(r'  // 转债策略 × 归因分析图表.*?  \}\n', '', html, flags=re.DOTALL)
    
    # 3. 在分项评分卡片之后插入 HTML
    marker = '<div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:10px">📊 分项评分</div>'
    pos = html.find(marker)
    if pos == -1:
        print("❌ 找不到分项评分标题")
        return
    
    # 往后找到包含这个标题的卡片的结束 </div>
    # 先找到这个标题所在的父级 card div
    card_start = html.rfind('<div class="card"', 0, pos)
    if card_start == -1:
        print("❌ 找不到分项评分卡片开始")
        return
    
    # 从卡片开始位置匹配层级找结束
    depth = 1
    i = card_start + 17  # 跳过 '<div class="card"'
    while i < len(html) and depth > 0:
        if html[i:i+5] == '<div ':
            depth += 1
        elif html[i:i+6] == '</div>':
            depth -= 1
            if depth == 0:
                end_pos = i + 6
                break
        i += 1
    
    if depth != 0:
        print("❌ 找不到分项评分卡片结束")
        return
    
    # 在分项评分卡片之后插入
    html = html[:end_pos] + '\n\n' + nav_html + html[end_pos:]
    
    # 4. 在 initCbCharts 函数末尾插入图表代码
    func_marker = 'function initCbCharts() {'
    func_start = html.find(func_marker)
    if func_start == -1:
        print("❌ 找不到 initCbCharts 函数")
        return
    
    # 找到函数的结束 }
    func_end = html.find('\n}', func_start)
    if func_end == -1:
        print("❌ 找不到函数结束")
        return
    
    html = html[:func_end] + nav_chart_code + html[func_end:]
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 转债净值已注入")
    print(f"   {fund['date_range']}")
    print(f"   产品 {fund['total_return']:.2f}% | 基准 {fund['index_return']:.2f}% | 超额 {fund['excess_return']:.2f}%")

if __name__ == '__main__':
    inject_cb_nav()
