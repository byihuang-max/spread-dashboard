#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAMT Dashboard v3 - 基于v2_final修复：
1. 排序按钮在"全部"时也可点击
2. 侧边栏配色优化
3. 产品点击弹出详情（净值曲线）
"""
import json, re, os, hashlib, time, requests
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ID = "hfnogbr8zceiiygdkhw"
APP_KEY = "c6e941fd6aad65ceede2d780262d11ee"
BASE_URL = "https://mallapi.huofuniu.com"

def sign(params):
    sorted_keys = sorted([k for k in params.keys() if k != 'sign'])
    s = '&'.join([f'{k}={params[k]}' for k in sorted_keys]) + APP_KEY
    return hashlib.md5(s.encode()).hexdigest()

def fetch_nav_history(reg_code, source='team'):
    """拉取单只产品从2025-01-01至今的净值序列"""
    uri = '/company/price' if source == 'team' else '/price'
    tm = int(time.time())
    params = {
        'app_id': APP_ID, 'reg_code': reg_code, 'order': '0',
        'order_by': 'price_date', 'start_date': '2025-01-01',
        'end_date': datetime.now().strftime('%Y-%m-%d'), 'tm': str(tm)
    }
    params['sign'] = sign(params)
    try:
        r = requests.get(f'{BASE_URL}{uri}', params=params, timeout=15, verify=False)
        data = r.json()
        if data.get('error_code') == 0 and data.get('data'):
            return [(n['price_date'], float(n['cumulative_nav'])) for n in data['data'] if n.get('price_date') and n.get('cumulative_nav')]
        if source == 'team':
            return fetch_nav_history(reg_code, source='platform')
    except:
        pass
    return []

# 产品code到数据源的映射
SOURCE_MAP = {
    'SZC020': 'platform', 'SSV122': 'platform',
}

def main():
    src = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v2_final.html')
    with open(src, 'r', encoding='utf-8') as f:
        html = f.read()

    # 提取所有产品code
    m_summary = re.search(r'const strategySummary = (\[.*?\]);', html, re.DOTALL)
    summary = json.loads(m_summary.group(1))
    all_codes = {}
    for s in summary:
        for item in s.get('items', []):
            code = item.get('code', '')
            name = item.get('name', '')
            if code:
                all_codes[code] = name

    # 拉取所有产品的历史净值
    print(f"📡 拉取 {len(all_codes)} 只产品历史净值...")
    nav_history = {}
    for code, name in all_codes.items():
        source = SOURCE_MAP.get(code, 'team')
        print(f"  {name} ({code}, {source})...", end=" ", flush=True)
        navs = fetch_nav_history(code, source)
        if navs:
            nav_history[code] = navs
            print(f"✅ {len(navs)}条")
        else:
            print(f"❌")
        time.sleep(0.3)

    # 组合产品
    combi_codes = {'c59639ceac9aca1f': '大方向之中波思源365'}
    for combi_id, name in combi_codes.items():
        print(f"  {name} (combi:{combi_id})...", end=" ", flush=True)
        tm = int(time.time())
        params = {
            'app_id': APP_ID, 'combi_id': combi_id, 'order': '0',
            'order_by': 'price_date', 'start_date': '2025-01-01',
            'end_date': datetime.now().strftime('%Y-%m-%d'), 'tm': str(tm)
        }
        params['sign'] = sign(params)
        try:
            r = requests.get(f'{BASE_URL}/combi/price', params=params, timeout=15, verify=False)
            data = r.json()
            if data.get('error_code') == 0 and data.get('data'):
                navs = [(n['price_date'], float(n.get('cumulative_nav') or n.get('nav'))) for n in data['data'] if n.get('price_date')]
                nav_history[combi_id] = navs
                print(f"✅ {len(navs)}条")
            else:
                print(f"❌")
        except:
            print(f"❌")
        time.sleep(0.3)

    nav_json = json.dumps(nav_history, ensure_ascii=False)
    print(f"\n💾 共拉取 {len(nav_history)} 只产品历史净值")

    # 注入修改
    # 1. 在 </script> 前注入 navHistory 数据和新的JS逻辑
    # 2. 替换CSS中的侧边栏样式
    # 3. 修复renderSortFilters

    # 找到 <script> 标签的位置
    script_start = html.index('<script>') + len('<script>')
    script_end = html.index('</script>')
    old_js = html[script_start:script_end]

    # 修复JS：移除排序按钮的disabled逻辑 + 添加产品详情弹窗
    new_js = fix_js(old_js, nav_json)
    html = html[:script_start] + new_js + html[script_end:]

    # 修复CSS：优化侧边栏 + 添加弹窗样式
    style_start = html.index('<style>') + len('<style>')
    style_end = html.index('</style>')
    old_css = html[style_start:style_end]
    new_css = fix_css(old_css)
    html = html[:style_start] + new_css + html[style_end:]

    # 添加弹窗HTML（在</div></main>之前）
    modal_html = get_modal_html()
    insert_pos = html.index('</main>')
    html = html[:insert_pos] + modal_html + html[insert_pos:]

    # 更新生成时间
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = re.sub(r'生成时间 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', f'生成时间 {now}', html)

    out = os.path.join(SCRIPT_DIR, 'GAMT_Dashboard_v3.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'\n✅ 已生成: {out}')
    print(f'   file://{out}')

def fix_js(old_js, nav_json):
    """修复JS逻辑"""
    # 1. 移除排序按钮disabled逻辑
    old_sort = """function renderSortFilters(){
  const wrap = document.getElementById('sortFilters');
  const disabled = currentStrategy === '全部';
  wrap.querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sort === currentSort && !disabled);
    btn.disabled = disabled;
    btn.style.opacity = disabled ? '0.45' : '1';
    btn.style.cursor = disabled ? 'not-allowed' : 'pointer';
    btn.onclick = disabled ? null : (() => { currentSort = btn.dataset.sort; renderAll(); });
  });
}"""
    new_sort = """function renderSortFilters(){
  const wrap = document.getElementById('sortFilters');
  wrap.querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sort === currentSort);
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
    btn.onclick = () => { currentSort = btn.dataset.sort; renderAll(); };
  });
}"""
    js = old_js.replace(old_sort, new_sort)

    # 2. 修改product-chip和表格行，添加点击事件
    # 替换renderCards中的product-chip
    js = js.replace(
        '<div class="product-chip">',
        '<div class="product-chip" onclick="showDetail(\'${item.code||item.name}\', \'${item.name}\')" style="cursor:pointer">'
    )
    # 替换renderTable中的tr
    js = js.replace(
        'body.innerHTML = filteredRows().map(item => `\n    <tr>',
        'body.innerHTML = filteredRows().map(item => `\n    <tr onclick="showDetail(\'${item.code||item.name}\', \'${item.name}\')" style="cursor:pointer">'
    )

    # 3. 注入navHistory数据和showDetail函数
    detail_js = f"""
