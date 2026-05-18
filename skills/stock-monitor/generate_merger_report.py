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
    """调用 chip_api.analyze_stock 获取筹码数据（延迟导入）"""
    try:
        sys.path.insert(0, str(GAMT_ROOT / 'server'))
        sys.path.insert(0, str(GAMT_ROOT / 'chip_query'))
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

请输出更新后的完整 markdown 底稿。保持原有模板结构。"""
    else:
        prompt = f"""你是一个专业的并购重组分析师。请根据以下搜索结果，为 {stock_name}（{code}）生成一份深度并购重组跟踪底稿。

【搜索结果汇总】
{context}

请严格按以下结构输出完整 markdown 底稿（每个部分都必须有实质内容，不能只写"待披露"）：

# {stock_name}（{code}）并购重组跟踪底稿

**更新日期：** {datetime.now().strftime('%Y-%m-%d')}

## 一、事件时间线
用表格列出所有已知事件节点（日期/事件/性质）

## 二、交易结构
用表格列出：交易类型/买方/卖方/标的资产/交易对价/支付方式/业绩承诺
如未披露，基于搜索结果推断最可能的结构

## 三、控股股东画像
实控人信息/持股比例/质押/减持/家族关系
用【收购结构图】展示股权关系（ASCII 箭头图）：
```
实控人
  ├── 直接持股 XX%
  ├── 通过XX平台间接持股 XX%
  └── 合计控制 XX%
       │
       ▼ 拟转让/收购
       │
  买方/标的
```

## 四、公司基本面
营收/净利润/主营业务/毛利率/ROE/行业地位

## 五、潜在买方/标的分析
用表格列出可能的买方/标的，标注概率（★）和逻辑

## 六、估值参考
分多情形推演（至少2-3个情形），每个情形给出对应市值和股价区间

## 七、进度判断
当前阶段/成功概率/风险点/预期时间表

## 八、收购路径推演
用 ASCII 流程图展示最可能的路径（从当前状态到最终结果的完整链条）：
```
当前状态
  ↓
下一步动作
  ↓
...
  ↓
最终结果
```
至少给出路径A（最可能）和路径B（备选），每条路径都要有完整的推演逻辑

## 九、信号监控清单
用表格列出需要监控的信号（信号/数据源/紧急度/触发动作）

## 十、当前结论
一段话总结：当前判断 + 核心逻辑 + 观察窗口

要求：
- 信息不足的部分，基于已有信息做合理推断，标注"推断"
- 路径推演和估值必须有具体数字和逻辑链
- 收购结构图和路径流程图必须用 ASCII 箭头画出来
- 语言简洁专业，像卖方研报的风格"""

    payload = {
        'model': CLAUDE_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 8192,
    }

    try:
        resp = requests.post(
            f'{CLAUDE_BASE_URL}/v1/messages',
            headers=headers,
            json=payload,
            timeout=180,
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


def claude_analyze_round1(stock_name: str, code: str, round1_context: str) -> dict:
    """
    Claude 中间分析：读第一轮搜索结果，提炼深挖方向和第二轮关键词
    返回 {'directions': [...], 'queries': [...]}
    """
    if not CLAUDE_API_KEY:
        return {'directions': [], 'queries': []}

    headers = {
        'x-api-key': CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
    }

    prompt = f"""你是并购重组分析师。以下是关于 {stock_name}（{code}）第一轮搜索的结果。

请分析这些信息，告诉我：
1. 目前已知的关键事实（2-3句话总结）
2. 需要深挖的方向（最多4个方向）
3. 针对每个方向，给出具体的搜索关键词（用于联网搜索引擎）

【第一轮搜索结果】
{round1_context[:4000]}

请用 JSON 格式输出：
{{
  "summary": "已知事实总结",
  "directions": ["方向1", "方向2", ...],
  "queries": ["搜索关键词1", "搜索关键词2", ...]
}}

