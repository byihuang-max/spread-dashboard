#!/usr/bin/env python3
"""
把 quant_stock_data.json 注入到 FOF 看板 index.html 的策略环境适配度模块
替换原有的静态示例内容，改为按策略分类的 tab + Chart.js 图表
"""

import json, os, re

DIR = os.path.dirname(os.path.abspath(__file__))

# 读数据
with open(os.path.join(DIR, 'quant_stock_data.json'), encoding='utf-8') as f:
    data = json.load(f)

# 获取最新日期
latest_date = data.get('dates', [])[-1] if data.get('dates') else ''

# 读 HTML
html_path = os.path.join(DIR, '..', '..', 'index.html')
html_path = os.path.normpath(html_path)
with open(html_path, encoding='utf-8') as f:
    html = f.read()

# ============ 构造新的策略环境适配度模块 ============

# 压缩 JSON（去掉缩进）
data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

new_module = '''    <!-- ========== 策略环境适配度 ========== -->
    <div class="module-page" id="page-env-fit">

      <!-- 策略 tab 导航 -->
      <div class="strat-tabs">
        <div class="strat-tab active" data-strat="quant-stock">📊 宽基量化股票</div>
        <div class="strat-tab" data-strat="momentum-stock" style="opacity:0.4">🔥 强势股</div>
        <div class="strat-tab" data-strat="cta" style="opacity:0.4">📦 商品CTA</div>
        <div class="strat-tab" data-strat="convertible" style="opacity:0.4">🔄 转债</div>
        <div class="strat-tab" data-strat="arbitrage" style="opacity:0.4">⚖️ 套利</div>
      </div>

      <!-- ===== 宽基量化股票 ===== -->
      <div class="strat-page active" id="strat-quant-stock">

        <!-- 图1: 全市场成交额 -->
        <div class="card">
          <div class="card-title"><span class="dot" style="background:#e74c3c"></span> 全市场成交额时序（亿元）<span style="margin-left:auto;font-size:11px;color:#999;font-weight:400">更新: {latest_date}</span></div>
          <div style="position:relative;height:280px"><canvas id="chartAmount"></canvas></div>
        </div>

        <!-- 图2: 宽基成交额占比 -->
        <div class="card">
          <div class="card-title"><span class="dot" style="background:#3498db"></span> 宽基成交额占全A比例（%）<span style="margin-left:auto;font-size:11px;color:#999;font-weight:400">更新: {latest_date}</span></div>
          <div style="position:relative;height:320px"><canvas id="chartShare"></canvas></div>
        </div>

        <!-- 图3: 股指期货年化基差 -->
        <div class="card">
          <div class="card-title"><span class="dot" style="background:#f39c12"></span> IF/IC/IM 年化基差（%）<span style="margin-left:auto;font-size:11px;color:#999;font-weight:400">更新: {latest_date}</span></div>
          <div style="position:relative;height:280px"><canvas id="chartBasis"></canvas></div>
        </div>

        <!-- 图4: 因子超额收益 -->
        <div class="card">
          <div class="card-title"><span class="dot" style="background:#9b59b6"></span> 因子超额收益净值（vs 中证全指）<span style="margin-left:auto;font-size:11px;color:#999;font-weight:400">更新: {latest_date}</span></div>
          <div style="position:relative;height:280px"><canvas id="chartFactor"></canvas></div>
        </div>

        <!-- 计算说明 -->
        <div class="card" style="font-size:12px;color:#999;line-height:1.8">
          <div class="card-title" style="font-size:13px;color:#666"><span class="dot" style="background:#999"></span> 📐 指标说明</div>
          <p><b style="color:#555">① 全市场成交额：</b>中证全指(000985.CSI)日成交额，单位亿元，反映市场整体流动性水平</p>
          <p><b style="color:#555">② 宽基占比：</b>沪深300/中证500/1000/2000/科创50+创业板指 各自成交额占中证全指比例，观察资金主战场迁移</p>
          <p><b style="color:#555">③ 年化基差：</b>(主力合约收盘-现货指数收盘)/现货 × 12 × 100，负值=贴水（对冲成本），正值=升水</p>
          <p><b style="color:#555">④ 因子超额：</b>各因子指数相对中证全指的日度超额收益累计净值。成长=国证成长(399370)，红利=中证红利(000922)，小盘=中证2000(932000)</p>
        </div>
      </div>

      <!-- 占位策略页 -->
      <div class="strat-page" id="strat-momentum-stock">
        <div class="card" style="text-align:center;padding:60px;color:#999">
          <div style="font-size:48px;margin-bottom:16px">🔥</div>
          <div style="font-size:16px;font-weight:600;color:#666">强势股策略指标</div>
          <div style="margin-top:8px">全A+双创涨跌家数比 · WKRD动量分位数 · 信用一级拥挤度 · 变化梯度最高行业 · 涨跌停家数比</div>
          <div style="margin-top:16px;font-size:13px">模块规划中</div>
        </div>
      </div>
      <div class="strat-page" id="strat-cta">
        <div class="card" style="text-align:center;padding:60px;color:#999">
          <div style="font-size:48px;margin-bottom:16px">📦</div>
          <div style="font-size:16px;font-weight:600;color:#666">商品CTA策略指标</div>
          <div style="margin-top:8px">流动性总值 · 持仓排名 · CTA多样性 · 基本面+期限+趋势跟踪</div>
          <div style="margin-top:16px;font-size:13px">模块规划中</div>
        </div>
      </div>
      <div class="strat-page" id="strat-convertible">
        <div class="card" style="text-align:center;padding:60px;color:#999">
          <div style="font-size:48px;margin-bottom:16px">🔄</div>
          <div style="font-size:16px;font-weight:600;color:#666">转债策略指标</div>
          <div style="margin-top:8px">成交量相关性 · 换手前50%均价分位+转股溢价率 · 成交量前50%DELTA中位数 · 债底跟踪</div>
          <div style="margin-top:16px;font-size:13px">模块规划中</div>
        </div>
      </div>
      <div class="strat-page" id="strat-arbitrage">
        <div class="card" style="text-align:center;padding:60px;color:#999">
          <div style="font-size:48px;margin-bottom:16px">⚖️</div>
          <div style="font-size:16px;font-weight:600;color:#666">套利策略指标</div>
          <div style="margin-top:8px">期权隐含波动率时序 · 股指/商品期货流动性波动率</div>
          <div style="margin-top:16px;font-size:13px">模块规划中</div>
        </div>
      </div>

    </div>'''