// 历史净值数据
const navHistory = {nav_json};

function showDetail(code, name) {{
  const modal = document.getElementById('detailModal');
  const title = document.getElementById('modalTitle');
  const canvas = document.getElementById('navChart');
  const info = document.getElementById('modalInfo');
  
  title.textContent = name;
  modal.style.display = 'flex';
  
  // 找产品信息
  const product = rows.find(r => (r.code||r.name) === code) || {{}};
  const summaryItem = strategySummary.flatMap(s => s.items).find(i => (i.code||i.name) === code) || {{}};
  
  info.innerHTML = `
    <div class="modal-kpi-grid">
      <div class="modal-kpi"><div class="modal-kpi-label">策略分类</div><div class="modal-kpi-val">${{product.strategy || '-'}} · ${{product.strategy_detail || summaryItem.strategy_detail || '-'}}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">近一周</div><div class="modal-kpi-val ${{cls(product.week_return)}}">${{fmtPct(product.week_return)}}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">近一月</div><div class="modal-kpi-val ${{cls(product.month_return)}}">${{fmtPct(product.month_return)}}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">今年以来</div><div class="modal-kpi-val ${{cls(product.ytd_return)}}">${{fmtPct(product.ytd_return)}}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">最新净值日</div><div class="modal-kpi-val">${{summaryItem.latest_date || product.stat_end_used_date || '-'}}</div></div>
      <div class="modal-kpi"><div class="modal-kpi-label">累计净值</div><div class="modal-kpi-val">${{summaryItem.latest_cum_nav ? summaryItem.latest_cum_nav.toFixed(4) : '-'}}</div></div>
    </div>`;
  
  // 画净值曲线
  const navData = navHistory[code];
  if (!navData || navData.length === 0) {{
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#64748b';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('暂无历史净值数据', canvas.width/2, canvas.height/2);
    return;
  }}
  
  drawChart(canvas, navData, name);
}}

