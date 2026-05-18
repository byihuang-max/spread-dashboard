#!/usr/bin/env python3
"""
并购深度分析报告生成器

功能：
1. 筹码峰分析（每次都重算，因为价格每天变）
2. B 类底稿生成/增量更新（Kimi 搜索 + Claude 结构化）
3. 输出 JSON（供前端 merger_detail.html 读取）

调用方式：
  python3 generate_merger_report.py --code 002176.SZ
  python3 generate_merger_report.py --code 002176.SZ --chip-only   # 只跑筹码
  python3 generate_merger_report.py --code 002176.SZ --report-only # 只跑底稿
  python3 generate_merger_report.py --auto                         # 自动跑异动 Top 8

输出：
  detail/{code}.json  — 前端读取的完整数据（筹码+底稿+元信息）
  analysis/{name}_并购重组跟踪.md — B 类底稿 markdown

成本：
  筹码：¥0（Tushare + iFinD）
  底稿首次：~¥0.50（Kimi 8-12次 + Claude 1次）
  底稿增量：~¥0.15（Kimi 2-3次 + Claude 1次）
"""
import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DETAIL_DIR = SCRIPT_DIR / 'detail'
ANALYSIS_DIR = SCRIPT_DIR / 'analysis'
POOL_PATH = SCRIPT_DIR / 'merger_pool.json'
REACTIONS_PATH = SCRIPT_DIR / 'backtest_output' / 'merger_reactions.json'

DETAIL_DIR.mkdir(exist_ok=True)
ANALYSIS_DIR.mkdir(exist_ok=True)

# ── 路径设置 ──
def _find_gamt_root():
    candidates = [
        Path('/Users/apple/Desktop/gamt-dashboard'),
        Path('/home/ubuntu/gamt-dashboard'),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

GAMT_ROOT = _find_gamt_root()
sys.path.insert(0, str(GAMT_ROOT / 'server'))
sys.path.insert(0, str(GAMT_ROOT / 'chip_query'))

# ── API 配置（从 config/api_keys.json 读取）──
def _load_api_config():
    config_path = SCRIPT_DIR / 'config' / 'api_keys.json'
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}

_API_CONFIG = _load_api_config()
KIMI_API_KEY = _API_CONFIG.get('kimi_api_key', '')
KIMI_BASE_URL = _API_CONFIG.get('kimi_base_url', 'https://api.moonshot.cn/v1')
CLAUDE_API_KEY = _API_CONFIG.get('claude_api_key', '')
CLAUDE_BASE_URL = _API_CONFIG.get('claude_base_url', 'https://api.aicanapi.com/v1')
CLAUDE_MODEL = _API_CONFIG.get('claude_model', 'claude-opus-4-6')

# ── iFinD MCP ──
IFIND_DIR = Path(os.path.expanduser('~/.openclaw/extensions/ifind-finance-data'))


# ═══════════════════════════════════════════════════
# Part 1: 筹码峰分析
# ═══════════════════════════════════════════════════

def run_chip_analysis(ts_code: str) -> dict:
    """调用 chip_api.analyze_stock 获取筹码数据"""
    try:
        from chip_api import analyze_stock
        result = analyze_stock(ts_code, days=120)
        if result.get('success'):
            return result
        else:
            print(f"  [筹码] 分析失败: {result.get('error')}")
            return None
    except Exception as e:
        print(f"  [筹码] 异常: {e}")
        return None


# ═══════════════════════════════════════════════════
# Part 2: Kimi 联网搜索
# ═══════════════════════════════════════════════════

