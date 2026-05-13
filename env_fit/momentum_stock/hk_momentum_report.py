#!/usr/bin/env python3
"""港股强势股日报生成器

数据源：
  - Tushare hk_daily: 全量港股日线（涨跌幅、成交额）
  - Tushare hk_basic: 上市日期、市场板块
  - iFinD get_stock_info: 流通市值、行业（对 Top N 补充）

筛选逻辑：
  - 日成交额 >500万港币（排除僵尸股）
  - 涨幅 Top 15 + 跌幅 Top 15
  - 按市值分档：大票(>200亿) / 中票(50-200亿) / 小票(<50亿)
  - 新股标记（上市<30天）
  - 行业标签（iFinD 补充）
"""
import os, sys, json, subprocess, requests
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
IFIND_DIR = os.path.expanduser('~/.openclaw/extensions/ifind-finance-data')

# ─── Tushare ───
TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_API = 'https://api.tushare.pro'


def ts_call(api_name, params, fields=''):
    """调用 Tushare API"""
    try:
        r = requests.post(TUSHARE_API, json={
            'api_name': api_name, 'token': TUSHARE_TOKEN,
            'params': params, 'fields': fields
        }, timeout=20)
        d = r.json()
        if d.get('code') != 0:
            print(f'  ⚠ Tushare [{api_name}]: {d.get("msg")}')
            return None
        data = d.get('data', {})
        fields_list = data.get('fields', [])
        items = data.get('items', [])
        return [dict(zip(fields_list, row)) for row in items]
    except Exception as e:
        print(f'  ⚠ Tushare 调用失败: {e}')
        return None


def call_ifind(tool, params):
    """调用 iFinD MCP（Node.js）"""
    try:
        script = f"""
const {{ call }} = require('{IFIND_DIR}/call-node.js');
call('stock', '{tool}', {json.dumps(params, ensure_ascii=False)})
  .then(r => console.log(JSON.stringify(r)))
  .catch(e => console.error(e.message));
"""
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if data.get('ok'):
            return data.get('data')
        return None
    except:
        return None


def parse_ifind_text(raw):
    """解析 iFinD 返回的 markdown 表格文本"""
    if not raw:
        return {}
    try:
        content = raw.get('result', {}).get('content', [])
        if not content:
            return {}
        text = content[0].get('text', '')
        inner = json.loads(text)
        answer = inner.get('data', {}).get('answer', '')
        return {'answer': answer}
    except:
        return {}


def get_latest_trade_date():
    """获取最近的港股交易日"""
    today = date.today()
    # 尝试今天和前几天
    for delta in range(0, 5):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:  # 跳过周末
            continue
        ds = d.strftime('%Y%m%d')
        data = ts_call('hk_daily', {'trade_date': ds}, fields='ts_code')
        if data and len(data) > 100:
            return ds
    return today.strftime('%Y%m%d')


def fetch_hk_data(trade_date):
    """拉取港股全量日线 + 基本信息"""
    print(f'  拉取港股日线 ({trade_date})...')
    daily = ts_call('hk_daily', {'trade_date': trade_date})
    if not daily:
        return [], {}

    print(f'  共 {len(daily)} 只港股有交易')

    # 拉取基本信息（上市日期）
    print(f'  拉取港股基本信息...')
    basic = ts_call('hk_basic', {'list_status': 'L'})
    basic_map = {}
    if basic:
        for b in basic:
            basic_map[b['ts_code']] = b

    return daily, basic_map