function drawChart(canvas, data, name) {{
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.parentElement.clientWidth || 800;
  const h = 320;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  
  const pad = {{top:20, right:20, bottom:40, left:60}};
  const cw = w - pad.left - pad.right;
  const ch = h - pad.top - pad.bottom;
  
  // 数据按日期排序
  const sorted = [...data].sort((a,b) => a[0].localeCompare(b[0]));
  const dates = sorted.map(d => d[0]);
  const vals = sorted.map(d => d[1]);
  const minV = Math.min(...vals) * 0.998;
  const maxV = Math.max(...vals) * 1.002;
  const range = maxV - minV || 1;
  
  // 网格线
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {{
    const y = pad.top + ch * (1 - i/4);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + cw, y); ctx.stroke();
    ctx.fillStyle = '#94a3b8'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right';
    ctx.fillText((minV + range * i/4).toFixed(4), pad.left - 8, y + 4);
  }}
  
  // X轴标签
  ctx.fillStyle = '#94a3b8'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center';
  const step = Math.max(1, Math.floor(dates.length / 6));
  for (let i = 0; i < dates.length; i += step) {{
    const x = pad.left + (i / (dates.length-1)) * cw;
    ctx.fillText(dates[i].slice(5), x, h - pad.bottom + 20);
  }}
  
  // 净值曲线
  ctx.beginPath();
  ctx.strokeStyle = '#2563eb';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  for (let i = 0; i < vals.length; i++) {{
    const x = pad.left + (i / (vals.length-1)) * cw;
    const y = pad.top + ch * (1 - (vals[i] - minV) / range);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }}
  ctx.stroke();
  
  // 渐变填充
  const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
  grad.addColorStop(0, 'rgba(37,99,235,0.12)');
  grad.addColorStop(1, 'rgba(37,99,235,0)');
  ctx.lineTo(pad.left + cw, pad.top + ch);
  ctx.lineTo(pad.left, pad.top + ch);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();
  
  // 起止标注
  ctx.fillStyle = '#1e293b'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'left';
  ctx.fillText(vals[0].toFixed(4), pad.left + 4, pad.top + ch * (1 - (vals[0]-minV)/range) - 8);
  ctx.textAlign = 'right';
  ctx.fillText(vals[vals.length-1].toFixed(4), pad.left + cw - 4, pad.top + ch * (1 - (vals[vals.length-1]-minV)/range) - 8);
}}

document.getElementById('modalClose').onclick = () => document.getElementById('detailModal').style.display = 'none';
document.getElementById('detailModal').onclick = (e) => {{ if(e.target.id === 'detailModal') e.target.style.display = 'none'; }};
"""
    js = js + detail_js
    return js

def get_modal_html():
    return '''
    <div id="detailModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,23,42,.5);backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:16px;width:90%;max-width:860px;max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.15);">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid #e2e8f0;">
          <h2 id="modalTitle" style="margin:0;font-size:20px;font-weight:800;color:#0f172a;"></h2>
          <button id="modalClose" style="border:none;background:#f1f5f9;color:#64748b;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;">✕</button>
        </div>
        <div style="padding:20px 24px;">
          <div id="modalInfo"></div>
          <div style="margin-top:16px;">
            <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px;">📈 累计净值走势</div>
            <canvas id="navChart" style="width:100%;border:1px solid #e2e8f0;border-radius:10px;"></canvas>
          </div>
        </div>
      </div>
    </div>
'''

def fix_css(old_css):
    """优化侧边栏配色 + 添加弹窗样式"""
    # 替换侧边栏相关变量
    new_css = old_css.replace(
        '--sidebar:#0c1929;',
        '--sidebar:#0f1d32;'
    ).replace(
        '--sidebar-2:#132238;',
        '--sidebar-2:#162a45;'
    )
    
    # 替换侧边栏样式
    new_css = new_css.replace(
        '.sidebar { background:linear-gradient(180deg, var(--sidebar) 0%, var(--sidebar-2) 100%); color:var(--sidebar-text); padding:28px 20px; }',
        '.sidebar { background:linear-gradient(160deg, #0f1d32 0%, #1a3352 50%, #162a45 100%); color:var(--sidebar-text); padding:28px 20px; }'
    )
    
    # 优化品牌标题
    new_css = new_css.replace(
        '.brand-top { font-size:32px; font-weight:900; letter-spacing:1px; background:linear-gradient(135deg,#60a5fa,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }',
        '.brand-top { font-size:32px; font-weight:900; letter-spacing:1px; background:linear-gradient(135deg,#38bdf8,#818cf8,#c084fc); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }'
    )
    
    # 优化模块按钮active状态
    new_css = new_css.replace(
        '.module-btn.active { background:rgba(96,165,250,.12); border-color:rgba(96,165,250,.25); }',
        '.module-btn.active { background:linear-gradient(135deg,rgba(56,189,248,.15),rgba(129,140,248,.12)); border-color:rgba(129,140,248,.3); box-shadow:0 0 12px rgba(56,189,248,.08); }'
    )
    
    # 添加弹窗KPI样式
    new_css += """
.modal-kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.modal-kpi { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px; }
.modal-kpi-label { font-size:11px; color:#64748b; margin-bottom:4px; }
.modal-kpi-val { font-size:16px; font-weight:700; color:#0f172a; }
.product-chip:hover { border-color:#94a3b8; box-shadow:0 2px 8px rgba(0,0,0,.06); }
tr:hover td { background:#f8fafc; }
"""
    return new_css

if __name__ == '__main__':
    main()

