#!/usr/bin/env python3
import json, os, subprocess

SC_FILE = '/tmp/sc5.txt'
OUT = os.path.join(os.path.dirname(__file__), 'index.html')

def load_data():
    if not os.path.exists(SC_FILE):
        score_py = os.path.join(os.path.dirname(__file__), 'score.py')
        data_f = os.path.join(os.path.dirname(__file__), 'data/jielong_2026-06-03.json')
        subprocess.run(['/opt/homebrew/bin/python3', score_py, data_f, '20260605'],
                       stdout=open(SC_FILE,'w'), stderr=subprocess.DEVNULL)
    raw = open(SC_FILE).read()
    return json.loads(raw[raw.index('{'):])

def chan_badge(row):
    ss = row.get('small_signal') or ''
    md = row.get('mid_div') or ''
    mp = row.get('mid_pos') or ''
    if '一类买点' in ss: return '<span class="cb cb-buy">一买</span>'
    if '二类买点' in ss: return '<span class="cb cb-buy">二买</span>'
    if '三类买点' in ss: return '<span class="cb cb-buy">三买</span>'
    if '一类卖点' in ss: return '<span class="cb cb-sell">一卖</span>'
    if '二类卖点' in ss: return '<span class="cb cb-sell">二卖</span>'
    if '三类卖点' in ss: return '<span class="cb cb-sell">三卖</span>'
    if '顶背驰' in ss or md == 'top': return '<span class="cb cb-warn">顶背驰</span>'
    if '底背驰' in ss or md == 'bot': return '<span class="cb cb-bot">底背驰</span>'
    if '上方' in mp: return '<span class="cb cb-above">枢上</span>'
    if '内' in mp: return '<span class="cb cb-mid">枢内</span>'
    if '下方' in mp: return '<span class="cb cb-below">枢下</span>'
    return '<span class="cb cb-none">—</span>'

def ret_color(v):
    if v is None: return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')

QUAD_STYLE = {
    '买点': ('#e8f8e8', '#27ae60'),
    '埋伏': ('#cfe2ff', '#084298'),
    '追高': ('#fff3cd', '#e67e22'),
    '回避': ('#e2e3e5', '#666666'),
}
def quad_badge(q):
    short = (q or '').split('(')[0]
    bg, fg = QUAD_STYLE.get(short, ('#eee', '#888'))
    return f'<span class="quad" style="background:{bg};color:{fg}" title="{q}">{short}</span>'

def fmt_ret(v):
    if v is None: return '—'
    return f'+{v:.1f}%' if v > 0 else f'{v:.1f}%'

def score_bar(score, max_score):
    pct = max(0, min(100, score / max_score * 100)) if max_score else 0
    return f'<div class="sb-wrap"><div class="sb-fill" style="width:{pct:.0f}%"></div><span class="sb-val">{score:.3f}</span></div>'

def env_badge(verdict):
    color = {'顺风': '#27ae60', '中性': '#f39c12', '逆风': '#e74c3c'}.get(verdict, '#888')
    return f'<span class="env-badge" style="background:{color}">{verdict}</span>'

def recommender_stats(ranking):
    stats = {}
    for row in ranking:
        for rec in (row.get('recs') or []):
            if rec not in stats:
                stats[rec] = {'picks': [], 'rets': []}
            stats[rec]['picks'].append(row['name'])
            stats[rec]['rets'].append(row['ret20'])
    result = []
    for person, d in stats.items():
        avg = sum(d['rets']) / len(d['rets']) if d['rets'] else 0
        result.append({'person': person, 'avg': avg, 'n': len(d['picks']),
                       'picks': d['picks'], 'rets': d['rets']})
    result.sort(key=lambda x: -x['avg'])
    return result