def enrich_with_ifind(stocks, top_n=10):
    """用 iFinD 补充市值和行业（批量查询）"""
    import re, time
    n = min(len(stocks), top_n)
    print(f'  iFinD 补充市值/行业（{n} 只）...')

    if n == 0:
        return stocks

    names = [s.get('name', s['ts_code']) for s in stocks[:n]]

    # 批量查行业（一次最多查 5 只，避免超长）
    industry_map = {}
    for i in range(0, n, 5):
        batch = names[i:i+5]
        query = '、'.join(batch) + '的所属恒生行业名称'
        raw = call_ifind('get_stock_info', {'query': query})
        parsed = parse_ifind_text(raw)
        answer = parsed.get('answer', '')
        if answer:
            lines = answer.split('\n')
            for line in lines:
                if line.startswith('|') and '---' not in line and '证券代码' not in line:
                    cols = [c.strip() for c in line.split('|')]
                    # cols: ['', 代码, 名称, 行业, ...]
                    if len(cols) >= 4:
                        name_col = cols[2] if len(cols) > 2 else ''
                        ind_col = cols[3] if len(cols) > 3 else ''
                        if name_col and ind_col and ind_col not in ('', '所属恒生行业名称'):
                            industry_map[name_col] = ind_col
        time.sleep(0.3)

    # 批量查市值
    cap_map = {}
    for i in range(0, n, 5):
        batch = names[i:i+5]
        query = '、'.join(batch) + '的流通市值'
        raw = call_ifind('get_stock_info', {'query': query})
        parsed = parse_ifind_text(raw)
        answer = parsed.get('answer', '')
        if answer:
            lines = answer.split('\n')
            for line in lines:
                if line.startswith('|') and '---' not in line and '证券代码' not in line:
                    cols = [c.strip() for c in line.split('|')]
                    if len(cols) >= 4:
                        name_col = cols[2] if len(cols) > 2 else ''
                        cap_col = cols[3] if len(cols) > 3 else ''
                        cap_match = re.search(r'([0-9.]+)\s*(万亿|亿|万)', cap_col)
                        if cap_match and name_col:
                            val = float(cap_match.group(1))
                            unit = cap_match.group(2)
                            if unit == '万亿':
                                cap_map[name_col] = val * 1e12
                            elif unit == '亿':
                                cap_map[name_col] = val * 1e8
                            elif unit == '万':
                                cap_map[name_col] = val * 1e4
        time.sleep(0.3)

    # 合并到 stocks
    for s in stocks[:n]:
        name = s.get('name', '')
        s['market_cap'] = cap_map.get(name, 0)
        s['industry'] = industry_map.get(name, '未知')

    return stocks[:n]


def filter_and_rank(daily, basic_map, trade_date):
    """筛选 + 排序"""
    # 过滤条件：成交额 > 500万港币
    MIN_AMOUNT = 500  # Tushare amount 单位是千港币
    filtered = [d for d in daily if d.get('amount', 0) > MIN_AMOUNT and d.get('pct_chg') is not None]

    print(f'  成交额>500万筛选后: {len(filtered)} 只')

    # 补充基本信息
    for d in filtered:
        b = basic_map.get(d['ts_code'], {})
        d['name'] = b.get('name', d['ts_code'])
        d['list_date'] = b.get('list_date', '')
        d['market'] = b.get('market', '')

        # 判断新股
        if d['list_date']:
            try:
                ld = datetime.strptime(d['list_date'], '%Y%m%d').date()
                td = datetime.strptime(trade_date, '%Y%m%d').date()
                d['is_new'] = (td - ld).days < 30
            except:
                d['is_new'] = False
        else:
            d['is_new'] = False

    # 按涨跌幅排序
    up = sorted(filtered, key=lambda x: x.get('pct_chg', 0), reverse=True)[:15]
    down = sorted(filtered, key=lambda x: x.get('pct_chg', 0))[:15]

    return up, down


def format_stock_line(s):
    """格式化单只股票行"""
    pct = s.get('pct_chg', 0)
    amount_m = s.get('amount', 0) / 1000  # 千港币 → 百万港币
    name = s.get('name', s['ts_code'])
    code = s['ts_code']
    industry = s.get('industry', '')
    new_tag = ' [新股]' if s.get('is_new') else ''

    # 市值分档
    cap = s.get('market_cap', 0)
    if cap > 200e8:  # >200亿
        cap_label = '大'
    elif cap > 50e8:
        cap_label = '中'
    elif cap > 0:
        cap_label = '小'
    else:
        cap_label = ''

    cap_str = f' · {cap_label}票' if cap_label else ''
    ind_str = f' · {industry}' if industry and industry != '未知' else ''
    amt_str = f'{amount_m:.0f}百万' if amount_m > 0 else ''

    return f"- {name}({code}) {pct:+.2f}% | 成交{amt_str}{ind_str}{cap_str}{new_tag}"


