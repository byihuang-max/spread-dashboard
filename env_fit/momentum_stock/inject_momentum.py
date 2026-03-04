#!/usr/bin/env python3
"""
强势股环境诊断面板注入脚本
读取 momentum_sentiment.json / momentum_sector.json / momentum_warning.json
生成完整的环境诊断 HTML/JS 注入到 index.html 的强势股 tab
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
INDEX_PATH = os.path.join(REPO_ROOT, 'index.html')


def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fmt_date(d):
    return f"{d[4:6]}/{d[6:8]}"


def build_html(sent_data, sector_data, warning_data, decomp_data, nav_chart_data=None):
    daily = sent_data['daily']
    meta = sent_data['meta']
    show = daily[-60:] if len(daily) > 60 else daily
    latest = show[-1]

    cycle_colors = {
        '冰点': '#3b82f6', '回暖': '#10b981', '加速': '#ef4444',
        '分歧': '#f59e0b', '退潮': '#8b5cf6', '震荡': '#94a3b8', '—': '#94a3b8'
    }
    warning_colors = {
        'RED': '#ef4444', 'YELLOW': '#f59e0b', 'WATCH': '#fbbf24',
        'GREEN': '#10b981'
    }

    def sentiment_color(v):
        if v >= 70: return '#ef4444'
        if v >= 50: return '#f59e0b'
        if v >= 30: return '#10b981'
        return '#3b82f6'

    # JS data arrays
    dates_js = json.dumps([fmt_date(d['date']) for d in show])
    sentiment_js = json.dumps([d['sentiment'] for d in show])
    height_js = json.dumps([d['max_height'] for d in show])
    up_js = json.dumps([d['up_count'] for d in show])
    down_js = json.dumps([d['down_count'] for d in show])
    zha_js = json.dumps([d['zha_count'] for d in show])
    promo_js = json.dumps([d['promotion_rate'] for d in show])
    rate1to2_js = json.dumps([d['rate_1to2'] for d in show])
    labels_js = json.dumps([d['cycle_label'] for d in show])
    h_norm_js = json.dumps([d['h_norm'] for d in show])
    p_norm_js = json.dumps([d['p_norm'] for d in show])
    z_norm_js = json.dumps([d['z_norm'] for d in show])
    u_norm_js = json.dumps([d['u_norm'] for d in show])
    s_norm_js = json.dumps([d['s_norm'] for d in show])
    cycle_colors_js = json.dumps(cycle_colors, ensure_ascii=False)

    lc = latest['cycle_label']
    lc_color = cycle_colors.get(lc, '#94a3b8')
    ls = latest['sentiment']
    ls_color = sentiment_color(ls)

    last_date = latest['date']
    date_fmt = f"{last_date[:4]}-{last_date[4:6]}-{last_date[6:8]}"

    # Warning data
    warn_latest = None
    if warning_data:
        warn_latest = warning_data.get('latest')
        if not warn_latest and warning_data.get('daily'):
            warn_latest = warning_data['daily'][-1]

    warn_level = warn_latest['warning_level'] if warn_latest else 'GREEN'
    warn_color = warning_colors.get(warn_level, '#10b981')
    narrative = warn_latest.get('narrative', '') if warn_latest else ''

    # Big cap data
    big_cap_up = latest.get('big_cap_up', 0)
    mega_cap_up = latest.get('mega_cap_up', 0)
    mega_names = latest.get('mega_cap_names', '')
    mega_display = mega_names if mega_names else '无'

    # Sector data
    sector_latest = None
    if sector_data and sector_data.get('daily'):
        sector_latest = sector_data['daily'][-1]

    # ====== Block 1: Overview ======
    # ── 预警条件链面板 ──
    # 三层嵌套逻辑：信号层（情绪退潮）→ 确认层（成交额萎缩）→ 过滤层（耐心资本托底）
    # 信号+确认+无托底 = 🔴RED | 信号+确认+有托底 = 🟡YELLOW | 仅信号 = 🟡WATCH | 无信号 = 🟢GREEN
    signal_html = ''
    if warn_latest:
        details = warn_latest.get('signal_details', [])
        sig_triggered = warn_latest.get('signal_triggered', False)
        confirmation = warn_latest.get('confirmation', False)
        vol_declining = warn_latest.get('volume_declining', False)
        vol_cv_high = warn_latest.get('volume_cv_high', False)
        has_support = warn_latest.get('has_support', False)

        # 信号层：列出具体触发项，没有则显示全绿
        if details:
            signal_items = ''.join(f'<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-size:11px">⚠️ {sig}</span>' for sig in details)
        else:
            signal_items = '<span style="color:#10b981;font-size:11px">✅ 无异常信号</span>'

        # 确认层：成交额两个子条件
        confirm_parts = []
        if vol_declining:
            confirm_parts.append('📉 成交额萎缩（MA5 < MA20 超10%）')
        if vol_cv_high:
            confirm_parts.append('📊 成交额波动大（CV > 0.15）')
        if confirm_parts:
            confirm_str = ''.join(f'<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;border-radius:4px;background:#fffbeb;color:#d97706;font-size:11px">{p}</span>' for p in confirm_parts)
        else:
            confirm_str = '<span style="color:#10b981;font-size:11px">✅ 成交额正常</span>'

        # 过滤层：耐心资本
        if has_support:
            support_str = '<span style="color:#10b981;font-size:11px">✅ 耐心资本持筹成本上移（在托底）</span>'
        else:
            support_str = '<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-size:11px">⚠️ 无耐心资本支撑</span>'

        # 综合判定 badge
        level_labels = {'RED': '🔴 高危预警', 'YELLOW': '🟡 需要警惕', 'WATCH': '🟡 持续关注', 'GREEN': '🟢 环境安全'}
        level_label = level_labels.get(warn_level, warn_level)

        signal_html = f'''
      <div class="card" style="padding:14px 18px">
        <div class="card-title" style="font-size:12px;margin-bottom:10px"><span class="dot" style="background:{warn_color}"></span> 预警条件链</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div style="display:flex;align-items:flex-start;gap:8px">
            <div style="min-width:56px;font-size:11px;font-weight:700;color:#64748b;padding-top:3px">信号层</div>
            <div style="flex:1;border-left:2px solid {"#ef4444" if sig_triggered else "#e2e8f0"};padding-left:10px">{signal_items}</div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:8px">
            <div style="min-width:56px;font-size:11px;font-weight:700;color:#64748b;padding-top:3px">确认层</div>
            <div style="flex:1;border-left:2px solid {"#f59e0b" if confirmation else "#e2e8f0"};padding-left:10px">{confirm_str}</div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:8px">
            <div style="min-width:56px;font-size:11px;font-weight:700;color:#64748b;padding-top:3px">过滤层</div>
            <div style="flex:1;border-left:2px solid {"#10b981" if has_support else "#ef4444"};padding-left:10px">{support_str}</div>
          </div>
          <div style="margin-top:4px;padding:6px 14px;border-radius:8px;background:{warn_color}15;border:1px solid {warn_color}33;color:{warn_color};font-weight:700;font-size:13px;display:inline-block;align-self:flex-start">
            {level_label}
          </div>
        </div>
        <div style="font-size:10px;color:#94a3b8;margin-top:8px;line-height:1.5">
          逻辑：情绪退潮信号 → 成交额确认 → 耐心资本过滤 · 三层都亮=红灯，有托底降为黄灯
        </div>
      </div>'''

    # Sector HTML
    sector_html = ''
    if sector_latest:
        top_sectors = sector_latest.get('top_sectors', [])[:3]
        chains = sector_latest.get('chain_analysis', [])
        sectors_all = sector_latest.get('sectors', [])

        # Top sectors cards
        if top_sectors:
            # top_sectors 是行业名列表，从 sectors_all 里查详情
            sector_lookup = {s['industry']: s for s in sectors_all}
            sector_cards = ''
            for sector_name in top_sectors:
                s = sector_lookup.get(sector_name, {})
                name = sector_name
                ud = s.get('ud_ratio', 0)
                amt = s.get('amount_yi', 0)
                avg_pct = s.get('avg_pct_chg', 0)
                bc = s.get('big_cap_up', 0)
                mc = s.get('mega_cap_up', 0)
                sector_cards += f'''<div style="flex:1;min-width:140px;background:#f8fafc;border-radius:8px;padding:10px 12px;border-left:3px solid #ef4444">
                  <div style="font-weight:700;font-size:13px;margin-bottom:4px">{name}</div>
                  <div style="font-size:11px;color:#64748b;line-height:1.8">
                    涨跌比 <b>{ud}</b> · 成交 <b>{amt:.0f}</b>亿<br>
                    均涨幅 <b style="color:{'#ef4444' if avg_pct > 0 else '#10b981'}">{avg_pct:+.2f}%</b>
                    {f' · 大市值↑{bc}' if bc else ''}{f' · 300亿+↑{mc}' if mc else ''}
                  </div>
                </div>'''
            sector_top_html = f'''
            <div class="card">
              <div class="card-title"><span class="dot" style="background:#ef4444"></span> 主攻方向</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap">{sector_cards}</div>
            </div>'''
        else:
            sector_top_html = '''
            <div class="card">
              <div class="card-title"><span class="dot" style="background:#ef4444"></span> 主攻方向</div>
              <div style="color:#94a3b8;font-size:12px">今日无明显主攻方向</div>
            </div>'''

        # Chain analysis
        chain_html = ''
        active_chains = [c for c in chains if c.get('resonance') or c.get('positions_active')]
        if active_chains:
            chain_items = ''
            for c in active_chains:
                name = c.get('chain', '')
                positions = c.get('positions_active', [])
                resonance = c.get('resonance', False)
                pos_str = ' '.join(
                    f"{'✅' if p in positions else '❌'} {p}"
                    for p in ['上游', '中游', '下游']
                )
                badge = ' <span style="background:#10b981;color:#fff;padding:1px 6px;border-radius:4px;font-size:10px">全链共振</span>' if resonance else ''
                chain_items += f'<div style="margin-bottom:4px">{name}：{pos_str}{badge}</div>'
            chain_html = f'''
            <div class="card">
              <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> 产业链传导 · {date_fmt}</div>
              <div style="font-size:12px;line-height:2">{chain_items}</div>
            </div>'''

        # Heatmap
        heatmap_html = ''
        if sectors_all:
            cells = ''
            for s in sectors_all:
                name = s.get('industry', '')
                avg_pct = s.get('avg_pct_chg', 0)
                has_zt = s.get('up_count', 0) > 0
                amt = s.get('amount_yi', 0)
                ud = s.get('ud_ratio', 0)
                # Color mapping
                if avg_pct > 2: bg = 'rgba(220,38,38,0.85)'
                elif avg_pct > 1: bg = 'rgba(239,68,68,0.6)'
                elif avg_pct > 0: bg = 'rgba(252,165,165,0.5)'
                elif avg_pct > -1: bg = 'rgba(167,243,208,0.5)'
                elif avg_pct > -2: bg = 'rgba(52,211,153,0.6)'
                else: bg = 'rgba(5,150,105,0.85)'
                tc = '#fff' if abs(avg_pct) > 1 else '#333'
                star = '⭐' if has_zt else ''
                cells += f'<div style="background:{bg};color:{tc};padding:4px 2px;border-radius:4px;font-size:10px;text-align:center;cursor:default;position:relative" title="{name} {avg_pct:+.2f}% 成交{amt:.0f}亿 涨跌比{ud}">{name[:2]}{star}</div>'
            heatmap_html = f'''
            <div class="card">
              <div class="card-title"><span class="dot" style="background:#f59e0b"></span> 行业热力图 · {date_fmt}</div>
              <div style="display:grid;grid-template-columns:repeat(8,1fr);gap:3px">{cells}</div>
              <div style="font-size:10px;color:#94a3b8;margin-top:6px">悬停查看详情 · 红涨绿跌 · ⭐有涨停</div>
            </div>'''

        sector_html = sector_top_html + chain_html + heatmap_html

    # ── 产品净值图表数据 ──
    nav_html = ''
    nav_js_data = ''
    if nav_chart_data and nav_chart_data.get('chart'):
        nc = nav_chart_data['chart']
        nav_dates = nc['dates']
        nav_fund = nc['fund_nav']
        nav_index = nc['index_nav']
        # 计算超额和基准回撤区域
        nav_excess = [round(f - idx, 6) for f, idx in zip(nav_fund, nav_index)]
        # 基准回撤高亮: running max, drawdown > 2%
        nav_dd_bar = []
        running_max = 0
        for idx_val in nav_index:
            if idx_val > running_max:
                running_max = idx_val
            in_dd = 1 if idx_val < running_max * 0.98 else 0
            nav_dd_bar.append(in_dd)
        # 计算左轴和右轴范围用的max值（给bar一个固定高度）
        nav_dates_js = json.dumps([d[5:] for d in nav_dates])  # MM-DD format
        nav_fund_js = json.dumps(nav_fund)
        nav_index_js = json.dumps(nav_index)
        nav_excess_js = json.dumps(nav_excess)
        nav_dd_js = json.dumps(nav_dd_bar)
        # 全日期用于tooltip匹配decomp (YYYYMMDD format)
        nav_dates_full_js = json.dumps([d.replace('-', '') for d in nav_dates])

        nav_js_data = f'''
        var navDates={nav_dates_js};
        var navFund={nav_fund_js};
        var navIndex={nav_index_js};
        var navExcess={nav_excess_js};
        var navDD={nav_dd_js};
        var navDatesFull={nav_dates_full_js};
        '''

        nav_html = '''
      <div class="card" style="padding:16px 20px">
        <div class="card-title"><span class="dot" style="background:#8b5cf6"></span> 产品净值 · 基准 · 超额收益</div>
        <div style="position:relative;height:360px"><canvas id="ms-nav-chart"></canvas></div>
        <div style="font-size:10px;color:#94a3b8;margin-top:6px;line-height:1.5">
          紫色=产品净值（左轴） · 灰色虚线=基准（左轴） · 橙色=累计超额（右轴） · 红色背景=基准回撤&gt;2%区域<br>
          回撤区域悬停可查看Beta/情绪/Alpha贡献
        </div>
      </div>'''

    # ── 绝对收益拆解 ──
    decomp_html = ''
    if decomp_data and decomp_data.get('daily'):
        ds = decomp_data['summary']
        dd = decomp_data['daily']
        # 只取最近120天展示
        dd_show = dd[-120:] if len(dd) > 120 else dd

        # 归因摘要卡片
        cycle_avgs = ds.get('cycle_avg_returns', {})
        cycle_items = ''
        cycle_order = ['加速', '回暖', '震荡', '分歧', '退潮', '冰点']
        cycle_card_colors = {'加速': '#ef4444', '回暖': '#10b981', '震荡': '#94a3b8', '分歧': '#f59e0b', '退潮': '#8b5cf6', '冰点': '#3b82f6'}
        for cyc in cycle_order:
            if cyc in cycle_avgs:
                avg_ret = cycle_avgs[cyc]
                color = cycle_card_colors.get(cyc, '#64748b')
                cycle_items += f'<span style="display:inline-block;margin:2px 4px;padding:3px 8px;border-radius:6px;background:{color}18;color:{color};font-size:11px;font-weight:600">{cyc} {avg_ret:+.3f}%/日</span>'

        # JS 数据
        decomp_dates_js = json.dumps([fmt_date(d['date']) for d in dd_show])
        cum_fund_js = json.dumps([round(d['cum_fund'], 2) for d in dd_show])
        cum_beta_js = json.dumps([round(d['cum_beta'], 2) for d in dd_show])
        cum_sent_js = json.dumps([round(d['cum_sentiment'], 2) for d in dd_show])
        cum_alpha_js = json.dumps([round(d['cum_alpha'], 2) for d in dd_show])
        decomp_labels_js = json.dumps([d.get('cycle_label', '—') for d in dd_show])

        decomp_html = f'''
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">
          <div style="flex:1;min-width:100px;background:#f0fdf4;border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:11px;color:#64748b">总收益</div>
            <div style="font-size:20px;font-weight:800;color:#10b981">{ds["total_return"]:+.2f}%</div>
          </div>
          <div style="flex:1;min-width:100px;background:#eff6ff;border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:11px;color:#64748b">Beta贡献</div>
            <div style="font-size:20px;font-weight:800;color:#3b82f6">{ds["beta_total"]:+.2f}%</div>
            <div style="font-size:10px;color:#94a3b8">β={ds["avg_beta"]:.2f}</div>
          </div>
          <div style="flex:1;min-width:100px;background:#fefce8;border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:11px;color:#64748b">情绪贡献</div>
            <div style="font-size:20px;font-weight:800;color:#f59e0b">{ds["sentiment_total"]:+.2f}%</div>
            <div style="font-size:10px;color:#94a3b8">占比{ds["sentiment_total"]/max(ds["total_return"],0.01)*100:.0f}%</div>
          </div>
          <div style="flex:1;min-width:100px;background:#fdf2f8;border-radius:8px;padding:10px;text-align:center">
            <div style="font-size:11px;color:#64748b">管理人Alpha</div>
            <div style="font-size:20px;font-weight:800;color:#ec4899">{ds["alpha_total"]:+.2f}%</div>
            <div style="font-size:10px;color:#94a3b8">选票+择时</div>
          </div>
        </div>
        <div style="margin-bottom:10px">
          <div style="font-size:11px;color:#64748b;margin-bottom:4px">各情绪周期日均超beta收益：</div>
          {cycle_items}
        </div>
        <div style="position:relative;height:300px"><canvas id="ms-decomp"></canvas></div>
        <div id="ms-decomp-tl" style="display:flex;gap:1px;margin-top:4px;height:12px;border-radius:3px;overflow:hidden"></div>
        <div style="font-size:10px;color:#94a3b8;margin-top:6px;line-height:1.5">
          归因逻辑：总收益 = Beta(60日滚动回归×指数收益) + 情绪环境(各周期平均超beta收益) + 管理人Alpha(残差)
        </div>'''

        # 把 decomp chart 初始化加入 JS
        # 我们需要在 initMsCharts 里加

    # ====== Build full HTML ======
    html = f'''
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 2px">
        <span style="font-size:13px;color:#888">🔥 强势股环境诊断 · 数据截至 <b style="color:#2d3142">{date_fmt}</b></span>
      </div>

      <!-- 区块一：环境总览 -->
      <div class="card" style="padding:16px 20px">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:10px">
          <div style="width:48px;height:48px;border-radius:50%;background:{warn_color};display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0;box-shadow:0 0 12px {warn_color}66">
            {"🔴" if warn_level == "RED" else "🟡" if warn_level in ("YELLOW","WATCH") else "🟢"}
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <span style="background:{lc_color};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600">{lc}</span>
              <span style="font-size:28px;font-weight:800;color:{ls_color}">{ls}</span>
              <span style="font-size:12px;color:#94a3b8">合成情绪指数</span>
            </div>
            {"<div style='font-size:12px;color:#64748b;margin-top:4px;line-height:1.5'>" + narrative + "</div>" if narrative else ""}
          </div>
        </div>
      </div>

      <div class="overview-grid">
        <div class="ov-card" style="border-left-color:#ef4444">
          <div class="ov-label">涨停 / 跌停 / 炸板</div>
          <div class="ov-value">{latest['up_count']} / {latest['down_count']} / {latest['zha_count']}</div>
          <div class="ov-sub">涨跌停比 {latest['ud_ratio']}</div>
        </div>
        <div class="ov-card" style="border-left-color:#2563eb">
          <div class="ov-label">最高连板</div>
          <div class="ov-value">{latest['max_height']}板</div>
          <div class="ov-sub">空间龙高度</div>
        </div>
        <div class="ov-card" style="border-left-color:#10b981">
          <div class="ov-label">晋级率</div>
          <div class="ov-value">{latest['promotion_rate']}%</div>
          <div class="ov-sub">1进2: {latest['rate_1to2']}%</div>
        </div>
        <div class="ov-card" style="border-left-color:#f59e0b">
          <div class="ov-label">炸板率 / 封板质量</div>
          <div class="ov-value">{latest['zha_rate']}% / {latest['seal_quality']}%</div>
          <div class="ov-sub">炸板率越低越好</div>
        </div>
        <div class="ov-card" style="border-left-color:#8b5cf6">
          <div class="ov-label">大市值涨停</div>
          <div class="ov-value">100亿+ {big_cap_up}个 / 300亿+ {mega_cap_up}个</div>
          <div class="ov-sub">机构资金参与度</div>
        </div>
        <div class="ov-card" style="border-left-color:#ec4899">
          <div class="ov-label">300亿+涨停股</div>
          <div class="ov-value" style="font-size:{12 if len(mega_display) > 10 else 16}px">{mega_display}</div>
          <div class="ov-sub">大象起舞信号</div>
        </div>
      </div>

      <!-- 区块二：预警条件链 + 产品净值 + 赚钱效应趋势 -->
      {signal_html}

      <!-- 产品净值 -->
      {nav_html}

      <!-- 绝对收益拆解 -->
      <details class="card" style="padding:16px 20px;cursor:pointer" id="ms-decomp-details">
        <summary style="font-size:13px;font-weight:700;color:#374151;list-style:none;display:flex;align-items:center;gap:6px">
          <span class="dot" style="background:#2563eb"></span> 绝对收益归因拆解（点击展开）
          <span style="font-size:10px;color:#94a3b8;font-weight:400;margin-left:auto">▶</span>
        </summary>
        <div id="ms-decomp-content" style="margin-top:12px">{decomp_html}</div>
      </details>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:{ls_color}"></span> 合成情绪指数（0-100）</div>
        <div style="position:relative;height:280px"><canvas id="ms-c1"></canvas></div>
        <div id="ms-timeline" style="display:flex;gap:1px;margin-top:4px;height:14px;border-radius:3px;overflow:hidden"></div>
      </div>

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#10b981"></span> 连板高度 & 晋级率</div>
        <div style="position:relative;height:260px"><canvas id="ms-c4"></canvas></div>
      </div>

      <details class="card" style="cursor:pointer">
        <summary class="card-title" style="list-style:none"><span class="dot" style="background:var(--accent)"></span> 子因子分解（点击展开）</summary>
        <div style="position:relative;height:280px;margin-top:8px"><canvas id="ms-c2"></canvas></div>
      </details>

      <!-- 区块三：板块结构 -->
      {sector_html}

      <div class="card">
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 涨停 / 跌停 / 炸板数量</div>
        <div style="position:relative;height:260px"><canvas id="ms-c3"></canvas></div>
      </div>

      <div class="card" style="font-size:11px;color:var(--text-sub);line-height:1.7">
        <div class="card-title" style="font-size:12px;color:#64748b"><span class="dot" style="background:#94a3b8"></span> 指标说明</div>
        <p>① 合成情绪指数 v2 = 0.20*空间高度 + 0.25*晋级率 + 0.20*(1-炸板率) + 0.10*涨跌停比 + 0.25*封板质量，120日分位数排名 + 交互修正</p>
        <p>② 封板质量 = (100亿+涨停 + 2×300亿+涨停) / 总涨停数，反映大资金参与度（旧版为一字板占比）</p>
        <p>③ 交互修正：连板高但全小票→打折 · 晋级率高但炸板也高→打折</p>
        <p>④ 情绪周期：冰点(&lt;20) → 回暖(突破30) → 加速(&gt;60) → 分歧(&gt;50下降) → 退潮(跌破40)</p>
        <p>⑤ 预警信号灯：GREEN=安全 · WATCH=关注 · YELLOW=警惕 · RED=高危</p>
        <p style="margin-top:6px;color:#94a3b8">数据来源：Tushare · 更新：{meta['generated']} · 区间：{meta['date_range']}</p>
      </div>

      <script>
      var _msInited=false;function initMsCharts(){{if(_msInited)return;_msInited=true;
        var msL={dates_js};
        var msS={sentiment_js};
        var msH={height_js};
        var msU={up_js};
        var msD={down_js};
        var msZ={zha_js};
        var msP={promo_js};
        var ms12={rate1to2_js};
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

        function msMA(a,n){{var r=[];for(var i=0;i<a.length;i++){{if(i<n-1)r.push(null);else{{var s=0;for(var j=i-n+1;j<=i;j++)s+=a[j];r.push(s/n)}}}}return r;}}

        new Chart(document.getElementById('ms-c1'),{{
          type:'line',
          data:{{labels:msL,datasets:[
            {{label:'情绪指数',data:msS,borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,0.08)',fill:true,borderWidth:2,pointRadius:1.5,pointBackgroundColor:'#ef4444',tension:.2}},
            {{label:'MA5',data:msMA(msS,5),borderColor:'#f59e0b',borderWidth:1.2,borderDash:[4,3],pointRadius:0,tension:.2}},
            {{label:'MA20',data:msMA(msS,20),borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:.2}}
          ]}},
          options:Object.assign({{}},msB,{{scales:{{x:msB.scales.x,y:{{ticks:{{font:{{size:9}},color:'#94a3b8',stepSize:20}},grid:{{color:'#f1f5f9'}},min:0,max:100}}}}}})
        }});

        // Cycle timeline
        var cycleColors={cycle_colors_js};
        var tl=document.getElementById('ms-timeline');
        if(tl){{msL.forEach(function(d,i){{
          var lb=msCL[i];var c=cycleColors[lb]||'#94a3b8';
          var el=document.createElement('div');
          el.style.cssText='flex:1;background:'+c+'88;height:100%';
          el.title=d+' '+lb+' 情绪='+msS[i];
          tl.appendChild(el);
        }});}}

        // Sub-factor chart (lazy init on details open)
        var c2Init=false;
        var det=document.querySelector('details:has(#ms-c2)');
        if(det){{det.addEventListener('toggle',function(){{
          if(!det.open||c2Init)return;c2Init=true;
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
        }});}}

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
        // ── 产品净值图表 ──
        {nav_js_data if nav_js_data else ''}
        {f"""
        // decomp lookup for tooltip
        var decompLookup={{}};
        {f"var _dcDaily={json.dumps([dict(date=d['date'],cum_beta=round(d.get('cum_beta',0),2),cum_sentiment=round(d.get('cum_sentiment',0),2),cum_alpha=round(d.get('cum_alpha',0),2),cycle_label=d.get('cycle_label','—'),beta=round(d.get('beta',0),4),sentiment=round(d.get('sentiment',0) if d.get('sentiment') is not None else 0,4)) for d in decomp_data['daily']])};" if decomp_data and decomp_data.get('daily') else "var _dcDaily=[];"}
        _dcDaily.forEach(function(d){{ decompLookup[d.date]=d; }});
        """ if nav_chart_data and nav_chart_data.get('chart') else ''}
        {f"""
        (function(){{
          var el=document.getElementById('ms-nav-chart');
          if(!el)return;
          // bar dataset for drawdown highlight: use left y-axis max
          var allVals=navFund.concat(navIndex);
          var yMax=Math.max.apply(null,allVals)*1.05;
          var ddData=navDD.map(function(v){{return v?yMax:0}});

          new Chart(el,{{
            type:'line',
            data:{{labels:navDates,datasets:[
              {{label:'基准回撤区域',data:ddData,type:'bar',backgroundColor:'rgba(239,68,68,0.08)',borderWidth:0,barPercentage:1.0,categoryPercentage:1.0,yAxisID:'y',order:4}},
              {{label:'产品净值',data:navFund,borderColor:'#8b5cf6',borderWidth:2,pointRadius:0,tension:.2,fill:false,yAxisID:'y',order:2}},
              {{label:'基准',data:navIndex,borderColor:'#94a3b8',borderWidth:1.5,borderDash:[5,3],pointRadius:0,tension:.2,fill:false,yAxisID:'y',order:3}},
              {{label:'累计超额',data:navExcess,borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,0.1)',borderWidth:1.5,pointRadius:0,tension:.2,fill:true,yAxisID:'y1',order:1}}
            ]}},
            options:{{
              responsive:true,maintainAspectRatio:false,
              interaction:{{mode:'index',intersect:false}},
              plugins:{{
                legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12,filter:function(item){{return item.text!=='基准回撤区域'}}}}}},
                tooltip:{{
                  callbacks:{{
                    afterBody:function(ctx){{
                      var i=ctx[0].dataIndex;
                      if(!navDD[i])return '';
                      var dt=navDatesFull[i];
                      var dc=decompLookup[dt];
                      if(!dc)return '\\n📉 基准回撤区域';
                      return '\\n📉 基准回撤区域'
                        +'\\nBeta贡献: '+dc.cum_beta.toFixed(2)+'%'
                        +'\\n情绪贡献: '+dc.cum_sentiment.toFixed(2)+'%'
                        +'\\n管理人Alpha: '+dc.cum_alpha.toFixed(2)+'%'
                        +'\\n情绪周期: '+dc.cycle_label;
                    }}
                  }}
                }}
              }},
              scales:{{
                x:{{ticks:{{maxTicksToShow:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},
                y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8',callback:function(v){{return v.toFixed(2)}}}},grid:{{color:'#f1f5f9'}},title:{{display:true,text:'净值',font:{{size:9}},color:'#94a3b8'}}}},
                y1:{{position:'right',ticks:{{font:{{size:9}},color:'#f59e0b',callback:function(v){{return (v*100).toFixed(1)+'%'}}}},grid:{{display:false}},title:{{display:true,text:'累计超额',font:{{size:9}},color:'#f59e0b'}}}}
              }}
            }}
          }});
        }})();
        """ if nav_chart_data and nav_chart_data.get('chart') else ''}

        // ── 收益拆解（懒加载） ──
        {f"""
        var dcL={decomp_dates_js};
        var dcF={cum_fund_js};
        var dcB={cum_beta_js};
        var dcS={cum_sent_js};
        var dcA={cum_alpha_js};
        var dcCL={decomp_labels_js};

        var dcInit=false;
        var dcDet=document.getElementById('ms-decomp-details');
        if(dcDet){{dcDet.addEventListener('toggle',function(){{
          if(!dcDet.open||dcInit)return;dcInit=true;
          // 更新箭头
          var arrow=dcDet.querySelector('summary span:last-child');
          if(arrow)arrow.textContent='▼';

          var dcEl=document.getElementById('ms-decomp');
          if(dcEl){{new Chart(dcEl,{{
            type:'line',
            data:{{labels:dcL,datasets:[
              {{label:'总收益',data:dcF,borderColor:'#1e293b',borderWidth:2.5,pointRadius:0,tension:.2,fill:false}},
              {{label:'Beta贡献',data:dcB,borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,0.12)',borderWidth:1.5,pointRadius:0,tension:.2,fill:true}},
              {{label:'情绪贡献',data:dcS,borderColor:'#f59e0b',backgroundColor:'rgba(245,158,11,0.12)',borderWidth:1.5,pointRadius:0,tension:.2,fill:true}},
              {{label:'管理人Alpha',data:dcA,borderColor:'#ec4899',backgroundColor:'rgba(236,72,153,0.12)',borderWidth:1.5,pointRadius:0,tension:.2,fill:true}}
            ]}},
            options:Object.assign({{}},msB,{{scales:{{x:msB.scales.x,y:{{ticks:{{font:{{size:9}},color:'#94a3b8',callback:function(v){{return v+'%'}}}},grid:{{color:'#f1f5f9'}}}}}}}})
          }})}}

          // 收益拆解周期色带
          var dcTl=document.getElementById('ms-decomp-tl');
          if(dcTl){{dcL.forEach(function(d,i){{
            var lb=dcCL[i];var c=cycleColors[lb]||'#94a3b8';
            var el=document.createElement('div');
            el.style.cssText='flex:1;background:'+c+'88;height:100%';
            el.title=d+' '+lb;
            dcTl.appendChild(el);
          }})}}
        }});}}
        """ if decomp_data and decomp_data.get('daily') else ''}
      }}
      </script>'''
    return html


def inject(html_content):
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()

    start_marker = '<div class="strat-page" id="strat-momentum-stock">'
    end_marker = '<div class="strat-page" id="strat-cta">'

    start_idx = index.find(start_marker)
    end_idx = index.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("❌ 找不到注入点")
        return False

    new_div = start_marker + html_content + '\n      </div>\n      '
    new_index = index[:start_idx] + new_div + index[end_idx:]

    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="momentum-stock" style="opacity:.4">',
        '<div class="strat-tab" data-strat="momentum-stock">'
    )
    new_index = new_index.replace(
        '<div class="strat-tab" data-strat="momentum-stock" style="opacity:0.4">',
        '<div class="strat-tab" data-strat="momentum-stock">'
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_index)
    return True


def main():
    print("🔥 强势股环境诊断面板注入")

    sent_data = load_json('momentum_sentiment.json')
    if not sent_data:
        print("❌ momentum_sentiment.json 不存在")
        return

    sector_data = load_json('momentum_sector.json')
    warning_data = load_json('momentum_warning.json')
    decomp_data = load_json('momentum_return_decomp.json')

    # 加载产品净值数据
    nav_path = os.path.join(REPO_ROOT, 'size_spread', 'fund_nav', 'fund_nav_momentum-stock.json')
    nav_chart_data = None
    if os.path.exists(nav_path):
        with open(nav_path, 'r', encoding='utf-8') as f:
            nav_chart_data = json.load(f).get('fund', {})

    print(f"📖 情绪: {sent_data['meta']['count']}天 | 板块: {'✅' if sector_data else '❌'} | 预警: {'✅' if warning_data else '❌'} | 归因: {'✅' if decomp_data else '❌'} | 净值: {'✅' if nav_chart_data else '❌'}")

    html = build_html(sent_data, sector_data, warning_data, decomp_data, nav_chart_data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        latest = sent_data['daily'][-1]
        print(f"✅ 注入成功！情绪={latest['sentiment']} 周期={latest['cycle_label']}")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
