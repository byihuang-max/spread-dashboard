#!/usr/bin/env python3
"""把风格轧差看板的数据+图表原生注入到 FOF 主看板 index.html"""
import re, os

BASE = os.path.expanduser("~/Desktop/gamt-dashboard")
src = open(os.path.join(BASE, "size_spread/风格轧差看板.html"), "r", encoding="utf-8").read()

# 用原始 index.html 的备份或当前文件
idx_path = os.path.join(BASE, "index.html")
idx = open(idx_path, "r", encoding="utf-8").read()

# 先清理之前注入的内容（如果有的话）
# 删掉之前注入的 CSS
idx = re.sub(r'/\* ── 风格轧差内嵌 ── \*/.*?(?=\n</style>)', '', idx, flags=re.DOTALL)
# 删掉之前注入的 JS script block
idx = re.sub(r'<script>\n// ════+\n// 风格轧差模块.*?</script>\n', '', idx, flags=re.DOTALL)

# 1) 从风格轧差看板提取 DATA 数组
m = re.search(r'const DATA = (\[.*?\]);', src, re.DOTALL)
if not m:
    raise RuntimeError("找不到 DATA 数组")
DATA_JS = m.group(1)

# 2) 构建风格轧差模块的 HTML
SS_HTML = '''
      <div class="strat-tabs" id="ss-tabs"></div>
      <div id="ss-content"></div>
'''

# 3) CSS
SS_CSS = '''
/* ── 风格轧差内嵌 ── */
.ss-stats{display:flex;gap:12px;margin:14px 0;flex-wrap:wrap}
.ss-stat{background:var(--card-bg);padding:12px 18px;border-radius:8px;border:1px solid var(--border);min-width:120px;text-align:center}
.ss-stat .ss-label{font-size:11px;color:var(--text-sub);margin-bottom:3px}
.ss-stat .ss-val{font-size:20px;font-weight:700}
.ss-stat .ss-val.pos{color:#e74c3c}.ss-stat .ss-val.neg{color:#27ae60}
.ss-desc{text-align:center;color:var(--text-sub);font-size:12px;margin:6px 0 14px}
.ss-chart-wrap{background:var(--card-bg);border-radius:10px;padding:16px;margin-bottom:14px;border:1px solid var(--border);position:relative;height:300px}
.ss-chart-wrap canvas{position:absolute;left:16px;top:16px;right:16px;bottom:16px}
.ss-chart-wrap.short{height:220px}
.ss-extra-info{background:var(--card-bg);border-radius:10px;padding:14px 18px;margin-bottom:14px;border:1px solid var(--border);font-size:11px;color:var(--text-sub);line-height:1.7}
.ss-extra-info strong{color:var(--text);font-weight:600}
.ss-footer{background:var(--card-bg);border-radius:10px;padding:16px 20px;margin-top:8px;border:1px solid var(--border);font-size:11px;color:var(--text-sub);line-height:1.8}
.ss-footer p{margin:2px 0}
.ss-footer .ft-title{font-size:12px;color:var(--text);font-weight:600;margin-bottom:6px}
.ss-footer b{color:var(--text);font-weight:600}
'''