# ============ 构造 Chart.js 脚本 ============

chart_script = '''
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
// ===== 策略 tab 切换 =====
document.querySelectorAll('.strat-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    if(tab.style.opacity==='0.4') return;
    document.querySelectorAll('.strat-tab').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.strat-page').forEach(p=>p.classList.remove('active'));
    const page = document.getElementById('strat-'+tab.dataset.strat);
    if(page) page.classList.add('active');
  });
});

// ===== 数据 =====
const QS_DATA = ''' + data_json + ''';

function fmtDate(d){ return d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8); }
function ma(arr, n){
  return arr.map((v,i)=>{
    if(i<n-1) return null;
    let s=0; for(let j=i-n+1;j<=i;j++) s+=arr[j];
    return s/n;
  });
}

const chartOpts = {
  responsive:true, maintainAspectRatio:false,
  interaction:{mode:'index',intersect:false},
  plugins:{legend:{position:'bottom',labels:{boxWidth:12,font:{size:11}}}},
  scales:{x:{ticks:{maxTicksToShow:12,font:{size:10}}}}
};

// ===== 图1: 全市场成交额 =====
(function(){
  const d = QS_DATA.total_amount;
  const labels = d.map(r=>fmtDate(r.date));
  const vals = d.map(r=>r.amount_yi);
  const ma20 = ma(vals, 20);
  new Chart(document.getElementById('chartAmount'), {
    type:'line',
    data:{
      labels,
      datasets:[
        {label:'全A成交额(亿)',data:vals,borderColor:'#e74c3c',backgroundColor:'rgba(231,76,60,0.08)',fill:true,borderWidth:1.5,pointRadius:0,tension:0.1},
        {label:'MA20',data:ma20,borderColor:'#f39c12',borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:0.1}
      ]
    },
    options:{...chartOpts,scales:{...chartOpts.scales,y:{ticks:{callback:v=>v>=10000?(v/10000).toFixed(1)+'万亿':v+'亿'}}}}
  });
})();

// ===== 图2: 宽基成交额占比 =====
(function(){
  const d = QS_DATA.index_share;
  const labels = d.map(r=>fmtDate(r.date));
  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6'];
  const names = ['沪深300','中证500','中证1000','中证2000','科创+创业板'];
  const datasets = names.map((n,i)=>({
    label:n,
    data:d.map(r=>r[n]||0),
    borderColor:colors[i],
    borderWidth:1.5,
    pointRadius:0,
    tension:0.1,
    fill:false
  }));
  new Chart(document.getElementById('chartShare'), {
    type:'line',
    data:{labels, datasets},
    options:{...chartOpts,scales:{...chartOpts.scales,y:{ticks:{callback:v=>v+'%'},min:0}}}
  });
})();

// ===== 图3: 年化基差 =====
(function(){
  const d = QS_DATA.basis;
  const labels = d.map(r=>fmtDate(r.date));
  const colors = {IF:'#e74c3c',IC:'#3498db',IM:'#2ecc71'};
  const datasets = ['IF','IC','IM'].map(k=>({
    label:k+'('+{IF:'沪深300',IC:'中证500',IM:'中证1000'}[k]+')',
    data:d.map(r=>r[k]||null),
    borderColor:colors[k],
    borderWidth:1.5,
    pointRadius:0,
    tension:0.1,
    fill:false
  }));
  new Chart(document.getElementById('chartBasis'), {
    type:'line',
    data:{labels, datasets},
    options:{
      ...chartOpts,
      scales:{
        ...chartOpts.scales,
        y:{ticks:{callback:v=>v+'%'}}
      },
      plugins:{
        ...chartOpts.plugins,
        annotation:{
          annotations:{
            zero:{type:'line',yMin:0,yMax:0,borderColor:'rgba(0,0,0,0.2)',borderWidth:1,borderDash:[3,3]}
          }
        }
      }
    }
  });
})();

// ===== 图4: 因子超额收益 =====
(function(){
  const d = QS_DATA.factor;
  const names = QS_DATA.factor_names;
  const labels = d.map(r=>fmtDate(r.date));
  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6'];
  const datasets = names.map((n,i)=>({
    label:n,
    data:d.map(r=>r[n]||null),
    borderColor:colors[i],
    borderWidth:1.5,
    pointRadius:0,
    tension:0.1,
    fill:false
  }));
  new Chart(document.getElementById('chartFactor'), {
    type:'line',
    data:{labels, datasets},
    options:{
      ...chartOpts,
      scales:{
        ...chartOpts.scales,
        y:{ticks:{callback:v=>v.toFixed(2)}}
      },
      plugins:{
        ...chartOpts.plugins,
        annotation:{
          annotations:{
            one:{type:'line',yMin:1,yMax:1,borderColor:'rgba(0,0,0,0.2)',borderWidth:1,borderDash:[3,3]}
          }
        }
      }
    }
  });
})();
</script>'''