def kimi_search(query: str, max_retries: int = 2) -> str:
    """调用 Kimi 联网搜索，返回文本结果"""
    headers = {
        'Authorization': f'Bearer {KIMI_API_KEY}',
        'Content-Type': 'application/json',
    }

    messages = [
        {'role': 'user', 'content': query}
    ]

    payload = {
        'model': 'moonshot-v1-128k',
        'messages': messages,
        'tools': [{'type': 'builtin_function', 'function': {'name': '$web_search'}}],
        'temperature': 0.3,
    }

    for attempt in range(max_retries + 1):
        try:
            # Step 1: 发送请求，可能触发 tool_calls
            resp = requests.post(
                f'{KIMI_BASE_URL}/chat/completions',
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data['choices'][0]
            msg = choice['message']

            # 如果有 tool_calls，需要第二轮
            if msg.get('tool_calls'):
                tool_call = msg['tool_calls'][0]
                tool_id = tool_call['id']
                # 搜索结果在 content 里（Kimi 特殊处理）
                search_result = msg.get('content', '') or ''

                # 第二轮：把搜索结果喂回去
                messages_round2 = messages + [
                    msg,  # assistant with tool_calls
                    {
                        'role': 'tool',
                        'tool_call_id': tool_id,
                        'content': search_result,
                    }
                ]
                payload2 = {
                    'model': 'moonshot-v1-128k',
                    'messages': messages_round2,
                    'temperature': 0.3,
                }
                resp2 = requests.post(
                    f'{KIMI_BASE_URL}/chat/completions',
                    headers=headers,
                    json=payload2,
                    timeout=60,
                )
                resp2.raise_for_status()
                data2 = resp2.json()
                return data2['choices'][0]['message']['content']
            else:
                return msg.get('content', '')

        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            print(f"  [Kimi] 搜索失败: {e}")
            return ''


def kimi_search_batch(queries: list) -> list:
    """批量 Kimi 搜索，带间隔"""
    results = []
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(1.5)  # 避免频率限制
        print(f"  [Kimi] ({i+1}/{len(queries)}) {q[:40]}...")
        result = kimi_search(q)
        results.append(result)
    return results


# ═══════════════════════════════════════════════════
# Part 3: Claude 结构化输出
# ═══════════════════════════════════════════════════

def claude_generate_report(stock_name: str, code: str, context: str, existing_report: str = None) -> str:
    """调用 Claude 生成/更新底稿（Anthropic Messages API）"""
    if not CLAUDE_API_KEY:
        print("  [Claude] 未配置 API Key，跳过底稿生成")
        return None

    headers = {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
    }

    if existing_report:
        prompt = f"""你是一个并购重组分析师。以下是 {stock_name}（{code}）的现有底稿和最新搜索信息。
请基于新信息增量更新底稿，保留原有结构，只修改/补充有变化的部分。

【现有底稿】
{existing_report}

【最新信息】
{context}

请输出更新后的完整 markdown 底稿。保持原有模板结构（事件时间线/交易结构/控股股东画像/公司基本面/潜在买方/估值/进度判断/收购路径推演）。"""
    else:
        prompt = f"""你是一个并购重组分析师。请根据以下搜索结果，为 {stock_name}（{code}）生成一份完整的并购重组跟踪底稿。

【搜索结果汇总】
{context}

请按以下结构输出 markdown 底稿：
1. 事件时间线（表格）
2. 交易结构（买方/卖方/标的/对价/支付方式）
3. 控股股东画像（实控人/持股/质押/减持）
4. 公司基本面（营收/利润/主营/估值）
5. 潜在买方分析（如未披露）
6. 估值参考
7. 进度判断（当前阶段/成功概率/风险点）
8. 收购路径推演（最可能路径 + 备选路径）

标题格式：# {stock_name}（{code}）并购重组跟踪底稿
开头加更新日期。未知信息标注"待披露"。"""

    payload = {
        'model': CLAUDE_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 4096,
    }

    try:
        resp = requests.post(
            f'{CLAUDE_BASE_URL}/v1/messages',
            headers=headers,
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        # Anthropic Messages API 格式
        content = data.get('content', [])
        if content and content[0].get('type') == 'text':
            return content[0]['text']
        return None
    except Exception as e:
        print(f"  [Claude] 生成失败: {e}")
        return None


# ═══════════════════════════════════════════════════
# Part 4: iFinD 公告/新闻
# ═══════════════════════════════════════════════════

def ifind_search(stock_name: str, code: str, days: int = 30) -> dict:
    """通过 iFinD MCP 搜索最近公告和新闻"""
    results = {'notices': [], 'news': []}

    config_path = IFIND_DIR / 'mcp_config.json'
    if not config_path.exists():
        return results

    try:
        config = json.loads(config_path.read_text())
        headers = config.get('headers', {})
        base_url = 'https://api-mcp.51ifind.com:8643/ds-mcp-servers'

        # 搜索公告
        payload = {
            'method': 'tools/call',
            'params': {
                'name': 'search_notice',
                'arguments': {
                    'keyword': f'{stock_name} 并购 重组',
                    'count': 10,
                }
            }
        }
        resp = requests.post(f'{base_url}/news/message', headers=headers, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            # 解析 iFinD 嵌套响应
            content = _parse_ifind_response(data)
            if content:
                results['notices'] = content[:5]

        # 搜索新闻
        time.sleep(0.5)
        payload['params']['name'] = 'search_news'
        payload['params']['arguments']['keyword'] = f'{stock_name} 并购 重组 收购'
        resp = requests.post(f'{base_url}/news/message', headers=headers, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            content = _parse_ifind_response(data)
            if content:
                results['news'] = content[:5]

    except Exception as e:
        print(f"  [iFinD] 搜索异常: {e}")

    return results


def _parse_ifind_response(data):
    """解析 iFinD MCP 4层嵌套 JSON"""
    try:
        if isinstance(data, dict):
            result = data.get('result', data)
            if isinstance(result, dict):
                content = result.get('content', [])
                if isinstance(content, list) and content:
                    text = content[0].get('text', '')
                    if text:
                        parsed = json.loads(text)
                        if isinstance(parsed, list):
                            return parsed
                        elif isinstance(parsed, dict):
                            return parsed.get('data', [parsed])
    except:
        pass
    return []


# ═══════════════════════════════════════════════════
# Part 5: 主流程
# ═══════════════════════════════════════════════════

def get_stock_info_from_pool(code_or_name: str) -> dict:
    """从 merger_pool.json 查找股票信息"""
    with open(POOL_PATH) as f:
        pool = json.load(f)

    code_clean = code_or_name.replace('.SH', '').replace('.SZ', '')

    for name, info in pool['stocks'].items():
        stock_code = info.get('code', '')
        if code_clean in stock_code or name == code_or_name:
            return {'name': name, **info}

    return None


def generate_report(ts_code: str, chip_only: bool = False, report_only: bool = False):
    """
    为单只票生成完整分析报告
    """
    # 查找股票信息
    stock_info = get_stock_info_from_pool(ts_code)
    if not stock_info:
        print(f"[!] {ts_code} 不在并购池中")
        return False

    stock_name = stock_info['name']
    code = stock_info.get('code', ts_code)
    code_clean = code.replace('.SH', '').replace('.SZ', '')

    print(f"\n{'='*50}")
    print(f"  {stock_name}（{code}）")
    print(f"{'='*50}")

    output = {
        'name': stock_name,
        'code': code,
        'stage': stock_info.get('stage', ''),
        'first_date': stock_info.get('first_date', ''),
        'last_date': stock_info.get('last_date', ''),
        'last_title': stock_info.get('last_title', ''),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'chip': None,
        'report_md': None,
        'has_report': False,
    }

    # ── 筹码分析（每次都跑）──
    if not report_only:
        print("\n[1] 筹码峰分析...")
        chip_data = run_chip_analysis(code)
        if chip_data:
            output['chip'] = chip_data
            print(f"  ✓ 筹码分析完成 (均成本: {chip_data.get('chip',{}).get('avg_cost','?')})")
        else:
            print(f"  ✗ 筹码分析失败")

    if chip_only:
        # 只跑筹码，保存并返回
        _save_output(code_clean, stock_name, output)
        return True

    # ── 检查已有底稿 ──
    report_path = ANALYSIS_DIR / f'{stock_name}_并购重组跟踪.md'
    existing_report = None
    if report_path.exists():
        existing_report = report_path.read_text()
        print(f"\n[2] 已有底稿（{len(existing_report)} 字），执行增量更新...")
    else:
        print(f"\n[2] 无底稿，首次生成...")

    # ── Step 0: iFinD 硬事实 ──
    print("\n[3] iFinD 公告/新闻...")
    ifind_data = ifind_search(stock_name, code)
    notice_count = len(ifind_data.get('notices', []))
    news_count = len(ifind_data.get('news', []))
    print(f"  公告 {notice_count} 条, 新闻 {news_count} 条")

    # ── Step 1-3: Kimi 搜索 ──
    print("\n[4] Kimi 联网搜索...")

    if existing_report:
        # 增量模式：只搜最近新信息
        queries = [
            f'{stock_name} {code.split(".")[0]} 并购重组 最新进展 2026',
            f'{stock_name} 股东变动 实控人 最新公告',
            f'{stock_name} 并购 买方 战略投资者 最新',
        ]
    else:
        # 首次模式：完整搜索
        queries = [
            f'{stock_name} {code.split(".")[0]} 并购重组 公告 实控人变更',
            f'{stock_name} 控股股东 持股比例 质押 减持',
            f'{stock_name} 注册地 产业基金 国资 地方政府',
            f'{stock_name} 主营业务 营收 净利润 行业地位',
            f'{stock_name} 并购 潜在买方 战略投资者 市场猜测',
            f'{stock_name} 并购重组 估值 对价 交易结构',
            f'{stock_name} 并购 审核进度 证监会 交易所',
            f'{stock_name} 同行业 并购案例 可比交易',
        ]

    kimi_results = kimi_search_batch(queries)

    # ── 汇总上下文 ──
    context_parts = []

    # iFinD 数据
    if ifind_data['notices']:
        context_parts.append("【iFinD 公告】\n" + json.dumps(ifind_data['notices'], ensure_ascii=False, indent=1)[:2000])
    if ifind_data['news']:
        context_parts.append("【iFinD 新闻】\n" + json.dumps(ifind_data['news'], ensure_ascii=False, indent=1)[:2000])

    # Kimi 搜索结果
    for i, (q, r) in enumerate(zip(queries, kimi_results)):
        if r:
            context_parts.append(f"【搜索{i+1}: {q[:30]}】\n{r[:1500]}")

    context = '\n\n'.join(context_parts)
    print(f"  汇总上下文: {len(context)} 字")

    # ── Step 4: Claude 生成底稿 ──
    print("\n[5] Claude 生成底稿...")
    report_md = claude_generate_report(stock_name, code, context, existing_report)

    if report_md:
        # 保存 markdown 底稿
        report_path.write_text(report_md)
        output['report_md'] = report_md
        output['has_report'] = True
        print(f"  ✓ 底稿已保存 ({len(report_md)} 字)")
    else:
        # 如果 Claude 失败但有旧底稿，保留旧的
        if existing_report:
            output['report_md'] = existing_report
            output['has_report'] = True
            print(f"  ⚠ Claude 失败，保留旧底稿")
        else:
            print(f"  ✗ 底稿生成失败")

    # ── 保存输出 ──
    _save_output(code_clean, stock_name, output)
    return True


def _save_output(code_clean: str, stock_name: str, output: dict):
    """保存 JSON 输出供前端读取"""
    out_path = DETAIL_DIR / f'{code_clean}.json'

    # 如果已有旧数据，合并（保留旧底稿如果新的没有）
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text())
            if not output.get('chip') and old.get('chip'):
                output['chip'] = old['chip']
            if not output.get('report_md') and old.get('report_md'):
                output['report_md'] = old['report_md']
                output['has_report'] = old.get('has_report', False)
        except:
            pass

    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    print(f"\n  ✓ 输出已保存: detail/{code_clean}.json")


def run_auto():
    """自动模式：跑异动 Top 8（只跑池内的票）"""
    print("=" * 50)
    print("  并购深度分析 - 自动模式（异动 Top 8）")
    print("=" * 50)

    # 加载异动数据
    if not REACTIONS_PATH.exists():
        print("[!] 无异动数据，请先跑回测")
        return

    with open(REACTIONS_PATH) as f:
        reactions = json.load(f)

    # 加载池子，确定哪些票在池内
    with open(POOL_PATH) as f:
        pool = json.load(f)
    pool_codes = {v.get('code') for v in pool['stocks'].values() if v.get('code')}

    # 筛选最近 60 天入池、5天涨幅 > 5%、且在池内的票
    cutoff = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    recent = [r for r in reactions
              if r.get('entry_date', '') >= cutoff
              and (r.get('ret_5d') or 0) > 5
              and r.get('code') in pool_codes]
    recent.sort(key=lambda x: x.get('ret_5d') or 0, reverse=True)
    top8 = recent[:8]

    if not top8:
        print("[!] 最近 60 天无池内异动票（5天涨幅 > 5%）")
        return

    print(f"\n异动 Top {len(top8)}（池内）:")
    for r in top8:
        print(f"  {r['name']:8s} {r['code']:12s} 5d={r.get('ret_5d',0):+.1f}%")

    # 逐个生成
    # Top 3 跑完整（底稿+筹码），4-8 只跑筹码
    for i, r in enumerate(top8):
        code = r['code']
        if i < 3:
            print(f"\n{'─'*40}")
            print(f"[{i+1}/{len(top8)}] {r['name']} - 完整分析（底稿+筹码）")
            generate_report(code, chip_only=False)
        else:
            print(f"\n{'─'*40}")
            print(f"[{i+1}/{len(top8)}] {r['name']} - 筹码分析")
            generate_report(code, chip_only=True)

    print(f"\n{'='*50}")
    print(f"  完成！Top 3 完整底稿 + Top 4-8 筹码")
    print(f"{'='*50}")


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='并购深度分析报告生成器')
    parser.add_argument('--code', type=str, help='股票代码（如 002176.SZ 或 002176）')
    parser.add_argument('--chip-only', action='store_true', help='只跑筹码分析')
    parser.add_argument('--report-only', action='store_true', help='只跑底稿生成')
    parser.add_argument('--auto', action='store_true', help='自动模式：跑异动 Top 8')
    args = parser.parse_args()

    if args.auto:
        run_auto()
    elif args.code:
        # 标准化代码
        code = args.code
        if '.' not in code:
            if code.startswith(('6', '9')):
                code = f'{code}.SH'
            else:
                code = f'{code}.SZ'
        generate_report(code, chip_only=args.chip_only, report_only=args.report_only)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