# 4) JS
SS_JS = r'''
// ════════════════════════════════════════════
// 风格轧差模块（原生嵌入）
// ════════════════════════════════════════════
(function(){
const SS_DATA = ''' + DATA_JS + r''';

const ssTabsEl = document.getElementById('ss-tabs');
const ssContentEl = document.getElementById('ss-content');
let ssCharts = [];

// MA 计算
function ssMA(arr, n) {
  return arr.map((v, i) => i < n - 1 ? null : arr.slice(i - n + 1, i + 1).reduce((s, x) => s + x, 0) / n);
}

// 构建 tabs
SS_DATA.forEach((d, i) => {
  const tab = document.createElement('div');
  tab.className = 'strat-tab' + (i === 0 ? ' active' : '');
  tab.textContent = d.label;
  tab.dataset.idx = i;
  tab.addEventListener('click', () => ssSwitch(i));
  ssTabsEl.appendChild(tab);
});

function ssSwitch(idx) {
  ssTabsEl.querySelectorAll('.strat-tab').forEach((t, i) => {
    t.classList.toggle('active', i === idx);
  });
  ssRender(idx);
}

function ssRender(idx) {
  const d = SS_DATA[idx];
  const spreads = d.spreads;
  const navs = d.navs;
  const dates = d.dates;
  const last = navs[navs.length - 1];
  const cumSpread = spreads.reduce((a, b) => a + b, 0);
  const last5 = spreads.slice(-5).reduce((a, b) => a + b, 0);
  const last20 = spreads.slice(-20).reduce((a, b) => a + b, 0);
  const maxS = Math.max(...spreads);
  const minS = Math.min(...spreads);
  const avgS = spreads.reduce((a, b) => a + b, 0) / spreads.length;

  // 销毁旧图表
  ssCharts.forEach(c => c.destroy());
  ssCharts = [];

  let html = '';

  // 描述
  html += '<div class="ss-desc">' + d.desc + '</div>';

  // 统计卡片
  html += '<div class="ss-stats">';
  html += ssStatCard('最终净值', last.toFixed(4), last >= 1);
  html += ssStatCard('累计收益', (cumSpread >= 0 ? '+' : '') + cumSpread.toFixed(2) + '%', cumSpread >= 0);
  html += ssStatCard('最大轧差', '+' + maxS.toFixed(2) + '%', true);
  html += ssStatCard('最小轧差', minS.toFixed(2) + '%', false);
  html += ssStatCard('平均轧差', (avgS >= 0 ? '+' : '') + avgS.toFixed(2) + '%', avgS >= 0);
  html += '</div>';

  // 净值曲线
  html += '<div class="ss-chart-wrap"><canvas id="ss-nav-chart"></canvas></div>';

  // 每日轧差柱状图
  html += '<div class="ss-chart-wrap short"><canvas id="ss-spread-chart"></canvas></div>';

  // 特殊面板：双创等权
  if (d.isSC && d.cyb && d.kc) {
    html += '<div class="ss-chart-wrap"><canvas id="ss-sc-chart"></canvas></div>';
  }

  // 特殊面板：经济敏感
  if (d.isEco && d.cycle && d.defense) {
    html += '<div class="ss-chart-wrap"><canvas id="ss-eco-chart"></canvas></div>';
  }

  // 特殊面板：动量
  if (d.isMomentum && d.topChg && d.botChg) {
    html += '<div class="ss-chart-wrap"><canvas id="ss-mom-chart"></canvas></div>';
    if (d.topNames || d.botNames) {
      html += '<div class="ss-extra-info">';
      if (d.topNames) html += '<strong>高动量 Top6:</strong> ' + d.topNames + '<br>';
      if (d.botNames) html += '<strong>低动量 Bot6:</strong> ' + d.botNames;
      html += '</div>';
    }
  }

  // 底部注释
  html += '<div class="ss-footer">';
  html += '<p class="ft-title">📋 数据源 & 计算方式</p>';
  html += '<p><b>数据源：</b>Tushare 私有 API（sw_daily 申万行业指数 + index_daily 宽基指数）</p>';
  html += '<p><b>通用计算逻辑：</b>每日轧差 = 多头篮子等权涨跌幅 − 空头篮子等权涨跌幅；净值 = 归1复利累乘（∏(1 + 轧差/100)）；黄色虚线 = 20日移动平均线</p>';
  html += '<p style="margin-top:4px"><b>① 大小盘</b>｜中证2000(932000.CSI) − 沪深300(000300.SH)，正值 = 小盘跑赢</p>';
  html += '<p><b>② 红利vs科创</b>｜中证红利(000922.CSI) − 科创50(000688.SH)，正值 = 红利跑赢</p>';
  html += '<p><b>③ 微盘vs全A</b>｜国证微盘股(399303.SZ) − 中证全指(000985.CSI)，正值 = 微盘跑赢</p>';
  html += '<p><b>④ 双创等权</b>｜创业板指(399006.SZ) + 科创50(000688.SH) 等权平均涨跌幅，归1复利净值</p>';
  html += '<p><b>⑤ 经济敏感</b>｜周期篮子 = 有色(801050.SI) + 煤炭(801950.SI) + 钢铁(801040.SI) 等权；防御篮子 = 食品饮料(801120.SI) + 医药(801150.SI) 等权；轧差 = 周期 − 防御，正值 = 周期跑赢</p>';
  html += '<p><b>⑥ 动量轧差</b>｜申万31个一级行业，每天按过去20个交易日的滚动平均成交额排名 + 波动率排名，复合得分；Top6 = 高动量组，Bot6 = 低动量组；轧差 = 高动量 − 低动量，正值 = 高动量跑赢。成分每天动态更新。</p>';
  html += '</div>';

  ssContentEl.innerHTML = html;

  // ── 绘制净值曲线 + MA20 ──
  const navCtx = document.getElementById('ss-nav-chart');
  if (navCtx) {
    const ma20 = ssMA(navs, 20);
    ssCharts.push(new Chart(navCtx, {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {
            label: '归1净值',
            data: navs,
            borderColor: d.color || '#2563eb',
            backgroundColor: (d.color || '#2563eb') + '15',
            fill: true,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.3
          },
          {
            label: 'MA20',
            data: ma20,
            borderColor: '#f39c12',
            backgroundColor: 'transparent',
            borderDash: [6, 3],
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.3
          }
        ]
      },
      options: ssChartOpts(d.title + ' 净值（归1）', '净值', null, true)
    }));
  }

  // ── 每日轧差柱状图 ──
  const spCtx = document.getElementById('ss-spread-chart');
  if (spCtx) {
    const barLabel = d.isSC ? '等权涨跌幅%' : '轧差%';
    const colors = spreads.map(v => v >= 0 ? (d.color || '#e74c3c') + '88' : '#3498db88');
    ssCharts.push(new Chart(spCtx, {
      type: 'bar',
      data: {
        labels: dates,
        datasets: [{
          label: barLabel,
          data: spreads,
          backgroundColor: colors,
          borderRadius: 2,
          barPercentage: 0.85
        }]
      },
      options: ssChartOpts(d.isSC ? '每日等权涨跌幅(%)' : '每日轧差（' + d.l1 + ' - ' + d.l2 + '）', '%', function(v) { return v.toFixed(1) + '%'; }, false)
    }));
  }

  // ── 双创等权：创业板 vs 科创50 ──
  if (d.isSC && d.cyb && d.kc) {
    const scCtx = document.getElementById('ss-sc-chart');
    if (scCtx) {
      ssCharts.push(new Chart(scCtx, {
        type: 'line',
        data: {
          labels: dates,
          datasets: [
            {label: '创业板指%', data: d.cyb, borderColor: '#e74c3c', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false},
            {label: '科创50%', data: d.kc, borderColor: '#3498db', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false}
          ]
        },
        options: ssChartOpts('创业板指 vs 科创50 每日涨跌幅', '%', function(v) { return v.toFixed(1) + '%'; }, true)
      }));
    }
  }

  // ── 经济敏感：周期 vs 防御 ──
  if (d.isEco && d.cycle && d.defense) {
    const ecoCtx = document.getElementById('ss-eco-chart');
    if (ecoCtx) {
      ssCharts.push(new Chart(ecoCtx, {
        type: 'line',
        data: {
          labels: dates,
          datasets: [
            {label: '周期篮子%', data: d.cycle, borderColor: '#e67e22', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false},
            {label: '防御篮子%', data: d.defense, borderColor: '#27ae60', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false}
          ]
        },
        options: ssChartOpts('周期篮子 vs 防御篮子 每日涨跌幅', '%', function(v) { return v.toFixed(1) + '%'; }, true)
      }));
    }
  }

  // ── 动量：高动量 vs 低动量 ──
  if (d.isMomentum && d.topChg && d.botChg) {
    const momCtx = document.getElementById('ss-mom-chart');
    if (momCtx) {
      ssCharts.push(new Chart(momCtx, {
        type: 'line',
        data: {
          labels: dates,
          datasets: [
            {label: '高动量Top6%', data: d.topChg, borderColor: '#c0392b', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false},
            {label: '低动量Bot6%', data: d.botChg, borderColor: '#2980b9', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false}
          ]
        },
        options: ssChartOpts('高动量Top6 vs 低动量Bot6 每日涨跌幅', '%', function(v) { return v.toFixed(1) + '%'; }, true)
      }));
    }
  }
}

function ssStatCard(label, value, isPos) {
  return '<div class="ss-stat"><div class="ss-label">' + label + '</div><div class="ss-val ' + (isPos ? 'pos' : 'neg') + '">' + value + '</div></div>';
}

function ssChartOpts(titleText, yLabel, yFmt, showLegend) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {mode: 'index', intersect: false},
    plugins: {
      title: {display: true, text: titleText, font: {size: 13, family: '-apple-system,PingFang SC,sans-serif', weight: '600'}, color: '#2d3142', padding: {bottom: 8}},
      legend: {display: !!showLegend, position: 'top', labels: {usePointStyle: true, pointStyle: 'line', boxWidth: 10, font: {size: 11, family: '-apple-system,PingFang SC,sans-serif'}, padding: 12}},
      tooltip: {callbacks: {label: function(ctx) { return ctx.dataset.label + ': ' + (typeof ctx.raw === 'number' ? ctx.raw.toFixed(4) : ctx.raw); }}}
    },
    scales: {
      x: {ticks: {maxTicksToShow: 12, font: {size: 9}, color: '#94a3b8', maxRotation: 0}, grid: {display: false}},
      y: {title: {display: true, text: yLabel, font: {size: 10}, color: '#94a3b8'}, ticks: {font: {size: 9}, color: '#94a3b8', callback: yFmt || function(v) { return v.toFixed(2); }}, grid: {color: '#f1f5f9'}}
    }
  };
}

// 初始渲染第一个 tab
ssRender(0);

// 暴露 resize 函数
window.ssResizeCharts = function() {
  ssCharts.forEach(c => c.resize());
};

})();
'''

# ═══ 注入到 index.html ═══

# A) 注入 CSS（在 </style> 前）
idx = idx.replace('</style>', SS_CSS + '\n</style>')

# B) 替换风格轧差模块 HTML
old_ss = re.search(
    r'(<!-- ══ 风格轧差 ══ -->\s*<div class="module-page" id="page-style-spread">)(.*?)(</div>\s*\n\s*<!-- ══ 策略环境适配度 ══ -->)',
    idx, re.DOTALL
)
if old_ss:
    idx = idx[:old_ss.start(2)] + '\n' + SS_HTML + '\n    ' + idx[old_ss.start(3):]

# C) 删掉旧的 iframe 加载逻辑
idx = re.sub(r"if\(mod==='style-spread'\)\{[^}]*\}", '', idx)

# D) 注入 JS（在 </body> 前）
idx = idx.replace('</body></html>', '<script>\n' + SS_JS + '\n</script>\n</body></html>')

# 写回
with open(idx_path, "w", encoding="utf-8") as f:
    f.write(idx)

print("✅ 风格轧差已注入 index.html（含 MA20 + 底部注释）")
print(f"   文件大小: {len(idx):,} 字节")
