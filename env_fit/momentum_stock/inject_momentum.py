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


def build_html(sent_data, sector_data, warning_data, decomp_data, nav_chart_data=None, limit_index_data=None, seal_spread_data=None):
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

    # ═══ 涨停指数 & 高低开 ═══
    li_html = ''
    li_js_data = ''
    li_signal_html = ''
    if limit_index_data and limit_index_data.get('daily'):
        li_daily = limit_index_data['daily']
        li_show = li_daily[-60:] if len(li_daily) > 60 else li_daily
        li_latest = li_show[-1]

        # JS 数据数组
        li_dates_js = json.dumps([fmt_date(d['date']) for d in li_show])
        li_all_nav_base = li_show[0]['all_nav'] if li_show and li_show[0]['all_nav'] else 1
        li_first_nav_base = li_show[0]['first_nav'] if li_show and li_show[0]['first_nav'] else 1
        li_all_nav_js = json.dumps([round(d['all_nav'] / li_all_nav_base, 4) for d in li_show])
        li_first_nav_js = json.dumps([round(d['first_nav'] / li_first_nav_base, 4) for d in li_show])
        li_all_bias_js = json.dumps([d['all_bias'] for d in li_show])
        li_first_bias_js = json.dumps([d['first_bias'] for d in li_show])
        li_all_gap_js = json.dumps([d['all_gap'] if d['all_gap'] is not None else 0 for d in li_show])
        li_first_gap_js = json.dumps([d['first_gap'] if d['first_gap'] is not None else 0 for d in li_show])
        li_all_ret_js = json.dumps([d['all_return'] if d['all_return'] is not None else 0 for d in li_show])
        li_first_ret_js = json.dumps([d['first_return'] if d['first_return'] is not None else 0 for d in li_show])

        li_js_data = f'''
        var liDates={li_dates_js};
        var liAllNav={li_all_nav_js};
        var liFirstNav={li_first_nav_js};
        var liAllBias={li_all_bias_js};
        var liFirstBias={li_first_bias_js};
        var liAllGap={li_all_gap_js};
        var liFirstGap={li_first_gap_js};
        var liAllRet={li_all_ret_js};
        var liFirstRet={li_first_ret_js};
        '''

        # ═══ 信号灯判定 v3：涨停指数 × 情绪周期 三重交叉验证 ═══
        # 
        # 数据验证结论（120日回测）：
        #   退潮日：BIASΔ<0占比75%，平均收益仅+0.50%，收益<0占比39%
        #   加速日：BIASΔ>0占比90%，平均收益+3.15%，收益<0占比0%
        #   → 情绪周期与涨停指数高度共振，可做交叉验证
        #
        # 三重信号：① 净值回撤/上行 ② BIAS变化方向 ③ 情绪周期标签
        #   三者一致 = 高置信信号 | 两者一致 = 中置信 | 矛盾 = 分歧/观望

        bias_val = li_latest['all_bias']
        gap_val = li_latest['all_gap'] if li_latest['all_gap'] is not None else 0

        # ── 因子1：净值回撤 ──
        li_nav_window = li_daily[-20:] if len(li_daily) >= 20 else li_daily
        nav_peak = max(d['all_nav'] for d in li_nav_window)
        nav_current = li_latest['all_nav']
        nav_drawdown = (nav_current - nav_peak) / nav_peak * 100 if nav_peak > 0 else 0

        # ── 因子2：BIAS变化方向（近3日均 vs 前3日均）──
        if len(li_daily) >= 6:
            bias_recent_3 = sum(d['all_bias'] for d in li_daily[-3:]) / 3
            bias_prev_3 = sum(d['all_bias'] for d in li_daily[-6:-3]) / 3
            bias_delta = bias_recent_3 - bias_prev_3
        elif len(li_daily) >= 2:
            bias_delta = li_daily[-1]['all_bias'] - li_daily[-2]['all_bias']
        else:
            bias_delta = 0

        # 净值趋势：近3日收益率之和
        if len(li_daily) >= 3:
            nav_trend = sum(d['all_return'] for d in li_daily[-3:] if d['all_return'] is not None)
        else:
            nav_trend = li_latest['all_return'] if li_latest['all_return'] is not None else 0

        # 首板BIAS同步检查
        first_bias_val = li_latest['first_bias']
        if len(li_daily) >= 6:
            first_bias_recent = sum(d['first_bias'] for d in li_daily[-3:] if d['first_bias'] is not None) / 3
            first_bias_prev = sum(d['first_bias'] for d in li_daily[-6:-3] if d['first_bias'] is not None) / 3
            first_bias_delta = first_bias_recent - first_bias_prev
        elif len(li_daily) >= 2:
            first_bias_delta = (li_daily[-1]['first_bias'] or 0) - (li_daily[-2]['first_bias'] or 0)
        else:
            first_bias_delta = 0

        # ── 因子3：情绪周期标签 ──
        cycle_label = latest.get('cycle_label', '震荡')
        sentiment_val = latest.get('sentiment', 50)
        cycle_is_cooling = cycle_label in ('退潮', '冰点')
        cycle_is_heating = cycle_label in ('加速', '回暖')
        cycle_is_neutral = cycle_label in ('震荡', '分歧')

        # ── 涨停指数方向判定 ──
        li_cooling = nav_drawdown < -1.5 and bias_delta < -0.5
        li_deep_cooling = nav_drawdown < -3.0 and bias_delta < -1.0
        li_heating = nav_drawdown > -0.5 and nav_trend > 1.5 and bias_delta > 0.5
        li_strong_heating = nav_drawdown > -0.3 and nav_trend > 3.0 and bias_delta > 1.0
        li_bottoming = nav_drawdown < -2.0 and bias_delta > 0.3 and nav_trend > 0
        li_divergence = nav_drawdown > -1.0 and bias_delta < -0.8 and bias_val > 2

        # ── 三重交叉判定（置信度标注）──
        # 🔵 降温系列
        if li_deep_cooling and cycle_is_cooling:
            li_signal = '🔵 快速降温 ★★★'
            li_sig_color = '#3b82f6'
            li_sig_desc = f'三重确认：净值回撤{nav_drawdown:.1f}% + BIAS下行 + 情绪{cycle_label}（{sentiment_val:.0f}）'
        elif li_deep_cooling:
            li_signal = '🔵 快速降温 ★★'
            li_sig_color = '#3b82f6'
            li_sig_desc = f'净值回撤{nav_drawdown:.1f}% + BIAS大幅下行，情绪{cycle_label}'
        elif li_cooling and cycle_is_cooling and first_bias_delta < -0.3:
            li_signal = '🔵 全面降温 ★★★'
            li_sig_color = '#60a5fa'
            li_sig_desc = f'三重确认：全板+首板BIAS同步下行 + 情绪{cycle_label}（{sentiment_val:.0f}）'
        elif li_cooling and cycle_is_cooling:
            li_signal = '🔵 降温 ★★★'
            li_sig_color = '#60a5fa'
            li_sig_desc = f'三重确认：净值回撤{nav_drawdown:.1f}% + BIAS下行 + 情绪{cycle_label}'
        elif li_cooling:
            li_signal = '⬇️ 边际降温 ★★'
            li_sig_color = '#93c5fd'
            li_sig_desc = f'净值回撤{nav_drawdown:.1f}% + BIAS下行，但情绪{cycle_label}未同步'
        elif cycle_is_cooling and bias_delta < -0.3:
            li_signal = '⬇️ 情绪降温 ★★'
            li_sig_color = '#93c5fd'
            li_sig_desc = f'情绪{cycle_label}（{sentiment_val:.0f}）+ BIAS下行（Δ{bias_delta:+.1f}），净值回撤{nav_drawdown:.1f}%'
        # 🟡 分歧系列
        elif li_divergence and cycle_is_cooling:
            li_signal = '🟡 见顶退潮 ★★★'
            li_sig_color = '#f59e0b'
            li_sig_desc = f'BIAS掉头（Δ{bias_delta:+.1f}）+ 情绪{cycle_label}，高位风险加大'
        elif li_divergence:
            li_signal = '🟡 见顶分歧 ★★'
            li_sig_color = '#f59e0b'
            li_sig_desc = f'净值高位但BIAS掉头（Δ{bias_delta:+.1f}），情绪{cycle_label}'
        elif cycle_is_cooling and li_heating:
            li_signal = '🟡 多空分歧'
            li_sig_color = '#f59e0b'
            li_sig_desc = f'涨停指数上行但情绪{cycle_label}（{sentiment_val:.0f}），信号矛盾观望'
        elif cycle_is_heating and li_cooling:
            li_signal = '🟡 多空分歧'
            li_sig_color = '#f59e0b'
            li_sig_desc = f'情绪{cycle_label}但涨停指数回撤{nav_drawdown:.1f}%，信号矛盾观望'
        # 🟢 回暖系列
        elif li_bottoming and cycle_is_heating:
            li_signal = '🟢 筑底回暖 ★★★'
            li_sig_color = '#10b981'
            li_sig_desc = f'三重确认：净值止跌 + BIAS回升（Δ{bias_delta:+.1f}）+ 情绪{cycle_label}'
        elif li_bottoming:
            li_signal = '🟢 筑底回暖 ★★'
            li_sig_color = '#10b981'
            li_sig_desc = f'净值止跌 + BIAS回升（Δ{bias_delta:+.1f}），情绪{cycle_label}'
        # 🔴 升温系列
        elif li_strong_heating and cycle_is_heating:
            li_signal = '🔴 加速升温 ★★★'
            li_sig_color = '#ef4444'
            li_sig_desc = f'三重确认：净值连涨{nav_trend:.1f}% + BIAS加速 + 情绪{cycle_label}（{sentiment_val:.0f}），警惕过热'
        elif li_strong_heating:
            li_signal = '🔴 加速升温 ★★'
            li_sig_color = '#ef4444'
            li_sig_desc = f'净值连涨{nav_trend:.1f}% + BIAS加速上行，情绪{cycle_label}'
        elif li_heating and cycle_is_heating:
            li_signal = '🟠 持续升温 ★★★'
            li_sig_color = '#f97316'
            li_sig_desc = f'三重确认：净值上行 + BIAS上升（Δ{bias_delta:+.1f}）+ 情绪{cycle_label}'
        elif li_heating:
            li_signal = '🟠 持续升温 ★★'
            li_sig_color = '#f97316'
            li_sig_desc = f'净值上行 + BIAS上升（Δ{bias_delta:+.1f}），情绪{cycle_label}'
        elif cycle_is_heating and bias_delta > 0.3:
            li_signal = '🟠 情绪升温 ★★'
            li_sig_color = '#f97316'
            li_sig_desc = f'情绪{cycle_label}（{sentiment_val:.0f}）+ BIAS上行（Δ{bias_delta:+.1f}）'
        # ⚪ 中性
        else:
            li_signal = '⚪ 中性震荡'
            li_sig_color = '#94a3b8'
            li_sig_desc = f'无明显共振信号，情绪{cycle_label}（{sentiment_val:.0f}），观望'

        # ── 置信度说明 ──
        # ★★★ = 涨停指数 + BIAS方向 + 情绪周期 三者一致
        # ★★  = 两者一致，第三个中性或矛盾
        # 无星  = 信号矛盾或无方向

        bias_color = '#ef4444' if bias_delta > 0.5 else '#3b82f6' if bias_delta < -0.5 else '#64748b'
        gap_color = '#ef4444' if gap_val > 0 else '#10b981'
        dd_color = '#ef4444' if nav_drawdown < -2 else '#f59e0b' if nav_drawdown < -1 else '#64748b'
        cycle_color = {'退潮': '#8b5cf6', '冰点': '#3b82f6', '加速': '#ef4444', '回暖': '#10b981', '分歧': '#f59e0b', '震荡': '#94a3b8'}.get(cycle_label, '#94a3b8')

        li_signal_html = f'''
      <div class="card" style="padding:14px 20px">
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="dot" style="background:{li_sig_color}"></span>
            <span style="font-size:14px;font-weight:700;color:#1e293b">涨停指数信号</span>
            <span style="font-size:14px;font-weight:700;color:{li_sig_color}">{li_signal}</span>
          </div>
          <span style="font-size:11px;color:#94a3b8">{li_sig_desc}</span>
          <div style="margin-left:auto;display:flex;gap:16px;font-size:12px">
            <span>BIAS <b style="color:{bias_color}">{bias_val:+.1f}%</b> <span style="color:#94a3b8;font-size:10px">Δ{bias_delta:+.1f}</span></span>
            <span>回撤 <b style="color:{dd_color}">{nav_drawdown:+.1f}%</b></span>
            <span>高低开 <b style="color:{gap_color}">{gap_val:+.2f}%</b></span>
            <span>情绪 <b style="color:{cycle_color}">{cycle_label}</b> <span style="color:#94a3b8;font-size:10px">{sentiment_val:.0f}</span></span>
            <span style="color:#94a3b8">首板BIAS <b>{first_bias_val:+.1f}%</b> <span style="font-size:10px">Δ{first_bias_delta:+.1f}</span></span>
          </div>
        </div>
      </div>'''

        li_html = f'''
      <div class="card" style="padding:16px 20px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div class="card-title" style="margin:0"><span class="dot" style="background:#6366f1"></span> 涨停指数 & 乖离率（BIAS）</div>
          <div style="font-size:11px;color:#94a3b8">最新 {fmt_date(li_latest['date'])}</div>
        </div>
        <div style="position:relative;height:300px"><canvas id="ms-li-chart"></canvas></div>
        <div style="font-size:10px;color:#94a3b8;margin-top:6px;line-height:1.5">
          灰线=全涨停净值（近60日归一化，左轴） · 灰虚线=首板净值（近60日归一化，左轴） · 紫线=全涨停BIAS（右轴） · 浅紫虚线=首板BIAS<br>
          信号v3：涨停指数(净值回撤+BIAS方向) × 情绪周期 三重交叉验证 · ★★★=三重确认 · ★★=两重确认
        </div>
      </div>'''

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

    # ═══ 封单额轧差 (Seal Spread) ═══
    seal_html = ''
    seal_js_data = ''
    if seal_spread_data and seal_spread_data.get('daily'):
        ss_daily = seal_spread_data['daily']
        ss_show = ss_daily[-60:] if len(ss_daily) > 60 else ss_daily
        ss_latest = ss_show[-1]

        ss_dates_js = json.dumps([fmt_date(d['date']) for d in ss_show])
        ss_spread_js = json.dumps([d['seal_spread'] for d in ss_show])
        ss_ma5_js = json.dumps([d['spread_ma5'] for d in ss_show])
        ss_ma20_js = json.dumps([d['spread_ma20'] for d in ss_show])
        ss_ratio_js = json.dumps([d['seal_ratio'] for d in ss_show])
        ss_up_js = json.dumps([d['up_seal_total'] for d in ss_show])
        ss_down_js = json.dumps([-d['down_seal_total'] for d in ss_show])  # 负值画向下

        seal_js_data = f'''
        var ssDates={ss_dates_js};
        var ssSpread={ss_spread_js};
        var ssMa5={ss_ma5_js};
        var ssMa20={ss_ma20_js};
        var ssRatio={ss_ratio_js};
        var ssUp={ss_up_js};
        var ssDown={ss_down_js};
        '''

        # 信号标签颜色
        ss_signal = ss_latest.get('signal', '⚪ 均衡')
        ss_pct = ss_latest.get('spread_pct_1y')
        ss_pct_str = f"{ss_pct*100:.1f}%" if ss_pct is not None else "N/A"
        if '极度恐慌' in ss_signal:
            ss_sig_color = '#10b981'
            ss_bg = '#f0fdf4'
        elif '偏空' in ss_signal:
            ss_sig_color = '#3b82f6'
            ss_bg = '#eff6ff'
        elif '偏多' in ss_signal:
            ss_sig_color = '#f59e0b'
            ss_bg = '#fefce8'
        elif '极度亢奋' in ss_signal:
            ss_sig_color = '#ef4444'
            ss_bg = '#fef2f2'
        else:
            ss_sig_color = '#64748b'
            ss_bg = '#f8fafc'

        seal_html = f'''
      <div class="card" style="padding:16px 20px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div class="card-title" style="margin:0"><span class="dot" style="background:#6366f1"></span> 涨跌停封单额轧差（抄底指标）</div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="background:{ss_bg};color:{ss_sig_color};padding:3px 10px;border-radius:10px;font-size:11px;font-weight:600">{ss_signal}</span>
            <span style="font-size:11px;color:#94a3b8">最新 {fmt_date(ss_latest['date'])} · 分位 {ss_pct_str}</span>
          </div>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap">
          <div style="font-size:12px;color:#64748b">轧差 <b style="color:{"#10b981" if ss_latest["seal_spread"] >= 0 else "#ef4444"};font-size:16px">{ss_latest["seal_spread"]:+.1f}</b> 亿</div>
          <div style="font-size:12px;color:#64748b">涨停封单 <b>{ss_latest["up_seal_total"]:.1f}</b>亿 ({ss_latest["up_count"]}只)</div>
          <div style="font-size:12px;color:#64748b">跌停封单 <b>{ss_latest["down_seal_total"]:.1f}</b>亿 ({ss_latest["down_count"]}只)</div>
        </div>
        <div style="position:relative;height:280px"><canvas id="ms-seal"></canvas></div>
        <div style="font-size:10px;color:#94a3b8;margin-top:4px">绿色柱=涨停封单额 · 红色柱=跌停封单额（向下） · 紫色线=轧差 · 橙虚线=MA5 · 灰虚线=MA20 · 轧差<5%分位=🟢抄底信号</div>
      </div>'''

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

      <!-- 涨停指数信号灯 -->
      {li_signal_html}

      <!-- 涨停指数 BIAS 图 -->
      {li_html}

      <!-- 封单额轧差图 -->
      {seal_html}

      <div class="card">
        <div class="card-title"><span class="dot" style="background:{ls_color}"></span> 合成情绪指数（0-100）</div>
        <div style="position:relative;height:280px"><canvas id="ms-c1"></canvas></div>
        <div id="ms-timeline" style="display:flex;gap:0;margin-top:6px;height:20px;border-radius:4px;overflow:hidden"></div>
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
        <div class="card-title"><span class="dot" style="background:#ef4444"></span> 涨停 / 跌停 / 炸板 & 次日高低开</div>
        <div style="position:relative;height:300px"><canvas id="ms-c3"></canvas></div>
        <div style="font-size:10px;color:#94a3b8;margin-top:4px">柱状=涨跌停/炸板家数（左轴） · 实线=全涨停次日高低开 · 虚线=首板次日高低开（右轴,%）</div>
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
          options:Object.assign({{}},msB,{{
            plugins:{{
              legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}},
              tooltip:{{
                callbacks:{{
                  afterBody:function(ctx){{
                    var idx=ctx[0].dataIndex;
                    return '情绪周期: '+msCL[idx];
                  }}
                }}
              }}
            }},
            scales:{{x:msB.scales.x,y:{{ticks:{{font:{{size:9}},color:'#94a3b8',stepSize:20}},grid:{{color:'#f1f5f9'}},min:0,max:100}}}}
          }})
        }});

        // Cycle timeline with text labels
        var cycleColors={cycle_colors_js};
        var tl=document.getElementById('ms-timeline');
        if(tl){{
          // 先把连续相同周期合并成段
          var segments=[];
          var curLabel=msCL[0], startIdx=0;
          for(var i=1;i<=msCL.length;i++){{
            if(i===msCL.length || msCL[i]!==curLabel){{
              segments.push({{label:curLabel, start:startIdx, end:i-1, len:i-startIdx}});
              if(i<msCL.length){{ curLabel=msCL[i]; startIdx=i; }}
            }}
          }}
          // 渲染每段为一个带文字的块
          segments.forEach(function(seg){{
            var c=cycleColors[seg.label]||'#94a3b8';
            var el=document.createElement('div');
            el.style.cssText='flex:'+seg.len+';background:'+c+'30;height:100%;display:flex;align-items:center;justify-content:center;position:relative;border-right:1px solid #fff;overflow:hidden;cursor:default';
            // 只在段宽够时显示文字（>=3天）
            if(seg.len>=3 && seg.label!=='—'){{
              var txt=document.createElement('span');
              txt.textContent=seg.label;
              txt.style.cssText='font-size:9px;font-weight:700;color:'+c+';white-space:nowrap;text-shadow:0 0 3px #fff,0 0 3px #fff';
              el.appendChild(txt);
            }}
            // tooltip 显示日期范围
            var d0=msL[seg.start], d1=msL[seg.end];
            el.title=seg.label+' ('+d0+'~'+d1+', '+seg.len+'天)';
            tl.appendChild(el);
          }});
        }}

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

        // ── 涨停指数数据 ──
        {li_js_data if li_js_data else ''}

        // ── 封单额轧差数据 ──
        {seal_js_data if seal_js_data else ''}
        if(typeof ssDates!=='undefined' && document.getElementById('ms-seal')){{
          new Chart(document.getElementById('ms-seal'),{{
            type:'bar',
            data:{{labels:ssDates,datasets:[
              {{label:'涨停封单(亿)',data:ssUp,backgroundColor:'rgba(16,185,129,0.6)',borderRadius:2,barPercentage:0.6,stack:'seal',yAxisID:'y'}},
              {{label:'跌停封单(亿)',data:ssDown,backgroundColor:'rgba(239,68,68,0.6)',borderRadius:2,barPercentage:0.6,stack:'seal',yAxisID:'y'}},
              {{label:'轧差(亿)',data:ssSpread,type:'line',borderColor:'#6366f1',borderWidth:2.5,pointRadius:1.5,pointBackgroundColor:ssSpread.map(function(v){{return v>=0?'#10b981':'#ef4444'}}),tension:.2,yAxisID:'y1',order:0}},
              {{label:'MA5',data:ssMa5,type:'line',borderColor:'#f59e0b',borderWidth:1.2,borderDash:[4,3],pointRadius:0,tension:.2,yAxisID:'y1',order:1}},
              {{label:'MA20',data:ssMa20,type:'line',borderColor:'#94a3b8',borderWidth:1,borderDash:[2,2],pointRadius:0,tension:.2,yAxisID:'y1',order:2}}
            ]}},
            options:{{
              responsive:true,maintainAspectRatio:false,
              interaction:{{mode:'index',intersect:false}},
              plugins:{{
                legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}},
                tooltip:{{
                  callbacks:{{
                    afterBody:function(ctx){{
                      var idx=ctx[0].dataIndex;
                      var r=ssRatio[idx];
                      return '涨停封单占比: '+(r*100).toFixed(1)+'%';
                    }}
                  }}
                }}
              }},
              scales:{{
                x:{{ticks:{{maxTicksToShow:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}},stacked:true}},
                y:{{position:'left',stacked:true,ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}},title:{{display:true,text:'封单额(亿)',font:{{size:9}},color:'#94a3b8'}}}},
                y1:{{position:'right',ticks:{{font:{{size:9}},color:'#6366f1'}},grid:{{display:false}},title:{{display:true,text:'轧差(亿)',font:{{size:9}},color:'#6366f1'}}}}
              }}
            }}
          }});
        }}

        // 对齐高低开数据到情绪日期轴（limit_index日期可能比情绪数据少）
        var liGapAll=[], liGapFirst=[];
        if(typeof liDates!=='undefined'){{
          var liMap={{}};
          liDates.forEach(function(d,i){{ liMap[d]={{allGap:liAllGap[i],firstGap:liFirstGap[i]}}; }});
          msL.forEach(function(d){{
            var m=liMap[d];
            liGapAll.push(m?m.allGap:null);
            liGapFirst.push(m?m.firstGap:null);
          }});
        }}

        new Chart(document.getElementById('ms-c3'),{{
          type:'bar',
          data:{{labels:msL,datasets:[
            {{label:'涨停',data:msU,backgroundColor:'rgba(239,68,68,0.7)',borderRadius:2,barPercentage:0.7,yAxisID:'y'}},
            {{label:'跌停',data:msD.map(function(v){{return -v}}),backgroundColor:'rgba(16,185,129,0.7)',borderRadius:2,barPercentage:0.7,yAxisID:'y'}},
            {{label:'炸板',data:msZ,backgroundColor:'rgba(245,158,11,0.5)',borderRadius:2,barPercentage:0.7,yAxisID:'y'}}
          ].concat(liGapAll.length?[
            {{label:'全涨停高低开(%)',data:liGapAll,type:'line',borderColor:'#6366f1',borderWidth:2,pointRadius:1,pointBackgroundColor:liGapAll.map(function(v){{return v!==null&&v>0?'#ef4444':'#10b981'}}),tension:.2,yAxisID:'y1',spanGaps:true}},
            {{label:'首板高低开(%)',data:liGapFirst,type:'line',borderColor:'#a78bfa',borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:.2,yAxisID:'y1',spanGaps:true}}
          ]:[])
          }},
          options:Object.assign({{}},msB,{{scales:{{
            x:msB.scales.x,
            y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8'}},grid:{{color:'#f1f5f9'}}}},
            y1:{{position:'right',ticks:{{font:{{size:9}},color:'#6366f1',callback:function(v){{return v+'%'}}}},grid:{{display:false}},title:{{display:true,text:'高低开 %',font:{{size:9}},color:'#6366f1'}}}}
          }}}})
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

        // ── 涨停指数 & BIAS 图 ──
        {f"""
        (function(){{
          var el=document.getElementById('ms-li-chart');
          if(!el||typeof liDates==='undefined')return;

          // BIAS 背景色带数据：超过阈值区域
          var biasBgAll=liAllBias.map(function(v){{
            if(v>3)return v;
            if(v<-3)return v;
            return null;
          }});

          new Chart(el,{{
            type:'line',
            data:{{labels:liDates,datasets:[
              // 净值（左轴，灰色调背景）
              {{label:'全涨停净值',data:liAllNav,borderColor:'#94a3b8',borderWidth:1.5,pointRadius:0,tension:.3,fill:false,yAxisID:'y',order:3}},
              {{label:'首板净值',data:liFirstNav,borderColor:'#cbd5e1',borderWidth:1.2,borderDash:[4,3],pointRadius:0,tension:.3,fill:false,yAxisID:'y',order:4}},
              // BIAS（右轴，彩色突出）
              {{label:'全涨停BIAS',data:liAllBias,borderColor:'#6366f1',borderWidth:2,pointRadius:1.5,pointBackgroundColor:liAllBias.map(function(v){{return v>3?'#ef4444':v<-3?'#3b82f6':'#6366f1'}}),tension:.2,fill:false,yAxisID:'y1',order:1}},
              {{label:'首板BIAS',data:liFirstBias,borderColor:'#a78bfa',borderWidth:1.2,borderDash:[4,3],pointRadius:0,tension:.2,fill:false,yAxisID:'y1',order:2}}
            ]}},
            options:{{
              responsive:true,maintainAspectRatio:false,
              interaction:{{mode:'index',intersect:false}},
              plugins:{{
                legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}},padding:12}}}},
                tooltip:{{
                  callbacks:{{
                    afterBody:function(ctx){{
                      var i=ctx[0].dataIndex;
                      var ret='\\n收益: '+liAllRet[i].toFixed(2)+'%';
                      ret+='\\n高低开: '+liAllGap[i].toFixed(2)+'%';
                      if(liAllBias[i]>3)ret+='\\n⚠️ BIAS偏高，拥挤警告';
                      if(liAllBias[i]<-3)ret+='\\n💡 BIAS偏低，关注反转';
                      return ret;
                    }}
                  }}
                }},
                annotation:{{
                  annotations:{{
                    biasHigh:{{type:'line',yMin:3,yMax:3,yScaleID:'y1',borderColor:'rgba(239,68,68,0.4)',borderWidth:1,borderDash:[4,4],label:{{display:true,content:'+3%',position:'end',font:{{size:9}},color:'#ef4444',backgroundColor:'transparent'}}}},
                    biasLow:{{type:'line',yMin:-3,yMax:-3,yScaleID:'y1',borderColor:'rgba(59,130,246,0.4)',borderWidth:1,borderDash:[4,4],label:{{display:true,content:'-3%',position:'end',font:{{size:9}},color:'#3b82f6',backgroundColor:'transparent'}}}},
                    biasZero:{{type:'line',yMin:0,yMax:0,yScaleID:'y1',borderColor:'rgba(148,163,184,0.3)',borderWidth:1}}
                  }}
                }}
              }},
              scales:{{
                x:{{ticks:{{maxTicksToShow:12,font:{{size:9}},color:'#94a3b8'}},grid:{{display:false}}}},
                y:{{position:'left',ticks:{{font:{{size:9}},color:'#94a3b8',callback:function(v){{return v.toFixed(1)}}}},grid:{{color:'#f1f5f9'}},title:{{display:true,text:'净值',font:{{size:9}},color:'#94a3b8'}}}},
                y1:{{position:'right',ticks:{{font:{{size:9}},color:'#6366f1',callback:function(v){{return v+'%'}}}},grid:{{display:false}},title:{{display:true,text:'BIAS %',font:{{size:9}},color:'#6366f1'}}}}
              }}
            }}
          }});
        }})();
        """ if limit_index_data and limit_index_data.get('daily') else ''}

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

    # 加载涨停指数数据
    li_path = os.path.join(BASE_DIR, 'limit_index', 'limit_index.json')
    limit_index_data = None
    if os.path.exists(li_path):
        with open(li_path, 'r', encoding='utf-8') as f:
            limit_index_data = json.load(f)

    # 加载封单额轧差数据
    ss_path = os.path.join(BASE_DIR, 'limit_index', 'seal_spread', 'seal_spread.json')
    seal_spread_data = None
    if os.path.exists(ss_path):
        with open(ss_path, 'r', encoding='utf-8') as f:
            seal_spread_data = json.load(f)

    print(f"📖 情绪: {sent_data['meta']['count']}天 | 板块: {'✅' if sector_data else '❌'} | 预警: {'✅' if warning_data else '❌'} | 归因: {'✅' if decomp_data else '❌'} | 净值: {'✅' if nav_chart_data else '❌'} | 涨停指数: {'✅' if limit_index_data else '❌'} | 封单轧差: {'✅' if seal_spread_data else '❌'}")

    html = build_html(sent_data, sector_data, warning_data, decomp_data, nav_chart_data, limit_index_data, seal_spread_data)
    print(f"🎨 生成 {len(html)} 字符")

    if inject(html):
        latest = sent_data['daily'][-1]
        print(f"✅ 注入成功！情绪={latest['sentiment']} 周期={latest['cycle_label']}")
    else:
        print("❌ 注入失败")


if __name__ == '__main__':
    main()
