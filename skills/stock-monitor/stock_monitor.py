#!/usr/bin/env python3
"""
个股监控 Skill - 每日盘后自动推送飞书卡片
内容：全量公告（减持加粗标红）+ 舆情 + 筹码结构

数据源：
- 公告/舆情：iFinD MCP (search_notice / search_news)
- 减持明细：Tushare stk_holdertrade
- 筹码结构：chip_query 模块
"""
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ── 路径 ──
SCRIPT_DIR = Path(__file__).parent.resolve()
WATCHLIST_PATH = SCRIPT_DIR / 'watchlist.json'


def _truncate_with_link(content: str, stock_name: str, title: str, max_len: int = 300) -> str:
    """内容超长时截断 + 加巨潮全文链接"""
    if not content or len(content) <= max_len:
        return content or "（无详细内容）"
    # 截断
    truncated = content[:max_len] + "..."
    # 巨潮搜索链接
    search_key = quote(f"{stock_name} {title[:20]}")
    link = f"http://www.cninfo.com.cn/new/fulltextSearch?searchkey={search_key}"
    truncated += f"\n\n[▶ 查看全文]({link})"
    return truncated

# GAMT 项目根目录（环境自适应）
def _find_gamt_root():
    candidates = [
        Path('/Users/apple/Desktop/gamt-dashboard'),
        Path('/home/ubuntu/gamt-dashboard'),
        Path.home() / 'Desktop' / 'gamt-dashboard',
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

GAMT_ROOT = _find_gamt_root()

# 添加 chip_query 到 path
sys.path.insert(0, str(GAMT_ROOT / 'chip_query'))
sys.path.insert(0, str(GAMT_ROOT / 'server'))

# ── 配置 ──
TUSHARE_TOKEN = '8a2c71af4fbc6faf83da2ad4404c1c47f41983562cc9fb2fa6dd4fae'
TUSHARE_URL = 'https://api.tushare.pro'

FEISHU_APP_ID = 'cli_a91c36caf5785cb2'
FEISHU_APP_SECRET = 'HWhYR833N0xObKumrjNCKdRSHq3jg0zi'

# iFinD MCP
IFIND_DIR = Path(os.path.expanduser('~/.openclaw/extensions/ifind-finance-data'))


def load_watchlist():
    with open(WATCHLIST_PATH, 'r') as f:
        return json.load(f)


# ══════════════════════════════════════════
# 数据拉取
# ══════════════════════════════════════════

def ts_query(api_name, **params):
    """Tushare API 调用"""
    body = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params,
    }
    resp = requests.post(TUSHARE_URL, json=body, timeout=30)
    data = resp.json()
    if data.get('code') != 0:
        return []
    items = data.get('data', {})
    if not items or not items.get('items'):
        return []
    fields = items['fields']
    return [dict(zip(fields, row)) for row in items['items']]


def get_holder_trades(ts_code: str, days: int = 7) -> list:
    """获取股东增减持明细（Tushare stk_holdertrade）"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    results = ts_query(
        'stk_holdertrade',
        ts_code=ts_code,
        start_date=start,
        end_date=end,
    )
    # 只保留减持
    reduces = [r for r in results if r.get('in_de') == 'DE']
    return reduces


def ifind_call(server_type: str, tool_name: str, params: dict) -> dict:
    """调用 iFinD MCP Node.js 接口"""
    call_script = IFIND_DIR / 'call-node.js'
    if not call_script.exists():
        return {'ok': False, 'error': 'iFinD call-node.js not found'}

    import subprocess
    # 构造临时调用脚本
    js_code = f"""
