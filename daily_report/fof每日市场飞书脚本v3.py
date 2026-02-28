#!/usr/bin/env python3
"""FOF 每日市场观察报告 v3 - Tushare + iFind 双源"""
import requests, json, sys
from datetime import datetime, timedelta

# ═══ 配置 ═══
TS_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TS_SERVER = 'http://lianghua.nanyangqiankun.top'
IFIND_BASE = 'https://quantapi.51ifind.com/api/v1'
IFIND_REFRESH = 'eyJzaWduX3RpbWUiOiIyMDI2LTAyLTA5IDE5OjE3OjQwIn0=.eyJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyIjp7ImFjY291bnQiOiJncnN6aDAwMSIsImF1dGhVc2VySW5mbyI6eyJhcGlGb3JtYWwiOiIxIn0sImNvZGVDU0kiOltdLCJjb2RlWnpBdXRoIjpbXSwiaGFzQUlQcmVkaWN0IjpmYWxzZSwiaGFzQUlUYWxrIjpmYWxzZSwiaGFzQ0lDQyI6ZmFsc2UsImhhc0NTSSI6ZmFsc2UsImhhc0V2ZW50RHJpdmUiOmZhbHNlLCJoYXNGVFNFIjpmYWxzZSwiaGFzRmFzdCI6ZmFsc2UsImhhc0Z1bmRWYWx1YXRpb24iOmZhbHNlLCJoYXNISyI6dHJ1ZSwiaGFzTE1FIjpmYWxzZSwiaGFzTGV2ZWwyIjpmYWxzZSwiaGFzUmVhbENNRSI6ZmFsc2UsImhhc1RyYW5zZmVyIjpmYWxzZSwiaGFzVVMiOmZhbHNlLCJoYXNVU0FJbmRleCI6ZmFsc2UsImhhc1VTREVCVCI6ZmFsc2UsIm1hcmtldEF1dGgiOnsiRENFIjpmYWxzZX0sIm1heE9uTGluZSI6MSwibm9EaXNrIjpmYWxzZSwicHJvZHVjdFR5cGUiOiJTVVBFUkNPTU1BTkRQUk9EVUNUIiwicmVmcmVzaFRva2VuRXhwaXJlZFRpbWUiOiIyMDI2LTAzLTA5IDE5OjAwOjU1Iiwic2Vzc3Npb24iOiI0YzRjYjhhNTdiNWQwYzA3N2UxNTEwMzIxN2M2YWNjYSIsInNpZEluZm8iOns2NDoiMTExMTExMTExMTExMTExMTExMTExMTExIiwxOiIxMDEiLDI6IjEiLDY3OiIxMDExMTExMTExMTExMTExMTExMTExMTEiLDM6IjEiLDY5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiw1OiIxIiw2OiIxIiw3MToiMTExMTExMTExMTExMTExMTExMTExMTAwIiw3OiIxMTExMTExMTExMSIsODoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDEiLDEzODoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTM5OiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDA6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDE0MToiMTExMTExMTExMTExMTExMTExMTExMTExMSIsMTQyOiIxMTExMTExMTExMTExMTExMTExMTExMTExIiwxNDM6IjExIiw4MDoiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MToiMTExMTExMTExMTExMTExMTExMTExMTExIiw4MjoiMTExMTExMTExMTExMTExMTExMTEwMTEwIiw4MzoiMTExMTExMTExMTExMTExMTExMDAwMDAwIiw4NToiMDExMTExMTExMTExMTExMTExMTExMTExIiw4NzoiMTExMTExMTEwMDExMTExMDExMTExMTExIiw4OToiMTExMTExMTEwMTEwMTExMTExMTAxMTExIiw5MDoiMTExMTEwMTExMTExMTExMTExMTExMTExMTAiLDkzOiIxMTExMTExMTExMTExMTExMTAwMDAxMTExIiw5NDoiMTExMTExMTExMTExMTExMTExMTExMTExMSIsOTY6IjExMTExMTExMTExMTExMTExMTExMTExMTEiLDk5OiIxMDAiLDEwMDoiMTExMTAxMTExMTExMTExMTExMCIsMTAyOiIxIiw0NDoiMTEiLDEwOToiMSIsNTM6IjExMTExMTExMTExMTExMTExMTExMTExMSIsNTQ6IjExMDAwMDAwMDAxMTAwMDAwMTAxMDAwMDAxMDAxMDAwMDAwIiw1NzoiMDAwMDAwMDAwMDAwMDAwMDAwMDAxMDAwMDAwMDAiLDYyOiIxMTExMTExMTExMTExMTExMTExMTExMTEiLDYzOiIxMTExMTExMTExMTExMTExMTExMTExMTEifSwidGltZXN0YW1wIjoiMTc3MDYzNTg2MDcxOSIsInRyYW5zQXV0aCI6ZmFsc2UsInR0bFZhbHVlIjowLCJ1aWQiOiI4NDQ3MzY2NjMiLCJ1c2VyVHlwZSI6Ik9GRklDSUFMIiwid2lmaW5kTGltaXRNYXAiOnt9fX0=.7AAB9445C9074F4FD9C933A4ECF96C3359428E3393255673AFE507504D9E7270'
PROXY = None  # iFind 直连，不走代理

