#!/usr/bin/env python3
"""
并购池扫描器 - 定期扫描全市场并购动态，维护并购池

功能：
1. 通过 iFinD 公告/新闻搜索，抓取有并购关键字的票（增量）
2. 通过通联 UQER EquRestructuringGet 拉取结构化并购事件（增量）
3. 分类为：筹划中 / 方案公布 / 审核中 / 已过会 / 已注册 / 已完成 / 已终止
4. 输出到 merger_pool.json，供后续分析和前端展示
5. 增量更新：每次只搜最近 N 天的新公告，合并到已有池子

数据源：
- iFinD MCP search_notice（公告）- 7天窗口
- iFinD MCP search_news（新闻/舆情）- 7天窗口
- 通联 UQER EquRestructuringGet（结构化）- 14天窗口（入库延迟约7-10天）

用法：
  python3 merger_pool.py                # 增量更新（iFinD 7天 + 通联 14天）
  python3 merger_pool.py --full         # 全量扫描（iFinD 924以来 + 通联全量）
  python3 merger_pool.py --days 30      # iFinD搜最近30天
  python3 merger_pool.py --stats        # 只输出统计，不更新
  python3 merger_pool.py --ifind-only   # 只跑 iFinD（跳过通联）
  python3 merger_pool.py --uqer-only    # 只跑通联（跳过 iFinD）
"""
import os
import sys
import json
import subprocess
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径 ──
SCRIPT_DIR = Path(__file__).parent.resolve()
POOL_PATH = SCRIPT_DIR / 'merger_pool.json'
IFIND_DIR = Path(os.path.expanduser('~/.openclaw/extensions/ifind-finance-data'))

# UQER SDK 路径（自动检测本地 Mac / 腾讯云）
_LOCAL_UQER_PY = Path(os.path.expanduser(
    '~/Desktop/quant-backtest/timing_model/.venv_uqer/bin/python'))
_LOCAL_UQER_TOKEN = Path(os.path.expanduser(
    '~/Desktop/quant-backtest/timing_model/config/uqer_token.json'))
_CLOUD_UQER_PY = SCRIPT_DIR / '.venv_uqer' / 'bin' / 'python'
_CLOUD_UQER_TOKEN = SCRIPT_DIR / 'config' / 'uqer_token.json'

# 优先用本地路径，fallback 到脚本同目录下的 venv
if _LOCAL_UQER_PY.exists():
    UQER_VENV_PY = _LOCAL_UQER_PY
    UQER_TOKEN_FILE = _LOCAL_UQER_TOKEN
elif _CLOUD_UQER_PY.exists():
    UQER_VENV_PY = _CLOUD_UQER_PY
    UQER_TOKEN_FILE = _CLOUD_UQER_TOKEN
else:
    UQER_VENV_PY = _LOCAL_UQER_PY  # fallback，运行时会报 warning
    UQER_TOKEN_FILE = _LOCAL_UQER_TOKEN

# ── 通联增量窗口（天）──
UQER_WINDOW_DAYS = 14  # 通联入库延迟约7-10天，用14天窗口覆盖

# ── 并购关键字（44组：公告29 + 新闻15）──
NOTICE_KEYWORDS = [
    # 原始7组
    '筹划重大资产重组',
    '发行股份购买资产',
    '重大资产重组报告书',
    '股份转让 实控人变更',
    '吸收合并',
    '发行可转债购买资产',
    '控股股东筹划战略重组',
    # 扩展22组（2026-05-16全量扫描时新增）
    '重大资产重组 草案',
    '现金收购 控股权',
    '要约收购报告书',
    '控制权变更',
    '股权转让 实际控制人',
    '资产注入',
    '定增收购',
    '收购报告书',
    '重组上会',
    '并购重组委',
    '发行股份及支付现金购买资产',
    '重大资产置换',
    '借壳上市',
    '协议收购',
    '间接收购',
    '重组方案获批',
    '资产出售 重大资产',
    '股权收购 交割',
    '并购重组 配套募集',
    '重大资产重组 恢复审核',
    '国有股权无偿划转',
    '战略投资者 入股',
]

NEWS_KEYWORDS = [
    # 原始4组
    '并购重组 过会',
    '并购重组 注册生效',
    '发行股份购买资产 获通过',
    '重大资产重组 终止',
    # 扩展11组（2026-05-16全量扫描时新增）
    '并购重组 受理',
    '重大资产重组 获批',
    '控制权转让 完成',
    '并购重组 问询',
    '发行股份购买资产 注册',
    '重组 复牌',
    '并购 停牌',
    '并购重组 上会',
    '重组 获有条件通过',
    '借壳 方案',
    '要约收购 完成',
]