def render(data):
    ranking = data['ranking']
    env = data['env']
    sector_mood = data['sector_mood']
    end_date = data['end_date']
    date_str = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    max_score = max(r['score'] for r in ranking) or 1

    rows_html = ''
    for r in ranking:
        rc20 = ret_color(r['ret20']); rc5 = ret_color(r['ret5'])
        qcol = 'pos' if r['momentum'] > 0 else ('neg' if r['momentum'] < 0 else '')
        rows_html += (
            f'<tr>'
            f'<td>{r["rank"]}</td>'
            f'<td><b>{r["name"]}</b></td>'
            f'<td class="mono">{r["ticker"]}</td>'
            f'<td data-val="{r["score"]:.4f}">{score_bar(r["score"], max_score)}</td>'
            f'<td data-val="{r["quality"]:.4f}" style="color:#2563eb;font-weight:600">{r["quality"]:+.2f}</td>'
            f'<td data-val="{r["momentum"]:.4f}" class="{qcol}">{r["momentum"]:+.2f}</td>'
            f'<td>{quad_badge(r["quadrant"])}</td>'
            f'<td><span class="sector-tag">{r["sector"]}</span></td>'
            f'<td class="{rc20}" data-val="{r["ret20"]}">{fmt_ret(r["ret20"])}</td>'
            f'<td class="{rc5}" data-val="{r["ret5"]}">{fmt_ret(r["ret5"])}</td>'
            f'<td>{chan_badge(r)}</td>'
            f'<td data-val="{r["consensus"]}">{"★"*r["consensus"]}</td>'
            f'</tr>\n'
        )

    consensus_stocks = sorted([r for r in ranking if r['consensus'] >= 2], key=lambda x: -x['score'])
    cards_html = ''
    for r in consensus_stocks:
        rc20 = ret_color(r['ret20']); rc5 = ret_color(r['ret5'])
        recs_str = ' '.join(f'<span class="rec-tag">{rec}</span>' for rec in (r.get('recs') or []))
        cards_html += (
            f'<div class="cons-card">'
            f'<div class="cons-head">'
            f'<span class="cons-name">{r["name"]}</span>'
            f'<span class="mono cons-ticker">{r["ticker"]}</span>'
            f'<span class="sector-tag">{r["sector"]}</span>'
            f'<span class="stars">{"★"*r["consensus"]}</span>'
            f'</div>'
            f'<div class="cons-body">'
            f'<span>20日: <b class="{rc20}">{fmt_ret(r["ret20"])}</b></span>'
            f'<span>5日: <b class="{rc5}">{fmt_ret(r["ret5"])}</b></span>'
            f'<span>{chan_badge(r)}</span>'
            f'<span>{quad_badge(r["quadrant"])}</span>'
            f'</div>'
            f'<div class="cons-recs">推荐: {recs_str}</div>'
            f'</div>\n'
        )

    sm_sorted = sorted(sector_mood, key=lambda x: -x['avg_ret20'])
    sm_labels = json.dumps([s['sector'] for s in sm_sorted], ensure_ascii=False)
    sm_vals   = json.dumps([round(s['avg_ret20'], 2) for s in sm_sorted])
    sm_colors = json.dumps(['#e74c3c' if s['avg_ret20'] >= 0 else '#2ecc71' for s in sm_sorted])

    QC = {'买点': '#27ae60', '埋伏': '#084298', '追高': '#e67e22', '回避': '#999999'}
    scatter_pts = json.dumps([
        {'x': round(r['momentum'], 3), 'y': round(r['quality'], 3),
         'name': r['name'], 'ret20': r['ret20'],
         'c': QC.get((r['quadrant'] or '').split('(')[0], '#999')}
        for r in ranking
    ], ensure_ascii=False)

    rec_stats = recommender_stats(ranking)
    rec_rows = ''
    for i, s in enumerate(rec_stats, 1):
        picks_detail = ' '.join(
            f'<span class="{ret_color(ret)}">{name}({fmt_ret(ret)})</span>'
            for name, ret in zip(s['picks'], s['rets'])
        )
        rec_rows += (
            f'<tr><td>{i}</td><td><b>{s["person"]}</b></td>'
            f'<td class="{ret_color(s["avg"])}">{fmt_ret(s["avg"])}</td>'
            f'<td>{s["n"]}</td><td class="picks-cell">{picks_detail}</td></tr>\n'
        )

    sml5 = env.get('sml5', 0); mom5 = env.get('mom5', 0); rv5 = env.get('rv5', 0)
    def factor_card(label, val, desc):
        c = ret_color(val)
        arrow = '▲' if val > 0 else ('▼' if val < 0 else '—')
        return (f'<div class="factor-card">'
                f'<div class="factor-label">{label}</div>'
                f'<div class="factor-val {c}">{arrow} {val:+.4f}</div>'
                f'<div class="factor-desc">{desc}</div></div>')
    barra_cards = (
        factor_card('小市值 SML5', sml5, '小盘股相对强弱') +
        factor_card('动量 MOM5', mom5, '近期趋势动量') +
        factor_card('反转 RV5', rv5, '短期反转信号')
    )
    verdict = env.get('verdict', '')
    coef = env.get('coef', 0)
    verdict_color = {'顺风': '#27ae60', '中性': '#f39c12', '逆风': '#e74c3c'}.get(verdict, '#888')
    verdict_desc = ('小市值风格占优，动量因子有效' if verdict == '顺风'
                    else ('小市值/动量因子中性，均衡配置' if verdict == '中性'
                          else '大盘防御占优，注意回撤风险'))

    css = '''*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f5f6f8;--card-bg:#fff;--text:#2d3142;--text-sub:#8b92a5;--border:#e8eaef;--accent:#2563eb}
body{font-family:-apple-system,'PingFang SC','Helvetica Neue','Microsoft YaHei',sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:var(--bg);color:var(--text);font-size:14px}
.header{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
h1{font-size:18px;font-weight:700}
.date-tag{font-size:12px;color:var(--text-sub);background:#fff;padding:3px 10px;border-radius:12px;border:1px solid var(--border)}
.env-badge{color:#fff;padding:3px 12px;border-radius:12px;font-size:12px;font-weight:600}
.ss-tabs{display:flex;gap:6px;margin:0 0 16px;flex-wrap:wrap}
.ss-tab{padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;background:#fff;border:1px solid #e5e7eb;transition:all .12s;color:#6b7280}
.ss-tab:hover{color:#333;border-color:#cbd5e1}
.ss-tab.active{background:#2563eb;color:#fff;border-color:#2563eb}
.ss-page{display:none}.ss-page.active{display:block}
.card{background:var(--card-bg);border-radius:10px;padding:16px;margin-bottom:16px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse}
th{background:#f8fafc;font-size:12px;font-weight:600;padding:8px 6px;border-bottom:2px solid var(--border);cursor:pointer;white-space:nowrap;user-select:none}
th:hover{background:#eef2ff;color:var(--accent)}
td{padding:7px 6px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}
tr:hover td{background:#f8fafc}
.mono{font-family:monospace;font-size:12px;color:var(--text-sub)}
.pos{color:#e74c3c}.neg{color:#2ecc71}
.sector-tag{background:#eef2ff;color:#2563eb;padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap}
.sb-wrap{display:flex;align-items:center;gap:6px;min-width:90px}
.sb-fill{height:6px;background:#2563eb;border-radius:3px;min-width:2px}
.sb-val{font-size:11px;color:var(--text-sub);white-space:nowrap}
.cb{padding:2px 7px;border-radius:10px;font-size:11px;font-weight:500}
.cb-buy{background:#fde8e8;color:#e74c3c}
.cb-sell{background:#e8f8e8;color:#2ecc71}
.cb-warn{background:#fff3cd;color:#e67e22}
.cb-bot{background:#d4edda;color:#155724}
.cb-above{background:#cfe2ff;color:#084298}
.cb-mid{background:#f0f4c3;color:#558b2f}
.cb-below{background:#e2e3e5;color:#41464b}
.cb-none{color:#bbb}
.quad{padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap;cursor:default}
.stars{color:#f39c12;font-size:13px;letter-spacing:-1px}
.note-card{background:#f0f6ff;border:1px solid #d6e4ff;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:12px;color:#3a5a8c;line-height:1.6}
.cons-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.cons-card{background:#fff;border:1px solid var(--border);border-radius:10px;padding:14px}
.cons-head{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.cons-name{font-weight:700;font-size:15px}
.cons-ticker{font-size:11px}
.cons-body{display:flex;gap:14px;font-size:12px;margin-bottom:8px;flex-wrap:wrap}
.cons-recs{font-size:11px;color:var(--text-sub)}
.rec-tag{background:#fff3e0;color:#e65100;padding:2px 7px;border-radius:10px;font-size:11px;margin-right:3px}
.picks-cell{font-size:11px;line-height:1.8}
.picks-cell span{margin-right:6px}
.factor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.factor-card{background:#fff;border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}
.factor-label{font-size:12px;color:var(--text-sub);margin-bottom:6px}
.factor-val{font-size:22px;font-weight:700;margin-bottom:4px}
.factor-desc{font-size:11px;color:var(--text-sub)}
.verdict-box{background:#fff;border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}
.verdict-main{font-size:28px;font-weight:700;margin-bottom:6px}
.verdict-sub{font-size:12px;color:var(--text-sub)}
.method-footer{background:#fbfcfe;border:1px solid var(--border);border-radius:10px;padding:18px 22px;margin-top:24px;font-size:12px;color:#5a6275;line-height:1.85}
.method-footer h3{font-size:13px;font-weight:700;color:#2d3142;margin-bottom:10px}
.method-footer h4{font-size:12px;font-weight:700;color:#2563eb;margin:12px 0 4px}
.method-footer .formula{background:#f0f4ff;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:12px;color:#1e3a8a;margin:6px 0;display:inline-block}
.method-footer ul{margin:4px 0 4px 18px}
.method-footer li{margin-bottom:3px}
.method-footer .tag{display:inline-block;background:#eef2ff;color:#2563eb;border-radius:4px;padding:1px 6px;font-weight:600;font-size:11px}
.method-footer .caveat{color:#94999f;font-style:italic;margin-top:12px;border-top:1px dashed var(--border);padding-top:10px}
@media(max-width:768px){
  .ss-tabs{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px}
  .ss-tab{white-space:nowrap;flex-shrink:0}
  .cons-grid{grid-template-columns:1fr}
  table{font-size:12px}
  td,th{padding:5px 4px}
}'''

    js = f'''const pages=document.querySelectorAll('.ss-page');
const tabs=document.querySelectorAll('.ss-tab');
let sectorInited=false,quadInited=false;
function switchTab(i){{
  pages.forEach((p,j)=>{{p.classList.toggle('active',i===j);tabs[j].classList.toggle('active',i===j)}});
  if(i===1&&!quadInited)initQuad();
  if(i===3&&!sectorInited)initSector();
}}
function initSector(){{
  sectorInited=true;
  new Chart(document.getElementById('sectorChart').getContext('2d'),{{
    type:'bar',
    data:{{labels:{sm_labels},datasets:[{{data:{sm_vals},backgroundColor:{sm_colors},borderRadius:3}}]}},
    options:{{indexAxis:'y',plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.raw.toFixed(2)+'%'}}}}}},
      scales:{{x:{{ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{size:11}}}}}}}}}}
  }});
}}
function initQuad(){{
  quadInited=true;
  const pts={scatter_pts};
  const quadLabels={{id:'ql',afterDraw(chart){{
    const{{ctx,chartArea:{{left,right,top,bottom}},scales:{{x,y}}}}=chart;
    const zx=x.getPixelForValue(0),zy=y.getPixelForValue(0);
    ctx.save();ctx.strokeStyle='#ccc';ctx.setLineDash([4,4]);
    ctx.beginPath();ctx.moveTo(zx,top);ctx.lineTo(zx,bottom);ctx.stroke();
    ctx.beginPath();ctx.moveTo(left,zy);ctx.lineTo(right,zy);ctx.stroke();
    ctx.setLineDash([]);ctx.font='bold 12px sans-serif';ctx.globalAlpha=0.5;
    ctx.fillStyle='#27ae60';ctx.textAlign='right';ctx.fillText('买点',right-8,top+18);
    ctx.fillStyle='#084298';ctx.textAlign='left';ctx.fillText('埋伏',left+8,top+18);
    ctx.fillStyle='#e67e22';ctx.textAlign='right';ctx.fillText('追高',right-8,bottom-8);
    ctx.fillStyle='#999';ctx.textAlign='left';ctx.fillText('回避',left+8,bottom-8);
    ctx.restore();
  }}}};
  new Chart(document.getElementById('quadChart').getContext('2d'),{{
    type:'scatter',
    data:{{datasets:[{{data:pts,backgroundColor:pts.map(p=>p.c),pointRadius:6,pointHoverRadius:9}}]}},
    options:{{
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>{{const p=c.raw;return p.name+'  质量'+p.y+'  动量'+p.x+'  (20日'+p.ret20+'%)'}}}}}}}},
      scales:{{x:{{title:{{display:true,text:'动量分'}}}},y:{{title:{{display:true,text:'质量分'}}}}}}
    }},
    plugins:[quadLabels]
  }});
}}
let sortDir={{}};
function sortTable(col){{
  const tb=document.querySelector('#rank-table tbody');
  const rows=Array.from(tb.rows);
  const asc=sortDir[col]=!sortDir[col];
  rows.sort((a,b)=>{{
    let av=a.cells[col].getAttribute('data-val')??a.cells[col].textContent.trim();
    let bv=b.cells[col].getAttribute('data-val')??b.cells[col].textContent.trim();
    let an=parseFloat(av),bn=parseFloat(bv);
    if(!isNaN(an)&&!isNaN(bn))return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv,'zh'):bv.localeCompare(av,'zh');
  }});
  rows.forEach(r=>tb.appendChild(r));
}}'''

    html_parts = [
        '<!DOCTYPE html>',
        '<html class="bb-dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>接龙股票池看板</title>',
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>',
        f'<style>{css}</style>',
        '''<style id="bb-dark-override">
html.bb-dark,:root.bb-dark{--bg:#0d0d0d;--card-bg:#141414;--text:#d4d8e2;--text-sub:#666;--border:#2a2a2a}
html.bb-dark body{background:#0d0d0d;color:#d4d8e2}
html.bb-dark .card,html.bb-dark .cons-card,html.bb-dark .factor-card,html.bb-dark .verdict-box,html.bb-dark .note-card,html.bb-dark .method-footer{background:#141414;border-color:#2a2a2a;color:#d4d8e2}
html.bb-dark table th{background:#1a1a1a;color:#888;border-color:#2a2a2a}
html.bb-dark table td{border-color:#1f1f1f}
html.bb-dark tr:hover td{background:#1a1a1a}
html.bb-dark .ss-tab{background:#141414;border-color:#2a2a2a;color:#888}
html.bb-dark .ss-tab.active{background:#2563eb;color:#fff}
html.bb-dark .sector-tag{background:#1a2340;color:#6ea3ff}
html.bb-dark .note-card{background:#0e1a30;border-color:#1e3a5a;color:#8ab4d8}
html.bb-dark .method-footer{background:#0f0f0f;color:#888}
html.bb-dark .method-footer h3{color:#c8cdd6}
html.bb-dark .sb-fill{background:#3b7bff}
html.bb-dark .score-bar-fill{background:#3b7bff}
</style>''',
        '''<script>(function(){
  var m;try{m=window.parent.__bbMode||"dark";}catch(e){m="dark";}
  if(m!=="light")document.documentElement.classList.add("bb-dark");
  window.addEventListener("message",function(e){
    if(!e.data||e.data.type!=="bb-theme")return;
    var mode=e.data.mode;window.__bbMode=mode;
    if(mode==="light"){document.documentElement.classList.remove("bb-dark");}
    else{document.documentElement.classList.add("bb-dark");}
    if(typeof Chart!=="undefined"){
      Chart.defaults.color=mode==="light"?"#475569":"#888";
      Chart.defaults.borderColor=mode==="light"?"#e2e8f0":"#2a2a2a";
      Object.values(Chart.instances||{}).forEach(function(c){try{c.update();}catch(_e){}});
    }
  });
})();</script>''',
        '</head><body>',
        '<div class="header">',
        '  <h1>接龙股票池看板</h1>',
        f'  <span class="date-tag">{date_str}</span>',
        f'  {env_badge(verdict)}',
        f'  <span class="date-tag" style="color:var(--text-sub)">共 {len(ranking)} 只 · Barra系数 {coef:.3f}</span>',
        '</div>',
        '<div class="ss-tabs">',
        '  <div class="ss-tab active" onclick="switchTab(0)">全排名</div>',
        '  <div class="ss-tab" onclick="switchTab(1)">象限图</div>',
        '  <div class="ss-tab" onclick="switchTab(2)">共识榜</div>',
        '  <div class="ss-tab" onclick="switchTab(3)">题材热度</div>',
        '  <div class="ss-tab" onclick="switchTab(4)">推荐人胜率</div>',
        '  <div class="ss-tab" onclick="switchTab(5)">风格环境</div>',
        '</div>',
        '<!-- Tab 0: 全排名 -->',
        '<div class="ss-page active" id="page0">',
        '<div class="note-card">',
        '<b>综合分</b> = 质量分 × 0.65 + 动量分 × 0.35。',
        '<b>质量分</b>(缠论结构/共识/量能/风格环境) 与 <b>动量分</b>(20日+5日涨幅) 正交，相关性 0.09。',
        '<b style="color:#e67e22">追高</b> = 涨多但结构弱；<b style="color:#084298">埋伏</b> = 结构优但尚未启动。',
        '</div>',
        '<div class="card" style="padding:0;overflow:auto">',
        '<table id="rank-table"><thead><tr>',
        '<th onclick="sortTable(0)">排名 ↕</th>',
        '<th onclick="sortTable(1)">股票</th>',
        '<th onclick="sortTable(2)">代码</th>',
        '<th onclick="sortTable(3)">综合分 ↕</th>',
        '<th onclick="sortTable(4)">质量分 ↕</th>',
        '<th onclick="sortTable(5)">动量分 ↕</th>',
        '<th onclick="sortTable(6)">象限</th>',
        '<th onclick="sortTable(7)">题材</th>',
        '<th onclick="sortTable(8)">20日% ↕</th>',
        '<th onclick="sortTable(9)">5日% ↕</th>',
        '<th>缠论信号</th>',
        '<th onclick="sortTable(11)">共识★ ↕</th>',
        f'</tr></thead><tbody>{rows_html}</tbody></table></div></div>',
        '<!-- Tab 1: 象限图 -->',
        '<div class="ss-page" id="page1">',
        '<div class="note-card">',
        '横轴 = 动量分，纵轴 = 质量分。',
        '<b style="color:#27ae60">右上 买点</b>(结构好+在涨)　',
        '<b style="color:#084298">左上 埋伏</b>(结构好+待启动)　',
        '<b style="color:#e67e22">右下 追高</b>(涨多+结构弱)　',
        '<b style="color:#999">左下 回避</b>',
        '</div>',
        '<div class="card"><canvas id="quadChart" height="480"></canvas></div>',
        '</div>',
        '<!-- Tab 2: 共识榜 -->',
        f'<div class="ss-page" id="page2"><div class="cons-grid">{cards_html}</div></div>',
        '<!-- Tab 3: 题材热度 -->',
        '<div class="ss-page" id="page3"><div class="card">',
        '<div style="font-size:13px;font-weight:600;margin-bottom:12px">题材20日平均涨跌幅</div>',
        '<canvas id="sectorChart" height="500"></canvas></div></div>',
        '<!-- Tab 4: 推荐人胜率 -->',
        '<div class="ss-page" id="page4"><div class="card" style="padding:0;overflow:auto"><table>',
        '<thead><tr><th>排名</th><th>推荐人</th><th>平均20日%</th><th>推荐数</th><th>个股详情</th></tr></thead>',
        f'<tbody>{rec_rows}</tbody></table></div></div>',
        '<!-- Tab 5: 风格环境 -->',
        '<div class="ss-page" id="page5">',
        f'<div class="factor-grid">{barra_cards}</div>',
        '<div class="verdict-box">',
        f'  <div class="verdict-main" style="color:{verdict_color}">{verdict}</div>',
        f'  <div class="verdict-sub">市场风格判断 · Barra环境系数 {coef:.3f}</div>',
        f'  <div class="verdict-sub" style="margin-top:8px">{verdict_desc}</div>',
        '</div></div>',
        '<!-- 常驻方法论注释 -->',
        '<div class="method-footer">',
        '<h3>打分方法论（常驻说明）</h3>',
        '<div class="formula">综合分 = 质量分 × 0.65 + 动量分 × 0.35</div>',
        '<p>质量分与动量分<b>正交分开</b>，互不混入，相关性仅 0.09。涨幅只进动量，不进质量，避免动量被重复打分。</p>',
        '<h4>质量分 = (0.45·缠论结构 + 0.25·共识度 + 0.20·量能配合 − 0.10·拥挤度) × Barra环境系数</h4>',
        '<p>四个成分先各自做截面 z-score 标准化再加权，刻意<b>不含涨幅</b>：</p>',
        '<ul>',
        '<li><span class="tag">缠论结构 45%</span> 日线中枢位置（上/内/下）+ 背驰 + 30分钟买卖点信号；只看结构位置，不含趋势方向（趋势=动量）。</li>',
        '<li><span class="tag">共识度 25%</span> 接龙里几个人独立推荐。人多 = 多位研究员同向，信号更可靠。</li>',
        '<li><span class="tag">量能配合 20%</span> 当日量 vs 近5日均量；上涨放量为正，下跌放量为负。</li>',
        '<li><span class="tag">拥挤度 −10%</span> 换手率 + 近5日振幅，越高扣分越多，反映短期追高风险。</li>',
        '</ul>',
        '<p>外层乘 <b>Barra环境系数</b>（0~1，当前由小市值/动量/反转因子滚动收益算出）：逆风时结构再好也打折，顺风时接近 1。</p>',
        '<h4>动量分 = z(20日涨幅)·0.6 + z(5日涨幅)·0.4</h4>',
        '<p>纯粹反映"最近涨了多少"，独立展示，不混入质量。</p>',
        '<h4>四象限（质量×动量，按中位数切分）</h4>',
        '<ul>',
        '<li><b style="color:#27ae60">买点</b> 质优 + 动量起 — 结构好且已启动</li>',
        '<li><b style="color:#084298">埋伏</b> 质优 + 待启动 — 结构好但还没涨</li>',
        '<li><b style="color:#e67e22">追高</b> 动量强 + 结构弱 — 涨多但缠论不支持</li>',
        '<li><b style="color:#999">回避</b> 双弱</li>',
        '</ul>',
        '<h4>缠论三级别框架</h4>',
        '<ul>',
        '<li><b>大级别（周线）</b> 定产业趋势方向 → 趋势系数</li>',
        '<li><b>中级别（日线）</b> 中枢 + 三类买卖点主战场（一买底背驰/二买回踩不破/三买突破回踩）</li>',
        '<li><b>小级别（30分钟）</b> 背驰 + 买卖点精确化</li>',
        '</ul>',
        '<p class="caveat">权重（0.45/0.25/0.20/0.10 与 0.65/0.35）是基于盘感主观拍定的，非回测最优解。基本面因子刻意不做——推荐人本身就是强基本面研究员，基本面已内嵌在选票里。</p>',
        '</div>',
        f'<script>{js}</script>',
        '</body></html>',
    ]
    return '\n'.join(html_parts)

if __name__ == '__main__':
    data = load_data()
    html = render(data)
    open(OUT, 'w', encoding='utf-8').write(html)
    size = os.path.getsize(OUT)
    print(f"index.html written: {size:,} bytes ({size//1024} KB)")