# ═══ Tushare 查询 ═══
def ts(api_name, params=None, fields=''):
    req = {'api_name': api_name, 'token': TS_TOKEN, 'params': params or {}, 'fields': fields}
    try:
        r = requests.post(TS_SERVER, json=req, timeout=30)
        result = r.json()
        if result.get('code') != 0: return None
        data = result.get('data', {})
        items, cols = data.get('items', []), data.get('fields', [])
        return [dict(zip(cols, row)) for row in items] if items else None
    except Exception as e:
        print(f"  [TS ERR] {api_name}: {e}", file=sys.stderr)
        return None

# ═══ iFind 查询 ═══
def get_ifind_token():
    try:
        r = requests.post(f'{IFIND_BASE}/get_access_token',
            json={'refresh_token': IFIND_REFRESH}, proxies=PROXY, timeout=15)
        d = r.json()
        if d.get('errorcode') == 0:
            return d['data']['access_token']
    except Exception as e:
        print(f"  [iFind ERR] get_token: {e}", file=sys.stderr)
    return None

def ifind_rt(access_token, codes, indicators='latest,change,pct_change', retries=2):
    """iFind 实时行情（带重试）"""
    import time
    for i in range(retries + 1):
        try:
            r = requests.post(f'{IFIND_BASE}/real_time_quotation',
                headers={'Content-Type': 'application/json', 'access_token': access_token},
                json={'codes': codes, 'indicators': indicators},
                proxies=PROXY, timeout=15)
            d = r.json()
            if d.get('errorcode') == 0 and d.get('tables'):
                return d['tables']
        except Exception as e:
            if i < retries:
                time.sleep(1)
                continue
            print(f"  [iFind ERR] rt {codes}: {e}", file=sys.stderr)
    return None

# ═══ 工具函数 ═══
def cs(v, fmt='.2f'):
    s = f"{v:{fmt}}"
    return f"+{s}" if v >= 0 else s

def log(msg):
    print(msg, file=sys.stderr)