# ── 阶段判断关键字 ──
STAGE_RULES = [
    ('已终止', ['终止', '撤回', '取消']),
    ('已完成', ['过户完成', '实施完毕', '新增股份上市', '交割完成']),
    ('已注册', ['注册生效', '证监会同意注册', '同意注册的批复']),
    ('已过会', ['过会', '审核通过', '审议通过', '获通过']),
    ('审核中', ['已问询', '已回复', '受理', '提交注册']),
    ('方案公布', ['重组报告书', '预案', '草案', '交易报告书']),
    ('筹划中', ['筹划', '停牌', '重大事项']),
]

# ── 通联 restructuringType 映射 ──
UQER_TYPE_MAP = {
    1: '资产收购',
    2: '股权转让',
    3: '吸收合并',
    4: '要约收购',
    5: '重大资产重组',
    7: '借壳上市',
    8: '资产出售',  # 清洗时排除
}

# ── 清洗规则：保留条件（满足任一即保留）──
# isMajorRes=1 / type in (5,4,7,3) / type=1且标题含并购词 / iFinD confirmed+medium
CLEAN_KEEP_TYPES = {5, 4, 7, 3}  # 重大重组/要约/借壳/吸收合并
CLEAN_EXCLUDE_TYPES = {8}  # 资产出售

# 并购关键词（用于 type=1 的二次过滤）
MERGER_KEYWORDS_FOR_TYPE1 = [
    '收购', '并购', '重组', '控制权', '实控人', '股权转让',
    '要约', '借壳', '注入', '吸收合并', '战略投资',
]


# ═══════════════════════════════════════════════════════
# iFinD 模块
# ═══════════════════════════════════════════════════════

def call_ifind(server_type, tool_name, params):
    """调用 iFinD MCP（通过 Node.js 脚本）"""
    js_code = f"""
const {{ call }} = require('./call-node.js');
call("{server_type}", "{tool_name}", {json.dumps(params, ensure_ascii=False)})
  .then(r => console.log(JSON.stringify(r)))
  .catch(e => console.error(e));
"""
    result = subprocess.run(
        ['node', '-e', js_code],
        cwd=str(IFIND_DIR),
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"[ERROR] iFinD call failed: {result.stderr[:200]}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
        if not data.get('ok'):
            return None
        content = data['data']['result']['content'][0]['text']
        parsed = json.loads(content)
        items_str = parsed.get('data', {}).get('data', '[]')
        return json.loads(items_str)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[ERROR] Parse failed: {e}", file=sys.stderr)
        return None


def determine_stage(title, content=''):
    """根据标题和内容判断并购阶段"""
    text = (title or '') + (content or '')
    for stage, keywords in STAGE_RULES:
        if any(kw in text for kw in keywords):
            return stage
    return '筹划中'


def extract_stock_info(title, content=''):
    """从公告标题提取公司名称"""
    for sep in ['：', ':', '|']:
        if sep in title:
            name = title.split(sep)[0].strip()
            if 2 <= len(name) <= 8:
                return name
    return None


def scan_notices(time_start, time_end, size=20):
    """扫描公告，返回并购相关条目"""
    results = []
    for kw in NOTICE_KEYWORDS:
        items = call_ifind('news', 'search_notice', {
            'query': kw,
            'time_start': time_start,
            'time_end': time_end,
            'size': size
        })
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict) or '公告标题' not in item:
                continue
            title = item.get('公告标题', '')
            content = item.get('公告片段内容', '')
            date = item.get('日期', '')
            stock_name = extract_stock_info(title, content)
            stage = determine_stage(title, content)
            results.append({
                'source': 'ifind_notice',
                'keyword': kw,
                'title': title,
                'content_snippet': content[:200] if content else '',
                'date': date,
                'stock_name': stock_name,
                'stage': stage,
            })
    return results


def scan_news(time_start, time_end, size=10):
    """扫描新闻，返回并购相关条目"""
    results = []
    for kw in NEWS_KEYWORDS:
        items = call_ifind('news', 'search_news', {
            'query': kw,
            'time_start': time_start,
            'time_end': time_end,
            'size': size
        })
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict) or '资讯标题' not in item:
                continue
            title = item.get('资讯标题', '')
            content = item.get('资讯内容', '')
            date = item.get('日期', '')
            results.append({
                'source': 'ifind_news',
                'keyword': kw,
                'title': title,
                'content_snippet': content[:200] if content else '',
                'date': date,
                'stock_name': None,
                'stage': determine_stage(title, content),
            })
    return results