要求：
- queries 最多 5 个，每个是一句适合搜索引擎的查询
- 重点关注：买方是谁/标的值多少/地方政府态度/产业链上下游/同行业案例
- 如果第一轮已经发现了具体的人名/机构名/基金名，第二轮要针对性验证
- 关键词要具体，不要太宽泛"""

    payload = {
        'model': CLAUDE_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 1024,
    }

    try:
        resp = requests.post(
            f'{CLAUDE_BASE_URL}/v1/messages',
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get('content', [])
        if content and content[0].get('type') == 'text':
            text = content[0]['text']
            # 提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
        return {'directions': [], 'queries': []}
    except Exception as e:
        print(f"  [Claude] 中间分析失败: {e}")
        return {'directions': [], 'queries': []}


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
    is_incremental = False
    if report_path.exists():
        existing_report = report_path.read_text()
        is_incremental = True
        print(f"\n[2] 已有底稿（{len(existing_report)} 字），执行增量更新...")
    else:
        print(f"\n[2] 无底稿，首次深度生成（两轮搜索）...")

    # ── Step 0: iFinD 硬事实 ──
    print("\n[3] iFinD 公告/新闻...")
    ifind_data = ifind_search(stock_name, code)
    notice_count = len(ifind_data.get('notices', []))
    news_count = len(ifind_data.get('news', []))
    print(f"  公告 {notice_count} 条, 新闻 {news_count} 条")

    if is_incremental:
        # ── 增量模式：只搜最近新信息，不做两轮 ──
        print("\n[4] Kimi 增量搜索（3次）...")
        queries = [
            f'{stock_name} {code.split(".")[0]} 并购重组 最新进展 2026',
            f'{stock_name} 股东变动 实控人 最新公告',
            f'{stock_name} 并购 买方 战略投资者 最新',
        ]
        results = kimi_search_batch(queries)

        context_parts = []
        if ifind_data['notices']:
            context_parts.append("【iFinD 公告】\n" + json.dumps(ifind_data['notices'], ensure_ascii=False, indent=1)[:2000])
        if ifind_data['news']:
            context_parts.append("【iFinD 新闻】\n" + json.dumps(ifind_data['news'], ensure_ascii=False, indent=1)[:2000])
        for i, (q, r) in enumerate(zip(queries, results)):
            if r:
                context_parts.append(f"【搜索{i+1}: {q[:30]}】\n{r[:1500]}")
        context = '\n\n'.join(context_parts)
        print(f"  汇总: {len(context)} 字")

        print("\n[5] Claude 增量更新底稿...")
        report_md = claude_generate_report(stock_name, code, context, existing_report)

    else:
        # ── 首次深度模式：两轮搜索 ──
        print("\n[4] Kimi 第一轮搜索（事实层，5次）...")

        round1_queries = [
            f'{stock_name} {code.split(".")[0]} 并购重组 公告 实控人变更 停牌',
            f'{stock_name} 控股股东 持股比例 质押 减持 股权结构',
            f'{stock_name} 注册地 产业基金 国资 地方政府 战略合作',
            f'{stock_name} 主营业务 营收 净利润 毛利率 行业地位 客户',
            f'{stock_name} 并购 交易结构 对价 标的资产 买方',
        ]

        round1_results = kimi_search_batch(round1_queries)

        # 汇总第一轮上下文
        round1_context_parts = []
        if ifind_data['notices']:
            round1_context_parts.append("【iFinD 公告】\n" + json.dumps(ifind_data['notices'], ensure_ascii=False, indent=1)[:2000])
        if ifind_data['news']:
            round1_context_parts.append("【iFinD 新闻】\n" + json.dumps(ifind_data['news'], ensure_ascii=False, indent=1)[:2000])
        for i, (q, r) in enumerate(zip(round1_queries, round1_results)):
            if r:
                round1_context_parts.append(f"【搜索{i+1}: {q[:30]}】\n{r[:1500]}")
        round1_context = '\n\n'.join(round1_context_parts)
        print(f"  第一轮汇总: {len(round1_context)} 字")

        # ── Step 2: Claude 中间分析（提炼深挖方向）──
        print("\n[5] Claude 中间分析（提炼第二轮关键词）...")
        analysis = claude_analyze_round1(stock_name, code, round1_context)

        if analysis.get('summary'):
            print(f"  已知事实: {analysis['summary'][:80]}...")
        if analysis.get('directions'):
            print(f"  深挖方向: {analysis['directions']}")

        # ── Step 3: Kimi 第二轮搜索（深挖层）──
        round2_queries = analysis.get('queries', [])
        if not round2_queries:
            # fallback：如果 Claude 没返回，用通用深挖关键词
            round2_queries = [
                f'{stock_name} 并购 潜在买方 战略投资者 产业资本',
                f'{stock_name} 估值 市值 PE 同行业对比',
                f'{stock_name} 并购 审核进度 证监会 交易所 最新',
            ]

        print(f"\n[6] Kimi 第二轮搜索（深挖层，{len(round2_queries)}次）...")
        round2_results = kimi_search_batch(round2_queries)

        # ── 汇总全部上下文 ──
        all_context_parts = round1_context_parts.copy()
        for i, (q, r) in enumerate(zip(round2_queries, round2_results)):
            if r:
                all_context_parts.append(f"【深挖{i+1}: {q[:30]}】\n{r[:1500]}")

        context = '\n\n'.join(all_context_parts)
        print(f"  全部汇总: {len(context)} 字")

        # ── Step 4: Claude 最终生成底稿 ──
        print("\n[7] Claude 生成深度底稿...")
        report_md = claude_generate_report(stock_name, code, context, existing_report)

    # ── 统一处理底稿结果 ──
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
    """自动模式：从"进行中"池子（~70只）实时拉涨幅，取 Top 8"""
    print("=" * 50)
    print("  并购深度分析 - 自动模式")
    print("=" * 50)

    # 加载池子，筛选"进行中"的票（方案公布 + 审核中 + 已过会 + 已注册）
    with open(POOL_PATH) as f:
        pool = json.load(f)

    active_stages = {'方案公布', '审核中', '已过会', '已注册'}
    active_stocks = []
    for name, v in pool['stocks'].items():
        if v.get('stage') in active_stages and v.get('code'):
            active_stocks.append({'name': name, 'code': v['code'], 'stage': v['stage']})

    if not active_stocks:
        print("[!] 无进行中的票")
        return

    print(f"\n进行中池子: {len(active_stocks)} 只")
    print("正在拉取实时涨幅...")

    # 用 Tushare 拉最近 10 个交易日行情，算 1/3/5 日涨幅
    sys.path.insert(0, str(GAMT_ROOT / 'server'))
    sys.path.insert(0, str(GAMT_ROOT / 'chip_query'))
    from data_source import get_daily

    today = datetime.now().strftime('%Y%m%d')
    results = []

    for stock in active_stocks:
        try:
            df = get_daily(stock['code'], days=10)
            if df is None or len(df) < 2:
                continue

            # df 按日期降序（最新在前）
            df = df.sort_values('trade_date', ascending=False).reset_index(drop=True)
            latest_close = float(df.iloc[0]['close'])
            latest_date = str(df.iloc[0]['trade_date'])[:10].replace('-', '')

            ret_1d = ((latest_close / float(df.iloc[1]['close'])) - 1) * 100 if len(df) >= 2 else 0
            ret_3d = ((latest_close / float(df.iloc[3]['close'])) - 1) * 100 if len(df) >= 4 else 0
            ret_5d = ((latest_close / float(df.iloc[5]['close'])) - 1) * 100 if len(df) >= 6 else 0

            results.append({
                'name': stock['name'],
                'code': stock['code'],
                'stage': stock['stage'],
                'close': latest_close,
                'data_date': latest_date,
                'ret_1d': round(ret_1d, 2),
                'ret_3d': round(ret_3d, 2),
                'ret_5d': round(ret_5d, 2),
            })
        except Exception as e:
            continue

    if not results:
        print("[!] 无法获取行情数据")
        return

    # 按 5 日涨幅排序，取 Top 8
    results.sort(key=lambda x: x['ret_5d'], reverse=True)
    # 过滤：至少有一个周期涨幅 > 5%
    top_candidates = [r for r in results if r['ret_5d'] > 5 or r['ret_3d'] > 5 or r['ret_1d'] > 5]

    if not top_candidates:
        print("[!] 进行中池子无异动票（1/3/5日涨幅均 < 5%）")
        # 仍然输出 anomaly JSON 供前端用（空列表）
        _save_anomaly_json([], results[0]['data_date'] if results else today)
        return

    top8 = top_candidates[:8]
    data_date = top8[0]['data_date']

    print(f"\n异动 Top {len(top8)}（数据截止: {data_date}）:")
    print(f"  {'名称':8s} {'代码':12s} {'阶段':6s} {'1日':>6s} {'3日':>6s} {'5日':>6s}")
    print(f"  {'─'*50}")
    for r in top8:
        print(f"  {r['name']:8s} {r['code']:12s} {r['stage']:6s} {r['ret_1d']:+5.1f}% {r['ret_3d']:+5.1f}% {r['ret_5d']:+5.1f}%")

    # 保存异动 JSON（供前端异动面板读取）
    _save_anomaly_json(top8, data_date)

    # 逐个生成：Top 3 完整底稿+筹码，4-8 只跑筹码
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


def _save_anomaly_json(top_list: list, data_date: str):
    """保存异动数据供前端读取"""
    out = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'data_date': data_date,
        'anomalies': top_list,
    }
    out_path = SCRIPT_DIR / 'anomaly_top.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n  异动数据已保存: anomaly_top.json（{len(top_list)} 只，截止 {data_date}）")


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