# ═══ 主流程 ═══
def run():
    now = datetime.now()
    end = now.strftime('%Y%m%d')
    s20 = (now - timedelta(days=45)).strftime('%Y%m%d')
    sm = (now - timedelta(days=400)).strftime('%Y%m')

    lines = []
    lines.append(f"📊 FOF 每日市场观察")
    lines.append(f"生成: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ═══ 获取 iFind token ═══
    log("获取 iFind access_token...")
    at = get_ifind_token()
    if at:
        log(f"  iFind token OK")
    else:
        log("  iFind token 获取失败，仅用 Tushare")

    # ═══ 1. 全球流动性 ═══
    lines.append("━━ 1. 全球流动性 ━━")

    # 美债 (Tushare)
    log("拉美债...")
    d = ts('us_tycr', {'start_date': s20, 'end_date': end})
    if d:
        d.sort(key=lambda x: x['date'], reverse=True)
        c, p = d[0], d[1]
        y2, y10 = float(c['y2']), float(c['y10'])
        py2, py10 = float(p['y2']), float(p['y10'])
        sp, psp = y10 - y2, py10 - py2
        lines.append(f"美债({c['date']})")
        lines.append(f"  2Y {y2:.3f}%({cs(y2-py2,'.3f')}) 10Y {y10:.3f}%({cs(y10-py10,'.3f')}) 利差 {sp:.3f}({cs(sp-psp,'.3f')})")
    else:
        lines.append("  美债: N/A")

    # USDCNH (Tushare)
    log("拉汇率...")
    d = ts('fx_daily', {'ts_code': 'USDCNH.FXCM', 'start_date': s20, 'end_date': end})
    ts_usdcnh = None
    if d:
        d.sort(key=lambda x: x['trade_date'], reverse=True)
        ck = 'close' if 'close' in d[0] else 'bid_close' if 'bid_close' in d[0] else None
        if ck:
            cv, pv = float(d[0][ck]), float(d[1][ck])
            ts_usdcnh = cv
            lines.append(f"USDCNH(TS {d[0]['trade_date']}) {cv:.4f}({cs(cv-pv,'.4f')})")

    # USDCNH (iFind 交叉校验)
    if at:
        log("拉 iFind USDCNH...")
        tables = ifind_rt(at, 'USDCNH.FX')
        if tables:
            t = tables[0]['table']
            ifind_cnh = t.get('latest', [None])[0]
            if ifind_cnh:
                chg = t.get('change', [0])[0] or 0
                lines.append(f"USDCNH(iFind) {ifind_cnh:.4f}({cs(chg,'.4f')})")
                if ts_usdcnh:
                    diff = abs(ts_usdcnh - ifind_cnh)
                    lines.append(f"  ✅ 交叉校验 差值{diff:.4f}" if diff < 0.05 else f"  ⚠️ 交叉校验 差值{diff:.4f}")

    # Shibor (Tushare)
    log("拉Shibor...")
    d = ts('shibor', {'start_date': s20, 'end_date': end})
    if d:
        d.sort(key=lambda x: x['date'], reverse=True)
        c, p = d[0], d[1]
        parts = []
        for col, lb in [('on','ON'),('1w','1W'),('1m','1M'),('3m','3M')]:
            if col in c and c[col] is not None:
                v, pv = float(c[col]), float(p[col])
                parts.append(f"{lb} {v:.2f}%({cs(v-pv,'.2f')})")
        lines.append(f"Shibor({c['date']}) {' | '.join(parts)}")
    else:
        lines.append("  Shibor: N/A")

    # 纳指100 + 费城半导体 + 恒生 + 恒生科技 (iFind)
    if at:
        for code, name in [('NDX.GI','纳指100'), ('SOXX.O','费城半导体ETF'), ('HSI.HK','恒生指数'), ('HSTECH.HK','恒生科技')]:
            log(f"拉 iFind {name}...")
            tables = ifind_rt(at, code)
            if tables:
                t = tables[0]['table']
                tm = tables[0].get('time', [''])[0][:10] if tables[0].get('time') else ''
                latest = t.get('latest', [None])[0]
                chg = t.get('change', [0])[0] or 0
                if latest:
                    lines.append(f"{name}({tm}) {latest:.2f}({cs(chg,'.2f')})")
                else:
                    lines.append(f"  {name}: 无数据")
            else:
                lines.append(f"  {name}: iFind N/A")
    else:
        lines.append("  纳指/费城半导体: iFind 不可用")

    lines.append("⚠️ DXY/黄金/WTI/BTC 待补充数据源")
    lines.append("")

    # ═══ 2. 中国基本盘 ═══
    lines.append("━━ 2. 中国基本盘 ━━")

    log("拉CPI...")
    d = ts('cn_cpi', {'start_m': sm, 'end_m': end[:6]})
    if d:
        d.sort(key=lambda x: x['month'], reverse=True)
        c, p = d[0], d[1]
        lines.append(f"CPI({c['month']}) 同比{float(c['nt_yoy']):.1f}%(前{float(p['nt_yoy']):.1f}%) 环比{float(c['nt_mom']):.1f}%")
    else:
        lines.append("  CPI: N/A")

    log("拉PPI...")
    d = ts('cn_ppi', {'start_m': sm, 'end_m': end[:6]})
    if d:
        d.sort(key=lambda x: x['month'], reverse=True)
        c, p = d[0], d[1]
        lines.append(f"PPI({c['month']}) 同比{float(c['ppi_yoy']):.1f}%(前{float(p['ppi_yoy']):.1f}%) 环比{float(c['ppi_mom']):.1f}%")
    else:
        lines.append("  PPI: N/A")

    log("拉PMI...")
    d = ts('cn_pmi', {'start_m': sm, 'end_m': end[:6]})
    if d:
        mk = 'MONTH' if 'MONTH' in d[0] else 'month'
        pk = 'PMI010000' if 'PMI010000' in d[0] else 'man_pmi'
        d.sort(key=lambda x: x[mk], reverse=True)
        c, p = d[0], d[1]
        m, pm = float(c[pk]), float(p[pk])
        lines.append(f"PMI({c[mk]}) 制造业{m:.1f}(前{pm:.1f},{cs(m-pm,'.1f')})")
    else:
        lines.append("  PMI: N/A")

    log("拉M1M2...")
    d = ts('cn_m', {'start_m': sm, 'end_m': end[:6]})
    if d:
        d.sort(key=lambda x: x['month'], reverse=True)
        c, p = d[0], d[1]
        lines.append(f"M1同比{float(c['m1_yoy']):.1f}%(前{float(p['m1_yoy']):.1f}%) M2同比{float(c['m2_yoy']):.1f}%(前{float(p['m2_yoy']):.1f}%)")
    else:
        lines.append("  M1/M2: N/A")
    lines.append("")

    # ═══ 3. 中观景气 ═══
    lines.append("━━ 3. 中观景气(期货主力) ━━")
    futs = {'RB.SHF':'螺纹','I.DCE':'铁矿','FG.ZCE':'玻璃','SA.ZCE':'纯碱','AL.SHF':'铝'}
    for code, name in futs.items():
        log(f"拉{name}...")
        try:
            dm = ts('fut_mapping', {'ts_code': code, 'start_date': s20, 'end_date': end})
            if not dm: raise Exception("no mapping")
            dm.sort(key=lambda x: x['trade_date'], reverse=True)
            contract = dm[0]['mapping_ts_code']
            df = ts('fut_daily', {'ts_code': contract, 'start_date': s20, 'end_date': end})
            if not df: raise Exception("no daily")
            df.sort(key=lambda x: x['trade_date'], reverse=True)
            close = float(df[0]['close'])
            fut_date = df[0]['trade_date']
            if len(df) >= 20:
                t20 = (close / float(df[19]['close']) - 1) * 100
                lines.append(f"  {name}({fut_date}) {close:.0f} (20日{cs(t20,'.1f')}%)")
            else:
                lines.append(f"  {name}({fut_date}) {close:.0f}")
        except:
            lines.append(f"  {name}: N/A")

    # 费城半导体 (已在模块1输出，这里跳过)
    lines.append("")

    # ═══ 4. A股微观 ═══
    a_stock_header_idx = len(lines)
    lines.append("")  # 占位，拉完数据后回填带日期的标题
    indices = [
        ('000300.SH','沪深300'),('000016.SH','上证50'),('000905.SH','中证500'),
        ('000852.SH','中证1000'),('932000.CSI','中证2000'),('000688.SH','科创50'),
        ('399006.SZ','创业板指'),('899050.BJ','北证50'),
    ]
    trade_date = None
    idx_data = {}
    for code, name in indices:
        log(f"拉{name}...")
        d = ts('index_daily', {'ts_code': code, 'start_date': s20, 'end_date': end})
        if d:
            d.sort(key=lambda x: x['trade_date'], reverse=True)
            c = d[0]
            close = float(c['close'])
            chg = float(c['pct_chg'])
            if trade_date is None: trade_date = c['trade_date']
            t20 = (close / float(d[min(19,len(d)-1)]['close']) - 1) * 100 if len(d) >= 20 else None
            emoji = "🔴" if chg < 0 else "🟢"
            t20s = f" 20日{cs(t20,'.1f')}%" if t20 is not None else ""
            lines.append(f"  {emoji}{name} {close:.2f} {chg:+.2f}%{t20s}")
            idx_data[code] = {'chg': chg, 'close': close}
        else:
            lines.append(f"  {name}: N/A")

    # 回填 A股微观标题日期
    if trade_date:
        lines[a_stock_header_idx] = f"━━ 4. A股微观({trade_date}) ━━"

    # 沪深300 交叉校验 (iFind)
    if at and '000300.SH' in idx_data:
        log("拉 iFind 沪深300 校验...")
        tables = ifind_rt(at, '000300.SH')
        if tables:
            ifind_300 = tables[0]['table'].get('latest', [None])[0]
            if ifind_300:
                ts_300 = idx_data['000300.SH']['close']
                diff = abs(ts_300 - ifind_300)
                lines.append(f"  ✅ 沪深300校验 TS={ts_300:.2f} iFind={ifind_300:.2f} 差{diff:.2f}" if diff < 5 else f"  ⚠️ 沪深300校验 TS={ts_300:.2f} iFind={ifind_300:.2f} 差{diff:.2f}")

    # 全A成交额 (amount单位=千元，除以100000=亿)
    log("拉全A成交额...")
    d = ts('index_daily', {'ts_code': '000985.CSI', 'start_date': s20, 'end_date': end})
    if d:
        d.sort(key=lambda x: x['trade_date'], reverse=True)
        amt = float(d[0]['amount']) / 100000  # 千元→亿
        lines.append(f"全A成交额({d[0]['trade_date']}): {amt:.0f}亿")

    # 涨跌家数
    up_ratio = 0.5
    if trade_date:
        log(f"拉涨跌家数({trade_date})...")
        d = ts('daily', {'trade_date': trade_date}, fields='ts_code,pct_chg')
        if d:
            ups = sum(1 for r in d if float(r['pct_chg']) > 0)
            downs = sum(1 for r in d if float(r['pct_chg']) < 0)
            total_stocks = len(d)
            ratio = ups/downs if downs > 0 else 0
            up_ratio = ups / total_stocks if total_stocks > 0 else 0.5
            lines.append(f"涨跌家数: 涨{ups} 跌{downs} 比{ratio:.2f}")

    # 涨跌停
    if trade_date:
        log("拉涨跌停...")
        d = ts('limit_list_d', {'trade_date': trade_date})
        if d:
            zt = sum(1 for r in d if r.get('limit') == 'U')
            dt = sum(1 for r in d if r.get('limit') == 'D')
            lines.append(f"涨停{zt} 跌停{dt}")

    # 北向 (north_money单位=百万元，除以100=亿)
    log("拉北向...")
    d = ts('moneyflow_hsgt', {'start_date': s20, 'end_date': end})
    if d:
        d.sort(key=lambda x: x['trade_date'], reverse=True)
        north = float(d[0]['north_money']) / 100  # 百万→亿
        n5 = sum(float(d[i]['north_money']) for i in range(min(5,len(d)))) / 100
        n20 = sum(float(d[i]['north_money']) for i in range(min(20,len(d)))) / 100
        lines.append(f"北向({d[0]['trade_date']}): 当日{north:.1f}亿 5日{n5:.1f}亿 20日{n20:.1f}亿")

    # 两融
    log("拉两融...")
    total, ptotal = 0, 0
    sse = ts('margin', {'exchange_id': 'SSE', 'start_date': s20, 'end_date': end})
    szse = ts('margin', {'exchange_id': 'SZSE', 'start_date': s20, 'end_date': end})
    if sse and szse:
        sse.sort(key=lambda x: x['trade_date'], reverse=True)
        szse.sort(key=lambda x: x['trade_date'], reverse=True)
        total = (float(sse[0]['rzye']) + float(szse[0]['rzye'])) / 1e8
        ptotal = (float(sse[1]['rzye']) + float(szse[1]['rzye'])) / 1e8
        lines.append(f"两融余额({sse[0]['trade_date']}): {total:.0f}亿({cs(total-ptotal,'.0f')}亿)")
    lines.append("")

    # ═══ 5. 结论 ═══
    lines.append("━━ 5. 结论 ━━")
    try:
        chg300 = idx_data.get('000300.SH', {}).get('chg', 0)
        chg2000 = idx_data.get('932000.CSI', {}).get('chg', 0)

        lines.append(f"• {'存量博弈' if up_ratio < 0.4 else '增量入场' if up_ratio > 0.6 else '中性'}")
        lines.append(f"• {'Risk-OFF' if chg300 < -0.5 and up_ratio < 0.4 else 'Risk-ON' if chg300 > 0.5 and up_ratio > 0.6 else '中性'}")
        if abs(chg300 - chg2000) > 0.3:
            lines.append(f"• 风格: {'大盘占优' if chg300 > chg2000 else '小盘占优'}")
        else:
            lines.append(f"• 风格: 均衡")

        alerts = []
        if up_ratio < 0.35: alerts.append(f"涨跌比极端({up_ratio:.0%})")
        if total and ptotal and (total - ptotal) < -200: alerts.append(f"两融大幅缩减({total-ptotal:.0f}亿)")
        if alerts:
            lines.append("🔴 红灯: " + " | ".join(alerts))
        else:
            lines.append("✅ 无红灯事件")
    except Exception as e:
        lines.append(f"  结论生成失败: {e}")

    # 数据源标注
    lines.append("")
    lines.append(f"数据源: Tushare{'+ iFind' if at else '(iFind不可用)'}")

    report = '\n'.join(lines)
    print(report)
    with open('/tmp/fof_report.txt', 'w') as f:
        f.write(report)
    log("[已保存到 /tmp/fof_report.txt]")
    return report

if __name__ == '__main__':
    run()