# ═══════════════════════════════════════════════════════
# 通联 UQER 模块
# ═══════════════════════════════════════════════════════

def call_uqer_restructuring(begin_date, end_date):
    """
    调用通联 UQER EquRestructuringGet 拉取结构化并购事件。
    begin_date/end_date 格式：YYYYMMDD
    返回 list of dict（每条记录一个 dict）
    """
    if not UQER_VENV_PY.exists():
        print("[WARN] UQER venv not found, skipping UQER scan", file=sys.stderr)
        return []
    if not UQER_TOKEN_FILE.exists():
        print("[WARN] UQER token not found, skipping UQER scan", file=sys.stderr)
        return []

    # 用分隔符隔离 JSON 输出（UQER SDK 登录时会在 stdout 打印登录信息）
    separator = '---UQER_JSON_START---'
    script = f"""
import json, sys
from pathlib import Path
token = json.loads(Path('{UQER_TOKEN_FILE}').read_text()).get('token')
import uqer
from uqer import DataAPI
client = uqer.Client(token=token)
df = DataAPI.EquRestructuringGet(beginDate='{begin_date}', endDate='{end_date}', pandas='1')
print('{separator}')
if df is None or len(df) == 0:
    print(json.dumps([]))
else:
    records = df.to_dict(orient='records')
    print(json.dumps(records, ensure_ascii=False, default=str))
"""
    try:
        result = subprocess.run(
            [str(UQER_VENV_PY), '-c', script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            # 忽略 SyntaxWarning，只看 stderr 里的真错误
            real_errors = [l for l in result.stderr.split('\n')
                          if l and 'SyntaxWarning' not in l and 'is an invalid escape' not in l]
            if real_errors:
                print(f"[ERROR] UQER call failed: {'; '.join(real_errors[:3])}", file=sys.stderr)
            # 即使 returncode != 0，stdout 可能有数据（SyntaxWarning 不影响执行）
            if not result.stdout.strip():
                return []
        # 用分隔符提取 JSON 部分（跳过 UQER SDK 登录信息）
        stdout = result.stdout
        if separator in stdout:
            stdout = stdout.split(separator, 1)[1].strip()
        data = json.loads(stdout)
        return data if isinstance(data, list) else []
    except subprocess.TimeoutExpired:
        print("[ERROR] UQER call timeout", file=sys.stderr)
        return []
    except (json.JSONDecodeError, Exception) as e:
        print(f"[ERROR] UQER parse failed: {e}", file=sys.stderr)
        return []


def clean_uqer_record(record):
    """
    清洗单条通联记录，判断是否保留。
    返回 (keep: bool, cleaned_dict or None)
    """
    try:
        rtype = int(record.get('restructuringType', 0))
    except (ValueError, TypeError):
        rtype = 0

    is_major = int(record.get('isMajorRes', 0)) == 1
    ticker = str(record.get('ticker', '') or '')
    name = str(record.get('secShortName', '') or '')
    publish_date = str(record.get('publishDate', '') or '')
    outline = str(record.get('outLine', '') or '') if record.get('outLine') == record.get('outLine') else ''
    program = str(record.get('program', '') or '') if record.get('program') == record.get('program') else ''
    is_succeed = record.get('isSucceed')

    # 排除 type=8（资产出售）
    if rtype in CLEAN_EXCLUDE_TYPES:
        return False, None

    # 保留条件
    keep = False
    confidence = 'medium'

    if is_major:
        keep = True
        confidence = 'confirmed'
    elif rtype in CLEAN_KEEP_TYPES:
        keep = True
        confidence = 'confirmed'
    elif rtype == 1:
        # type=1（资产收购）需要二次过滤
        text = outline + program + name
        if any(kw in text for kw in MERGER_KEYWORDS_FOR_TYPE1):
            keep = True
            confidence = 'medium'
        else:
            # 没有并购关键词的 type=1，大概率是日常经营性收购
            return False, None
    elif rtype == 2:
        # 股权转让，保留
        keep = True
        confidence = 'medium'

    if not keep:
        return False, None

    # 判断阶段
    stage = '筹划中'
    if is_succeed == 1 or is_succeed == '1':
        stage = '已完成'
    elif is_succeed == 0 or is_succeed == '0':
        stage = '已终止'
    else:
        # 从 outline/program 推断
        stage = determine_stage(outline + program)

    # 构建标准化 code
    if ticker and len(ticker) == 6:
        if ticker.startswith(('6', '9')):
            code = f"{ticker}.SH"
        else:
            code = f"{ticker}.SZ"
    else:
        code = ''

    return True, {
        'name': name,
        'code': code,
        'stage': stage,
        'first_date': publish_date,
        'last_date': publish_date,
        'last_title': outline[:100] if outline else f"{UQER_TYPE_MAP.get(rtype, '未知')}事件",
        'type': UQER_TYPE_MAP.get(rtype, '未知'),
        'target': '',
        'amount': '',
        'industry': '',
        'confidence': confidence,
        'hit_count': 1,
        'source': 'uqer',
        'is_major': is_major,
        'history': [{
            'date': publish_date,
            'stage': stage,
            'title': outline[:60] if outline else f"{UQER_TYPE_MAP.get(rtype, '未知')}",
        }],
    }


def process_uqer_results(raw_records):
    """处理通联原始记录，清洗后返回标准化的 stock dict 列表"""
    cleaned = []
    skipped = 0
    for record in raw_records:
        keep, item = clean_uqer_record(record)
        if keep and item:
            cleaned.append(item)
        else:
            skipped += 1
    print(f"    通联清洗: {len(cleaned)} 保留, {skipped} 排除")
    return cleaned


# ═══════════════════════════════════════════════════════
# 池子管理
# ═══════════════════════════════════════════════════════

def load_pool():
    """加载现有并购池"""
    if POOL_PATH.exists():
        with open(POOL_PATH, 'r') as f:
            return json.load(f)
    return {
        'meta': {
            'created': datetime.now().strftime('%Y-%m-%d'),
            'last_updated': None,
            'total_scans': 0,
            'source': '通联UQER(主) + iFinD MCP(补) · 增量日更',
        },
        'stocks': {},
    }


def merge_ifind_results(pool, new_results):
    """将 iFinD 扫描结果合并到池子（按公司名匹配）"""
    added = 0
    updated = 0
    stocks = pool['stocks']

    for item in new_results:
        stock_name = item.get('stock_name')
        if not stock_name or stock_name in ['备注']:
            continue

        title = item.get('title', '')
        date = item.get('date', '')
        stage = item.get('stage', '筹划中')

        if stock_name in stocks:
            existing = stocks[stock_name]
            # 只在日期更新时更新阶段
            if date > existing.get('last_date', ''):
                existing['stage'] = stage
                existing['last_date'] = date
                existing['last_title'] = title[:100]
                existing['history'].append({
                    'date': date,
                    'stage': stage,
                    'title': title[:60],
                })
                updated += 1
        else:
            # 新增
            stocks[stock_name] = {
                'name': stock_name,
                'code': '',  # iFinD 不直接给代码，后续可补
                'stage': stage,
                'first_date': date,
                'last_date': date,
                'last_title': title[:100],
                'type': '',
                'target': '',
                'amount': '',
                'industry': '',
                'confidence': 'medium',
                'hit_count': 1,
                'source': 'ifind',
                'is_major': False,
                'history': [{
                    'date': date,
                    'stage': stage,
                    'title': title[:60],
                }],
            }
            added += 1

    return added, updated


def merge_uqer_results(pool, cleaned_items):
    """将通联清洗后的结果合并到池子（按公司名匹配）"""
    added = 0
    updated = 0
    stocks = pool['stocks']

    for item in cleaned_items:
        name = item['name']
        if not name:
            continue

        if name in stocks:
            existing = stocks[name]
            date = item.get('last_date', '')
            # 只在日期更新时更新阶段
            if date > existing.get('last_date', ''):
                existing['stage'] = item['stage']
                existing['last_date'] = date
                existing['last_title'] = item['last_title']
                existing['history'].append({
                    'date': date,
                    'stage': item['stage'],
                    'title': item['last_title'][:60],
                })
                updated += 1
            # 补充 code（如果之前没有）
            if not existing.get('code') and item.get('code'):
                existing['code'] = item['code']
            # 升级 confidence
            if item.get('confidence') == 'confirmed' and existing.get('confidence') != 'confirmed':
                existing['confidence'] = 'confirmed'
            # 升级 is_major
            if item.get('is_major'):
                existing['is_major'] = True
        else:
            # 新增
            stocks[name] = item
            added += 1

    return added, updated


def save_pool(pool):
    """保存并购池"""
    pool['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    pool['meta']['total_scans'] = pool['meta'].get('total_scans', 0) + 1
    pool['meta']['total'] = len(pool['stocks'])
    with open(POOL_PATH, 'w') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)


def print_stats(pool):
    """输出统计"""
    stocks = pool['stocks']
    total = len(stocks)
    by_stage = {}
    for s in stocks.values():
        stage = s.get('stage', '未知')
        by_stage[stage] = by_stage.get(stage, 0) + 1

    print(f"\n{'='*50}")
    print(f"  并购池统计")
    print(f"{'='*50}")
    print(f"  总票数: {total}")
    print(f"  最后更新: {pool['meta'].get('last_updated', '从未')}")
    print(f"  累计扫描: {pool['meta'].get('total_scans', 0)} 次")
    print(f"\n  按阶段分布:")
    for stage in ['筹划中', '方案公布', '审核中', '已过会', '已注册', '已完成', '已终止']:
        count = by_stage.get(stage, 0)
        if count > 0:
            print(f"    {stage}: {count}")
    unknown = total - sum(by_stage.get(s, 0) for s in ['筹划中', '方案公布', '审核中', '已过会', '已注册', '已完成', '已终止'])
    if unknown > 0:
        print(f"    其他: {unknown}")
    print(f"{'='*50}\n")


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='并购池扫描器（iFinD + 通联双增量）')
    parser.add_argument('--full', action='store_true', help='全量扫描')
    parser.add_argument('--days', type=int, default=7, help='iFinD增量天数（默认7）')
    parser.add_argument('--uqer-days', type=int, default=UQER_WINDOW_DAYS,
                        help=f'通联增量天数（默认{UQER_WINDOW_DAYS}）')
    parser.add_argument('--stats', action='store_true', help='只输出统计')
    parser.add_argument('--size', type=int, default=20, help='iFinD每关键字搜索条数')
    parser.add_argument('--ifind-only', action='store_true', help='只跑iFinD')
    parser.add_argument('--uqer-only', action='store_true', help='只跑通联')
    args = parser.parse_args()

    pool = load_pool()

    if args.stats:
        print_stats(pool)
        return

    today = datetime.now().strftime('%Y-%m-%d')
    today_compact = datetime.now().strftime('%Y%m%d')

    total_added = 0
    total_updated = 0

    # ── iFinD 增量 ──
    if not args.uqer_only:
        if args.full:
            ifind_start = '2024-09-24'
            print(f"[iFinD 全量] 2024-09-24 ~ {today}")
        else:
            ifind_start = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
            print(f"[iFinD 增量] {ifind_start} ~ {today}（最近{args.days}天）")

        print(f"  扫描公告（{len(NOTICE_KEYWORDS)} 组关键字）...")
        notice_results = scan_notices(ifind_start, today, size=args.size)
        print(f"    命中 {len(notice_results)} 条")

        print(f"  扫描新闻（{len(NEWS_KEYWORDS)} 组关键字）...")
        news_results = scan_news(ifind_start, today, size=args.size)
        print(f"    命中 {len(news_results)} 条")

        all_ifind = notice_results + news_results
        added, updated = merge_ifind_results(pool, all_ifind)
        print(f"  iFinD: 新增 {added}, 更新 {updated}")
        total_added += added
        total_updated += updated

    # ── 通联 UQER 增量 ──
    if not args.ifind_only:
        if args.full:
            uqer_start = '20240924'
            uqer_end = today_compact
            print(f"\n[通联 全量] 2024-09-24 ~ {today}")
        else:
            uqer_start = (datetime.now() - timedelta(days=args.uqer_days)).strftime('%Y%m%d')
            uqer_end = today_compact
            print(f"\n[通联 增量] {uqer_start} ~ {uqer_end}（最近{args.uqer_days}天）")

        print(f"  调用 EquRestructuringGet...")
        raw_records = call_uqer_restructuring(uqer_start, uqer_end)
        print(f"    返回 {len(raw_records)} 条原始记录")

        if raw_records:
            cleaned = process_uqer_results(raw_records)
            added, updated = merge_uqer_results(pool, cleaned)
            print(f"  通联: 新增 {added}, 更新 {updated}")
            total_added += added
            total_updated += updated
        else:
            print(f"  通联: 无新数据")

    # ── 保存 ──
    print(f"\n  合计: 新增 {total_added}, 更新 {total_updated}")
    save_pool(pool)
    print(f"  已保存到 {POOL_PATH}")

    # ── 统计 ──
    print_stats(pool)


if __name__ == '__main__':
    main()
