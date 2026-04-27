#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMT Dashboard v3.1 - 填充市场策略看板模块
基于v3，将module-market的空壳替换为真实数据
"""
import json, re, os, hashlib, time, requests, urllib.parse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

def api_sign(params):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    s = '&'.join([f'{k}={params[k]}' for k in sorted_keys]) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()

def fetch_market_category(type_val, end_date='2026-04-10'):
    ids_raw = '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16'
    ids_encoded = urllib.parse.quote(ids_raw, safe='')
    tm = str(int(time.time()))
    sign_params = {'app_id': APP_ID, 'end_date': end_date, 'ids': ids_encoded, 'tm': tm, 'type': str(type_val)}
    sorted_keys = sorted(sign_params.keys())
    sign_str = '&'.join([f'{k}={sign_params[k]}' for k in sorted_keys]) + APP_KEY
    sign_val = hashlib.md5(sign_str.encode()).hexdigest()
    url = f'{BASE_URL}/market/category?app_id={APP_ID}&end_date={end_date}&ids={ids_encoded}&sign={sign_val}&tm={tm}&type={type_val}'
    r = requests.get(url, timeout=15, verify=False)
    return r.json().get('data', [])

def main():
    print("📡 拉取市场策略数据...")
    annual = fetch_market_category(5)  # 年度（含5项指标）
    print(f"  年度: {len(annual)}策略")
    time.sleep(0.3)
    monthly = fetch_market_category(2)  # 月度
    print(f"  月度: {len(monthly)}策略")
    time.sleep(0.3)
    quarterly = fetch_market_category(3)  # 季度
    print(f"  季度: {len(quarterly)}策略")

    # 构建JS数据
    market_data = build_market_data(annual, monthly, quarterly)
    market_json = json.dumps(market_data, ensure_ascii=False)

    # 读取v3 HTML
    src = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(src, 'r', encoding='utf-8') as f:
        html = f.read()

    # 替换module-market的空壳内容
    market_html = build_market_html()
    old_market = re.search(
        r'(<section class="module-panel active" id="module-market">)(.*?)(</section>)',
        html, re.DOTALL
    )
    if old_market:
        html = html[:old_market.start(2)] + '\n' + market_html + '\n' + html[old_market.end(2):]
        print("✅ 替换了module-market内容")

    # 在<script>开头注入市场数据
    script_pos = html.index('<script>') + len('<script>')
    inject = f"\nconst marketData = {market_json};\n"
    html = html[:script_pos] + inject + html[script_pos:]

    # 在renderAll()之前注入市场渲染函数
    render_js = build_market_js()
    # 找到 renderAll 定义
    ra_pos = html.index('function renderAll()')
    html = html[:ra_pos] + render_js + '\n' + html[ra_pos:]

    # 在renderAll中加入renderMarket
    html = html.replace(
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); }',
        'function renderAll(){ renderStrategyFilters(); renderSortFilters(); renderCards(); renderTable(); renderMarket(); }'
    )

    # 注入额外CSS
    style_end = html.index('</style>')
    html = html[:style_end] + MARKET_CSS + html[style_end:]

    # 更新时间
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = re.sub(r'生成时间 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', f'生成时间 {now}', html)

    out = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ 已生成: {out}')
    print(f'   file://{out}')

def build_market_data(annual, monthly, quarterly):
    """构建前端需要的市场数据结构"""
    result = []
    # 按id建索引
    monthly_map = {item['id']: item for item in monthly}
    quarterly_map = {item['id']: item for item in quarterly}

    strategy_groups = {
        '股票策略': [6, 7, 8, 9, 10, 5, 4],
        '期货策略': [1, 2, 3],
        '其他策略': [11, 12, 13, 14, 15, 16],
    }

    for item in annual:
        sid = item['id']
        name = item['name']
        ret = item.get('return') or {}
        sp = item.get('sp_return_data') or {}
        md = item.get('md_return_data') or {}
        vol = item.get('vol_return_data') or {}
        cal = item.get('calmar_return_data') or {}

        # 月度收益
        m_item = monthly_map.get(sid, )
        m_ret = m_item.get('return') or {}
        # 季度收益
        q_item = quarterly_map.get(sid, {})
        q_ret = q_item.get('return') or {}

        # 确定分组
        group = '其他策略'
        for g, ids in strategy_groups.items():
            if sid in ids:
                group = g
                break

        result.append({
            'id': sid, 'name': name, 'group': group,
            'count': ret.get('count', 0),
            # 年度收益分位
            'ret_mean': ret.get('mean'), 'ret_median': ret.get('median'),
            'ret_10': ret.get('ten'), 'ret_25': ret.get('tf'),
            'ret_75': ret.get('sf'), 'ret_90': ret.get('ninety'),
            'profit_rate': ret.get('profit_rate'),
            # 夏普
            'sp_mean': sp.get('mean'), 'sp_median': sp.get('median'),
            'sp_10': sp.get('ten'), 'sp_90': sp.get('ninety'),
            # 最大回撤
            'md_mean': md.get('mean'), 'md_median': md.get('median'),
            'md_10': md.get('ten'), 'md_90': md.get('ninety'),
            # 波动率
            'vol_mean': vol.get('mean'), 'vol_median': vol.get('median'),
            'vol_10': vol.get('ten'), 'vol_90': vol.get('ninety'),
            # 卡玛
            'cal_mean': cal.get('mean'), 'cal_median': cal.get('median'),
            'cal_10': cal.get('ten'), 'cal_90': cal.get('ninety'),
            # 月度/季度
            'month_mean': (m_ret.get('mean') if isinstance(m_ret, dict) else None),
            'month_profit': (m_ret.get('profit_rate') if isinstance(m_ret, dict) else None),
            'quarter_mean': (q_ret.get('mean') if isinstance(q_ret, dict) else None),
            'quarter_profit': (q_ret.get('profit_rate') if isinstance(q_ret, dict) else None),
        })
    return result

def build_market_html():
    return '''
    <div class="card">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h1>市场策略看板</h1>
          <div class="sub">统计截至 2026-04-10 · 数据来源：火富牛策略观察 API · 年度指标分位数</div>
        </div>
      </div>

      <div class="section">
        <div class="mkt-toolbar">
          <span class="toolbar-label">策略分组</span>
          <div id="mktGroupChips"></div>
          <div class="divider"></div>
          <span class="toolbar-label">指标</span>
          <div id="mktMetricChips"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">策略指标分布总览</div>
        <div class="mkt-table-wrap">
          <table class="mkt-table" id="mktTable">
            <thead><tr>
              <th>策略</th>
              <th>样本数</th>
              <th>收益均值</th>
              <th>收益中位</th>
              <th>正收益比</th>
              <th>夏普均值</th>
              <th>夏普中位</th>
              <th>最大回撤均值</th>
              <th>波动率均值</th>
              <th>卡玛均值</th>
              <th>本月收益</th>
            </tr></thead>
            <tbody id="mktBody"></tbody>
          </table>
        </div>
      </div>

      <div class="section">
        <div class="section-title">收益分位分布图</div>
        <div class="mkt-chart-grid" id="mktChartGrid"></div>
      </div>

      <div class="section">
        <div class="section-title">指标对比雷达图</div>
        <div class="mkt-radar-grid" id="mktRadarGrid"></div>
      </div>

      <div class="section"><div class="note">说明：年度指标基于火富牛策略观察数据，分位数为各策略样本内的分布。收益分位中 10% 表示前10%分位（最优），90% 表示后10%分位（最差）。</div></div>
    </div>
'''

def build_market_js():
    return '''
let mktGroup = '全部';
let mktMetric = 'return';

function fmtPctM(v, digits) {
  if (v === null || v === undefined) return '-';
  digits = digits || 2;
  return (v * 100).toFixed(digits) + '%';
}
function fmtNum(v, digits) {
  if (v === null || v === undefined) return '-';
  return v.toFixed(digits || 2);
}

function renderMarket() {
  // Group chips
  const groups = ['全部', '股票策略', '期货策略', '其他策略'];
  const gc = document.getElementById('mktGroupChips');
  if (!gc) return;
  gc.innerHTML = groups.map(g => `<button class="btn ${g===mktGroup?'active':''}" data-g="${g}">${g}</button>`).join('');
  gc.querySelectorAll('button').forEach(b => b.onclick = () => { mktGroup = b.dataset.g; renderMarket(); });

  // Metric chips
  const metrics = [{k:'return',l:'收益分位'},{k:'sharpe',l:'夏普比率'},{k:'maxdd',l:'最大回撤'},{k:'vol',l:'波动率'},{k:'calmar',l:'卡玛比率'}];
  const mc = document.getElementById('mktMetricChips');
  mc.innerHTML = metrics.map(m => `<button class="btn ${m.k===mktMetric?'active':''}" data-m="${m.k}">${m.l}</button>`).join('');
  mc.querySelectorAll('button').forEach(b => b.onclick = () => { mktMetric = b.dataset.m; renderMarket(); });

  const data = mktGroup === '全部' ? marketData : marketData.filter(d => d.group === mktGroup);
  data.sort((a, b) => (b.ret_mean || 0) - (a.ret_mean || 0));

  // Table
  const body = document.getElementById('mktBody');
  body.innerHTML = data.map(d => {
    const retCls = (d.ret_mean || 0) > 0 ? 'pos' : (d.ret_mean || 0) < 0 ? 'neg' : '';
    const mCls = (d.month_mean || 0) > 0 ? 'pos' : (d.month_mean || 0) < 0 ? 'neg' : '';
    return `<tr>
      <td style="font-weight:600">${d.name}</td>
      <td>${d.count}</td>
      <td class="${retCls}">${fmtPctM(d.ret_mean)}</td>
      <td class="${retCls}">${fmtPctM(d.ret_median)}</td>
      <td>${fmtPctM(d.profit_rate)}</td>
      <td>${fmtNum(d.sp_mean)}</td>
      <td>${fmtNum(d.sp_median)}</td>
      <td class="neg">${fmtPctM(d.md_mean)}</td>
      <td>${fmtPctM(d.vol_mean)}</td>
      <td>${fmtNum(d.cal_mean)}</td>
      <td class="${mCls}">${fmtPctM(d.month_mean)}</td>
    </tr>`;
  }).join('');

  // Box plot charts
  renderMktCharts(data);
  // Radar charts
  renderMktRadar(data);
}

function renderMktCharts(data) {
  const grid = document.getElementById('mktChartGrid');
  if (!grid) return;
  const metricMap = {
    'return': {label:'收益率', keys:['ret_10','ret_25','ret_median','ret_75','ret_90'], fmt:v=>fmtPctM(v,1), isPct:true},
    'sharpe': {label:'夏普比率', keys:['sp_10','sp_median','sp_90'], fmt:v=>fmtNum(v,2), isPct:false},
    'maxdd':  {label:'最大回撤', keys:['md_10','md_median','md_90'], fmt:v=>fmtPctM(v,1), isPct:true},
    'vol':    {label:'波动率', keys:['vol_10','vol_median','vol_90'], fmt:v=>fmtPctM(v,1), isPct:true},
    'calmar': {label:'卡玛比率', keys:['cal_10','cal_median','cal_90'], fmt:v=>fmtNum(v,2), isPct:false},
  };
  const m = metricMap[mktMetric];
  if (!m) return;

  grid.innerHTML = data.map(d => {
    const vals = m.keys.map(k => d[k]).filter(v => v !== null && v !== undefined);
    if (vals.length === 0) return '';
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 0.01;

    function pos(v) { return ((v - min) / range * 80 + 10).toFixed(1); }

    let bars = '';
    if (m.keys.length === 5) {
      // 5-point: 10%, 25%, median, 75%, 90%
      const [p10, p25, med, p75, p90] = m.keys.map(k => d[k]);
      bars = `
        <div class="box-whisker">
          <div class="box-line" style="left:${pos(p90)}%;width:${pos(p10)-pos(p90)}%"></div>
          <div class="box-fill" style="left:${pos(p75)}%;width:${pos(p25)-pos(p75)}%"></div>
          <div class="box-median" style="left:${pos(med)}%"></div>
          <div class="box-label" style="left:${pos(p10)}%">${m.fmt(p10)}</div>
          <div class="box-label" style="left:${pos(med)}%">${m.fmt(med)}</div>
          <div class="box-label" style="left:${pos(p90)}%">${m.fmt(p90)}</div>
        </div>`;
    } else {
      // 3-point: 10%, median, 90%
      const [p10, med, p90] = m.keys.map(k => d[k]);
      bars = `
        <div class="box-whisker">
          <div class="box-line" style="left:${pos(p90)}%;width:${pos(p10)-pos(p90)}%"></div>
          <div class="box-median" style="left:${pos(med)}%"></div>
          <div class="box-label" style="left:${pos(p10)}%">${m.fmt(p10)}</div>
          <div class="box-label" style="left:${pos(med)}%">${m.fmt(med)}</div>
          <div class="box-label" style="left:${pos(p90)}%">${m.fmt(p90)}</div>
        </div>`;
    }
    return `<div class="mkt-chart-item"><div class="mkt-chart-name">${d.name}</div>${bars}</div>`;
  }).join('');
}

function renderMktRadar(data) {
  const grid = document.getElementById('mktRadarGrid');
  if (!grid) return;
  // 简化版：用水平条形图对比各策略的均值指标
  const dims = [
    {key:'ret_mean', label:'收益率', fmt:v=>fmtPctM(v,1)},
    {key:'sp_mean', label:'夏普', fmt:v=>fmtNum(v,1)},
    {key:'md_mean', label:'回撤', fmt:v=>fmtPctM(v,1), invert:true},
    {key:'vol_mean', label:'波动', fmt:v=>fmtPctM(v,1), invert:true},
    {key:'cal_mean', label:'卡玛', fmt:v=>fmtNum(v,1)},
  ];

  // 找各维度的最大值用于归一化
  const maxVals = {};
  dims.forEach(dim => {
    const vals = data.map(d => Math.abs(d[dim.key] || 0));
    maxVals[dim.key] = Math.max(...vals) || 1;
  });

  grid.innerHTML = data.slice(0, 8).map(d => {
    const bars = dims.map(dim => {
      const v = d[dim.key] || 0;
      const pct = Math.min(Math.abs(v) / maxVals[dim.key] * 100, 100);
      const color = dim.invert ? (v > 0.05 ? 'var(--up)' : 'var(--primary)') : (v > 0 ? 'var(--primary)' : 'var(--up)');
      return `<div class="radar-row">
        <span class="radar-label">${dim.label}</span>
        <div class="radar-bar-bg"><div class="radar-bar" style="width:${pct}%;background:${color}"></div></div>
        <span class="radar-val">${dim.fmt(v)}</span>
      </div>`;
    }).join('');
    return `<div class="radar-card"><div class="radar-name">${d.name}</div>${bars}</div>`;
  }).join('');
}
'''

MARKET_CSS = """
/* Market Module */
.mkt-toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.mkt-table-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:#fff; }
.mkt-table { width:100%; border-collapse:collapse; min-width:1100px; }
.mkt-table th { background:#f8fafc; color:var(--muted); font-size:11px; font-weight:600; padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
.mkt-table td { padding:9px 12px; border-bottom:1px solid var(--line-soft); font-size:12px; white-space:nowrap; }
.mkt-table tr:hover td { background:#fafbfc; }
.mkt-chart-grid { display:flex; flex-direction:column; gap:6px; }
.mkt-chart-item { display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px solid var(--line-soft); }
.mkt-chart-name { width:90px; font-size:12px; font-weight:600; color:var(--text); flex-shrink:0; }
.box-whisker { position:relative; flex:1; height:32px; }
.box-line { position:absolute; top:14px; height:4px; background:#cbd5e1; border-radius:2px; }
.box-fill { position:absolute; top:8px; height:16px; background:rgba(37,99,235,.15); border:1px solid rgba(37,99,235,.3); border-radius:4px; }
.box-median { position:absolute; top:6px; width:3px; height:20px; background:var(--primary); border-radius:2px; transform:translateX(-1px); }
.box-label { position:absolute; top:28px; font-size:9px; color:var(--muted); transform:translateX(-50%); white-space:nowrap; }
.mkt-radar-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.radar-card { background:var(--panel-soft); border:1px solid var(--line); border-radius:12px; padding:14px; }
.radar-name { font-size:13px; font-weight:700; margin-bottom:10px; color:#0f172a; }
.radar-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
.radar-label { width:32px; font-size:10px; color:var(--muted); flex-shrink:0; }
.radar-bar-bg { flex:1; height:6px; background:#e2e8f0; border-radius:3px; overflow:hidden; }
.radar-bar { height:100%; border-radius:3px; transition:width .3s; }
.radar-val { width:48px; font-size:10px; font-weight:600; text-align:right; color:var(--text); }
@media(max-width:1200px) { .mkt-radar-grid { grid-template-columns:repeat(2,1fr); } }
@media(max-width:768px) { .mkt-radar-grid { grid-template-columns:1fr; } }
"""

if __name__ == '__main__':
    main()