# ============ 注入 CSS ============
strat_css = '''
/* === 策略 tab === */
.strat-tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.strat-tab{padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;background:var(--card-bg);box-shadow:0 1px 3px rgba(0,0,0,0.06);transition:all .15s;color:var(--text-sub)}
.strat-tab:hover{color:var(--text)}
.strat-tab.active{background:var(--sidebar-active);color:#fff;box-shadow:0 2px 8px rgba(231,76,60,0.3)}
.strat-page{display:none}
.strat-page.active{display:block}
'''

# 格式化模板，替换日期占位符
new_module = new_module.format(latest_date=latest_date)

# ============ 替换 HTML ============

# 1. 注入 CSS（在 </style> 前）
if '.strat-tabs' not in html:
    html = html.replace('</style>', strat_css + '</style>')

# 2. 替换策略环境适配度模块
pattern = r'    <!-- ========== 策略环境适配度 ========== -->.*?(?=    <!-- ========== 占位模块 ========== -->)'
html = re.sub(pattern, new_module + '\n\n', html, flags=re.DOTALL)

# 3. 注入 Chart.js 脚本（在 </body> 前，现有 <script> 后）
# 先移除旧的 chart script（如果有）
html = re.sub(r'<script src="https://cdn\.jsdelivr\.net/npm/chart\.js.*?</script>\s*', '', html, flags=re.DOTALL)
html = html.replace('</body></html>', chart_script + '\n</body></html>')

# 4. 更新最后更新时间
html = html.replace("v0.1 · 2026-02-22", f"v0.2 · {data['total_amount'][-1]['date'][:4]}-{data['total_amount'][-1]['date'][4:6]}-{data['total_amount'][-1]['date'][6:]}")

# 写回
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'✅ 已注入到 {html_path}')
print(f'   数据天数: {len(data["total_amount"])}')
print(f'   最新日期: {data["total_amount"][-1]["date"]}')
print(f'   HTML 大小: {len(html)/1024:.1f} KB')