const {{ call }} = require('{call_script}');
async function main() {{
    const r = await call("{server_type}", "{tool_name}", {json.dumps(params)});
    process.stdout.write(JSON.stringify(r));
}}
main().catch(e => {{ console.error(e); process.exit(1); }});
"""
    result = subprocess.run(
        ['node', '-e', js_code],
        capture_output=True, text=True, timeout=60,
        cwd=str(IFIND_DIR)
    )
    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr[:500]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'ok': False, 'error': f'JSON parse failed: {result.stdout[:200]}'}


def _parse_ifind_response(result: dict) -> list:
    """
    解析 iFinD MCP 嵌套 JSON 响应。
    实际结构（4层）:
      r.data                          → {jsonrpc, result, id}
      r.data.result.content[0].text   → JSON string
      → parsed = {code, msg, data}
      → parsed['data']                → object: {data: JSON_STRING}
      → parsed['data']['data']        → JSON string → 最终 list
    """
    if not result.get('ok') or not result.get('data'):
        return []
    data = result['data']

    # 层1: jsonrpc wrapper
    if isinstance(data, dict) and 'result' in data:
        data = data['result']
    if isinstance(data, dict) and 'content' in data:
        content_list = data['content']
        if isinstance(content_list, list) and len(content_list) > 0:
            item = content_list[0]
            text = item.get('text', '') if isinstance(item, dict) else str(item)
            # 层2: text 是 JSON string → {code, msg, data}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return []

            # 提取 parsed['data']
            inner = parsed.get('data') if isinstance(parsed, dict) else parsed
            if isinstance(inner, list):
                return inner

            # 层3: inner 是 dict，里面还有 .data 字段
            if isinstance(inner, dict) and 'data' in inner:
                deep = inner['data']
                if isinstance(deep, str):
                    try:
                        return json.loads(deep)
                    except json.JSONDecodeError:
                        return []
                elif isinstance(deep, list):
                    return deep

            # 层3 备选: inner 本身是 JSON string
            if isinstance(inner, str):
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    return []

    if isinstance(data, list):
        return data
    return []


def _dedup_by_title(items: list, title_key: str) -> list:
    """按标题去重，保留每个标题的第一条"""
    seen = set()
    result = []
    for item in items:
        if isinstance(item, dict):
            title = item.get(title_key, '')
        else:
            title = str(item)[:80]
        if title and title not in seen:
            seen.add(title)
            result.append(item)
    return result


def get_notices(stock_name: str, days: int = 3) -> list:
    """获取个股公告（iFinD）。默认回看3天，避免周末/节假日空窗"""
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    result = ifind_call('news', 'search_notice', {
        'query': f'{stock_name}',
        'time_start': start,
        'time_end': end,
        'size': 10,
    })
    items = _parse_ifind_response(result)
    return _dedup_by_title(items, '公告标题')


def get_news(stock_name: str, days: int = 3) -> list:
    """获取个股舆情（iFinD）。默认回看3天"""
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    result = ifind_call('news', 'search_news', {
        'query': f'{stock_name}',
        'time_start': start,
        'time_end': end,
        'size': 8,
    })
    items = _parse_ifind_response(result)
    return _dedup_by_title(items, '资讯标题')


def get_chip_data(ts_code: str, days: int = 60) -> dict:
    """获取筹码结构"""
    try:
        from chip_api import analyze_stock
        return analyze_stock(ts_code, days=days)
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ══════════════════════════════════════════
# 飞书卡片构建
# ══════════════════════════════════════════

def get_feishu_token():
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': FEISHU_APP_ID, 'app_secret': FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    return data.get('tenant_access_token')


def _build_ma_section(analysis_path: str) -> list:
    """从并购重组底稿中提取关键信息，构建卡片区块"""
    full_path = SCRIPT_DIR / analysis_path
    if not full_path.exists():
        return []

    content = full_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # 提取状态
    status = "未知"
    for line in lines:
        if '当前状态' in line and '**' in line:
            # 格式: **当前状态：** ⚠️ 终止...
            parts = line.split('**')
            for i, p in enumerate(parts):
                if '当前状态' in p and i + 1 < len(parts):
                    status = parts[i + 1].strip()
                    if not status:
                        # 值在 ** 之后
                        status = ''.join(parts[i + 2:]).strip()
                    break
            if status == "未知":
                # fallback: 取冒号后面的内容
                if '：' in line:
                    status = line.split('：', 1)[-1].strip().strip('*').strip()
            break

    # 提取表格字段（格式: | **字段名** | 值 |）
    def extract_table_field(key):
        for line in lines:
            if f'**{key}**' in line and '|' in line:
                cells = [c.strip() for c in line.split('|') if c.strip()]
                if len(cells) >= 2:
                    # 第二个 cell 是值
                    return cells[1].strip()
            elif f'**{key}' in line and '：' in line and '|' not in line:
                # 非表格格式: **字段名：** 值
                val = line.split('：', 1)[-1].strip().rstrip('*').strip()
                return val
        return ''

    trade_type = extract_table_field('交易类型')
    seller = extract_table_field('卖方')
    buyer = extract_table_field('买方')
    target = extract_table_field('标的资产')
    reason = extract_table_field('终止原因（公告口径）') or extract_table_field('终止原因')

    # 提取当前结论（第九部分）
    conclusion = ""
    in_conclusion = False
    for line in lines:
        if '当前结论' in line or '九、当前结论' in line:
            in_conclusion = True
            # 同一行可能有内容
            after = line.split('当前结论')[1] if '当前结论' in line else ''
            after = after.strip().strip('*').strip('.').strip()
            if after:
                conclusion = after
                break
            continue
        if in_conclusion and line.strip() and not line.startswith('#') and not line.startswith('---'):
            conclusion = line.strip().strip('*').strip()
            break

    # 提取收购结构图（```代码块内容）
    structure_block = ""
    in_code = False
    for line in lines:
        if '收购结构图' in line:
            in_code = True
            continue
        if in_code:
            if line.strip() == '```':
                if structure_block:
                    break
                continue
            if line.startswith('```'):
                continue
            structure_block += line + "\n"
            if '未披露' in line or '买方' in line:
                # 读到结构图末尾
                # 继续读几行
                pass

    # 构建卡片内容
    ma_lines = ["**▬▬▬ 并购重组进展 ▬▬▬**"]
    ma_lines.append(f"状态：{status}")

    if trade_type:
        ma_lines.append(f"类型：{trade_type}")

    # 收购结构图（文本版）
    if structure_block.strip():
        ma_lines.append("**【收购结构】**")
        for sl in structure_block.strip().split('\n')[:8]:
            ma_lines.append(sl)
    else:
        ma_lines.append("**【收购结构】**")
        ma_lines.append(f"  卖方：{seller or '未知'}")
        ma_lines.append(f"  └─→ 买方：{buyer or '未披露'}")
        if target:
            ma_lines.append(f"  标的：{target}")

    if reason:
        ma_lines.append(f"终止原因：{reason}")

    # 提取路径推演（```代码块）
    path_block = ""
    in_path = False
    for line in lines:
        if '最可能路径推演' in line:
            in_path = True
            continue
        if in_path:
            if line.strip() == '```':
                if path_block:
                    break
                continue
            if line.startswith('```'):
                continue
            path_block += line + "\n"

    if path_block.strip():
        ma_lines.append("")
        ma_lines.append("**【路径推演】**")
        for pl in path_block.strip().split('\n')[:10]:
            ma_lines.append(pl)

    # 提取估值核心结论
    valuation_conclusion = []
    in_val = False
    for line in lines:
        if '### 核心结论' in line:
            in_val = True
            continue
        if in_val:
            if line.startswith('#') or line.startswith('---'):
                break
            if line.strip().startswith('- '):
                valuation_conclusion.append(line.strip())

    if valuation_conclusion:
        ma_lines.append("")
        ma_lines.append("**【估值判断】**")
        for vc in valuation_conclusion[:4]:
            ma_lines.append(vc)

    if conclusion:
        ma_lines.append("")
        ma_lines.append(f"**判断：{conclusion}**")

    return ma_lines


def build_card(stock: dict, holder_trades: list, notices: list, news: list, chip: dict) -> dict:
    """构建飞书消息卡片"""
    ts_code = stock['ts_code']
    name = stock['name']
    today = datetime.now().strftime('%Y-%m-%d')
    focus_keywords = stock.get('focus', ['减持', '定增', '可转债', '增发', '配股'])
    # capital_keywords 合并 focus + 通用关键词
    capital_keywords = list(set(focus_keywords + ['减持', '定增', '可转债', '增发', '配股', '回购', '质押', '并购', '收购', '重大资产重组', '筹划', '重大事项', '股份转让', '实控人变更', '控制权']))

    elements = []

    # ── 标题 ──
    header = {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**■ {name} ({ts_code}) · {today}**"
        }
    }
    elements.append(header)
    elements.append({"tag": "hr"})

    # ── 重大资本运作（始终展开）──
    # 合并：Tushare 减持明细 + 公告中含资本运作关键词的
    capital_notices = []
    other_notices = []
    for n in notices:
        if isinstance(n, dict):
            title = n.get('公告标题', n.get('title', ''))
        else:
            title = str(n)[:80]
        if any(kw in title for kw in capital_keywords):
            capital_notices.append(n)
        else:
            other_notices.append(n)

    # 也检查舆情中的资本运作信息
    capital_news = []
    other_news = []
    for n in news:
        if isinstance(n, dict):
            title = n.get('资讯标题', n.get('新闻标题', n.get('title', '')))
        else:
            title = str(n)[:80]
        if any(kw in title for kw in capital_keywords):
            capital_news.append(n)
        else:
            other_news.append(n)

    has_capital = len(holder_trades) > 0 or len(capital_notices) > 0 or len(capital_news) > 0

    capital_lines = ["<font color='red'>**⚠️ 重大资本运作**</font>"]
    if has_capital:
        # Tushare 减持明细
        for t in holder_trades[:5]:
            holder = t.get('holder_name', '未知')
            vol = t.get('vol', 0)
            vol_str = f"{vol/10000:.1f}万股" if vol and vol > 10000 else f"{vol}股"
            price = t.get('avg_price', '-')
            method = t.get('trade_type', '-')
            date = t.get('ann_date', '-')
            line = f"<font color='red'>**● {holder}** 减持 {vol_str}  均价:{price}元  方式:{method}  ({date})</font>"
            capital_lines.append(line)
        # 公告中的资本运作（标题标红）
        for n in capital_notices[:5]:
            title = n.get('公告标题', n.get('title', '')) if isinstance(n, dict) else str(n)[:80]
            capital_lines.append(f"<font color='red'>**● {title}**</font>")
        # 舆情中的资本运作（标题标红）
        for n in capital_news[:3]:
            title = n.get('资讯标题', n.get('title', '')) if isinstance(n, dict) else str(n)[:80]
            capital_lines.append(f"<font color='red'>**● {title}**</font>")
    else:
        capital_lines.append("<font color='red'>当日无重大资本运作公告（减持/定增/可转债）</font>")

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(capital_lines)}
    })

    # 重大资本运作的详细内容（可折叠）
    if has_capital:
        for n in (capital_notices[:5] + capital_news[:3]):
            if isinstance(n, dict):
                title = n.get('公告标题', n.get('资讯标题', n.get('title', '')))
                date = n.get('日期', n.get('date', ''))
                content = n.get('公告片段内容', n.get('资讯内容', n.get('content', '')))
                display_title = f"● {title} ({date})" if date else f"● {title}"
                if not content:
                    content = "（无详细内容）"
                elements.append({
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": display_title[:60]
                        }
                    },
                    "border": {"color": "red"},
                    "elements": [{
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": _truncate_with_link(content, stock["name"], title)}
                    }]
                })

    elements.append({"tag": "hr"})

    # ── 当日公告（标题直接展示，内容可折叠）──
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**▬▬▬ 当日公告（{len(other_notices)}条）▬▬▬**"}
    })
    if other_notices:
        for n in other_notices[:8]:
            if isinstance(n, dict):
                title = n.get('公告标题', n.get('title', ''))
                date = n.get('日期', n.get('date', ''))
                content = n.get('公告片段内容', n.get('content', ''))
                display_title = f"● {title} ({date})" if date else f"● {title}"
            else:
                display_title = f"● {str(n)[:80]}"
                content = ''
            if content:
                # 标题 + 内容折叠
                elements.append({
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": display_title[:60]
                        }
                    },
                    "border": {"color": "grey"},
                    "elements": [{
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": _truncate_with_link(content, stock["name"], title)}
                    }]
                })
            else:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": display_title}
                })
    else:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "暂无其他公告"}
        })
    elements.append({"tag": "hr"})

    # ── 舆情动态（标题直接展示，内容可折叠）──
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"**▬▬▬ 舆情动态（{len(other_news)}条）▬▬▬**"}
    })
    if other_news:
        for n in other_news[:8]:
            if isinstance(n, dict):
                title = n.get('资讯标题', n.get('新闻标题', n.get('标题', n.get('title', ''))))
                date = n.get('日期', n.get('date', ''))
                content = n.get('资讯内容', n.get('新闻内容', n.get('content', '')))
                if not title:
                    title = str(n)[:80]
                display_title = f"● {title} ({date})" if date else f"● {title}"
            else:
                display_title = f"● {str(n)[:80]}"
                content = ''
            if content:
                elements.append({
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": display_title[:60]
                        }
                    },
                    "border": {"color": "grey"},
                    "elements": [{
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": _truncate_with_link(content, stock["name"], title)}
                    }]
                })
            else:
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": display_title}
                })
    else:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "暂无舆情"}
        })

    # ── 筹码结构（始终展开）──
    if chip.get('success'):
        c = chip['chip']
        mf = chip.get('moneyflow', {})
        big = chip.get('big_order_stats', {}).get('by_window', {})
        lookback = chip.get('lookback_days', 60)

        main_5d = mf.get('main_net_5d')
        main_10d = mf.get('main_net_10d')
        main_5d_str = f"{main_5d/10000:.0f}万" if main_5d else '-'
        main_10d_str = f"{main_10d/10000:.0f}万" if main_10d else '-'

        # 筹码分布
        chip_lines = [
            f"**▬▬▬ 筹码结构（{lookback}日）▬▬▬**",
            f"现价 {c.get('current_price','-')} | {lookback}日均成本 {c.get('avg_cost','-')} | 中位成本 {c.get('median_cost','-')}",
            f"获利盘 {round(c.get('profit_ratio',0)*100,1)}% | 套牢盘 {round(c.get('locked_ratio',0)*100,1)}%",
            f"70%筹码集中区 {c.get('range_70','-')}",
            f"90%筹码集中区 {c.get('range_90','-')}",
            f"峰值价 {c.get('peak_price','-')} | 距峰值 {'+' if c.get('peak_distance',0)>=0 else ''}{c.get('peak_distance','-')}%",
        ]
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(chip_lines)}
        })

        # 资金流向
        flow_lines = [
            "**▬▬▬ 资金流向 ▬▬▬**",
            f"主力5日净流入 {main_5d_str} | 10日净流入 {main_10d_str}",
        ]
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(flow_lines)}
        })

        # 大单监控
        big_30 = big.get('30', {})
        big_60 = big.get('60', {})
        if big_30:
            is_big_today = "是" if big_30.get('latest_is_big') else "否"
            zscore = big_30.get('latest_ratio_zscore', 0)
            # 大白话标签
            if zscore >= 2:
                zscore_label = "极度活跃"
            elif zscore >= 1:
                zscore_label = "偏活跃"
            elif zscore >= -1:
                zscore_label = "正常"
            else:
                zscore_label = "偏冷清"

            big_lines = [
                "**▬▬▬ 大单监控 ▬▬▬**",
                f"近30日异常大单天数：{big_30.get('big_days','-')}天 | 近60日：{big_60.get('big_days','-')}天",
                f"最新大单占比：{round(big_30.get('latest_big_ratio',0)*100,1)}%（Z-score: {zscore}，{zscore_label}）",
                f"当日是否大单日：{is_big_today}",
                f"30日主力净额：{big_30.get('net_sum',0)/10000:.0f}万 | 60日：{big_60.get('net_sum',0)/10000:.0f}万",
                "",
                "*大单=单笔≥20万成交（含超大单）；异常大单日=占比超30日80%分位；Z-score>2极度活跃，<-1偏冷清*",
            ]
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(big_lines)}
            })

    # ── 并购重组进展（B类票专属）──
    analysis_path = stock.get('analysis')
    if analysis_path:
        ma_lines = _build_ma_section(analysis_path)
        if ma_lines:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(ma_lines)}
            })

    # 构建完整卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"{name} 每日监控"
            },
            "template": "red" if has_capital else "blue"
        },
        "elements": elements
    }
    return card


def send_feishu_card(chat_id: str, card: dict):
    """发送飞书卡片消息"""
    token = get_feishu_token()
    if not token:
        print("[ERROR] 获取飞书 token 失败")
        return False

    resp = requests.post(
        'https://open.feishu.cn/open-apis/im/v1/messages',
        params={'receive_id_type': 'chat_id'},
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json={
            'receive_id': chat_id,
            'msg_type': 'interactive',
            'content': json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get('code') == 0:
        print(f"[OK] 飞书卡片发送成功 → {chat_id}")
        return True
    else:
        print(f"[ERROR] 飞书发送失败: {data}")
        return False


# ══════════════════════════════════════════
# 增量机制
# ══════════════════════════════════════════

LAST_RUN_PATH = SCRIPT_DIR / 'last_run.json'


def load_last_run() -> dict:
    """读取上次运行记录"""
    if LAST_RUN_PATH.exists():
        with open(LAST_RUN_PATH, 'r') as f:
            return json.load(f)
    return {}


def save_last_run(data: dict):
    """保存本次运行记录"""
    with open(LAST_RUN_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calc_news_days(last_run: dict) -> int:
    """根据上次运行时间计算需要回看的天数"""
    last_time = last_run.get('last_run_time')
    if not last_time:
        return 3  # 首次运行，回看3天
    try:
        last_dt = datetime.strptime(last_time, '%Y-%m-%d %H:%M:%S')
        delta = (datetime.now() - last_dt).days
        # 至少1天，最多7天（防止长时间没跑后拉太多）
        return max(1, min(delta + 1, 7))
    except (ValueError, TypeError):
        return 3


# ══════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════

def run_monitor(dry_run=False):
    """主入口：遍历 watchlist，拉数据，发卡片"""
    config = load_watchlist()
    stocks = config['stocks']
    settings = config['settings']
    chat_id = settings['feishu_chat_id']
    lookback = settings.get('lookback_days', 60)

    # 增量：根据上次运行时间决定回看天数
    last_run = load_last_run()
    news_days = calc_news_days(last_run)

    print(f"[stock-monitor] 开始运行，监控 {len(stocks)} 只股票")
    print(f"[stock-monitor] 飞书群: {chat_id}")
    print(f"[stock-monitor] 回看天数: {news_days}（上次运行: {last_run.get('last_run_time', '首次')}）")

    for stock in stocks:
        ts_code = stock['ts_code']
        name = stock['name']
        print(f"\n{'='*40}")
        print(f"处理: {name} ({ts_code})")

        # 1. 减持明细
        print("  拉取减持明细...")
        holder_trades = get_holder_trades(ts_code, days=7)
        print(f"  → 减持记录: {len(holder_trades)} 条")

        # 2. 公告
        print("  拉取公告...")
        notices = get_notices(name, days=news_days)
        print(f"  → 公告: {len(notices)} 条")

        # 3. 舆情
        print("  拉取舆情...")
        news = get_news(name, days=news_days)
        print(f"  → 舆情: {len(news)} 条")

        # 4. 筹码
        print("  计算筹码结构...")
        chip = get_chip_data(ts_code, days=lookback)
        print(f"  → 筹码: {'成功' if chip.get('success') else '失败'}")

        # 5. 构建卡片
        card = build_card(stock, holder_trades, notices, news, chip)

        # 6. 生成前端数据 JSON
        detail_dir = SCRIPT_DIR / 'detail'
        detail_dir.mkdir(exist_ok=True)
        code_short = ts_code.split('.')[0]
        detail_data = {
            'ts_code': ts_code,
            'name': name,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'type': 'B' if stock.get('analysis') else 'A',
            'holder_trades': holder_trades,
            'notices': notices,
            'news': news,
            'chip': chip,
            'analysis': None,
        }
        # B类票加载底稿
        if stock.get('analysis'):
            analysis_path = SCRIPT_DIR / stock['analysis']
            if analysis_path.exists():
                detail_data['analysis'] = analysis_path.read_text(encoding='utf-8')
        with open(detail_dir / f'{code_short}.json', 'w', encoding='utf-8') as f:
            json.dump(detail_data, f, ensure_ascii=False, indent=2)

        if dry_run:
            print(f"\n[DRY RUN] 卡片内容:")
            print(json.dumps(card, ensure_ascii=False, indent=2)[:2000])
        else:
            send_feishu_card(chat_id, card)

    print(f"\n[stock-monitor] 完成")

    # 保存运行记录（增量用）
    if not dry_run:
        save_last_run({
            'last_run_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stocks_count': len(stocks),
            'news_days_used': news_days,
        })


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='个股监控 - 每日飞书推送')
    parser.add_argument('--dry', action='store_true', help='预览模式，不实际发送')
    args = parser.parse_args()
    run_monitor(dry_run=args.dry)