def generate_report():
    """生成港股强势股日报 HTML"""
    today_str = date.today().strftime('%m/%d')

    # 获取最近交易日
    trade_date = get_latest_trade_date()
    td_display = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

    # 拉取数据
    daily, basic_map = fetch_hk_data(trade_date)
    if not daily:
        return f'<div style="padding:20px;color:#666">港股数据拉取失败（{td_display}）</div>'

    # 筛选排序
    up, down = filter_and_rank(daily, basic_map, trade_date)

    # iFinD 补充市值/行业（Top 10）
    up = enrich_with_ifind(up, top_n=10)
    down = enrich_with_ifind(down, top_n=10)

    # 构建 HTML
    C_BLACK = '#1a1a1a'
    C_GRAY = '#6b7280'
    C_BORDER = '#e5e7eb'
    C_RED = '#cc2929'
    C_GREEN = '#1a8a4a'

    def stock_html(s):
        pct = s.get('pct_chg', 0)
        color = C_RED if pct > 0 else C_GREEN
        name = s.get('name', s['ts_code'])
        code = s['ts_code']
        amount_m = s.get('amount', 0) / 1000
        industry = s.get('industry', '')
        new_tag = '<span style="background:#ff9800;color:#fff;font-size:9px;padding:1px 4px;border-radius:3px;margin-left:4px">新股</span>' if s.get('is_new') else ''

        cap = s.get('market_cap', 0)
        if cap > 200e8:
            cap_tag = '<span style="color:#4f46e5;font-size:10px"> 大票</span>'
        elif cap > 50e8:
            cap_tag = '<span style="color:#7c3aed;font-size:10px"> 中票</span>'
        elif cap > 0:
            cap_tag = '<span style="color:#94a3b8;font-size:10px"> 小票</span>'
        else:
            cap_tag = ''

        ind_str = f'<span style="color:{C_GRAY};font-size:11px"> · {industry}</span>' if industry and industry != '未知' else ''

        return f'''<div style="padding:6px 0;border-bottom:1px solid {C_BORDER};display:flex;justify-content:space-between;align-items:center">
<div><span style="font-weight:600;font-size:13px">{name}</span><span style="color:{C_GRAY};font-size:11px;margin-left:4px">{code}</span>{new_tag}{cap_tag}{ind_str}</div>
<div style="text-align:right"><span style="color:{color};font-weight:700;font-size:14px">{pct:+.2f}%</span><br><span style="color:{C_GRAY};font-size:10px">成交 {amount_m:.0f}百万</span></div>
</div>'''

    up_html = '\n'.join([stock_html(s) for s in up[:10]])
    down_html = '\n'.join([stock_html(s) for s in down[:10]])

    # 行业统计
    up_industries = {}
    for s in up[:10]:
        ind = s.get('industry', '未知')
        if ind and ind != '未知':
            up_industries[ind] = up_industries.get(ind, 0) + 1

    down_industries = {}
    for s in down[:10]:
        ind = s.get('industry', '未知')
        if ind and ind != '未知':
            down_industries[ind] = down_industries.get(ind, 0) + 1

    ind_up_str = ' · '.join([f'{k}({v})' for k, v in sorted(up_industries.items(), key=lambda x: -x[1])[:5]]) or '数据补充中'
    ind_down_str = ' · '.join([f'{k}({v})' for k, v in sorted(down_industries.items(), key=lambda x: -x[1])[:5]]) or '数据补充中'

    html = f'''<div style="font-size:13px;color:{C_BLACK}">
<div style="margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid {C_BLACK}">
<div style="font-size:11px;color:{C_GRAY}">交易日: {td_display} · 筛选: 成交额>500万港币 · 数据源: Tushare + iFinD</div>
</div>

<div style="font-weight:700;font-size:14px;margin-bottom:8px;color:{C_RED}">▲ 上涨异动 Top 10</div>
{up_html}

<div style="font-weight:700;font-size:14px;margin:16px 0 8px;color:{C_GREEN}">▼ 下跌异动 Top 10（做空机会）</div>
{down_html}

<div style="margin-top:16px;padding-top:12px;border-top:1px solid {C_BORDER}">
<div style="font-weight:600;font-size:12px;margin-bottom:4px">行业分布</div>
<div style="font-size:11px;color:{C_GRAY}">上涨集中: {ind_up_str}</div>
<div style="font-size:11px;color:{C_GRAY}">下跌集中: {ind_down_str}</div>
</div>

<div style="margin-top:12px;font-size:10px;color:#9ca3af">
港股无涨跌停限制，单日波动可能较大，注意风险控制
</div>
</div>'''

    return html


if __name__ == '__main__':
    html = generate_report()
    # 输出纯文本版本（用于终端预览）
    import re
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\n{3,}', '\n\n', text)
    print(text)
