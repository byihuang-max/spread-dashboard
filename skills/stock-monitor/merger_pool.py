#!/usr/bin/env python3
"""
并购池扫描器 - 定期扫描全市场并购动态，维护并购池

功能：
1. 通过 iFinD 公告/新闻搜索，抓取有并购关键字的票
2. 分类为：筹划中 / 方案公布 / 审核中 / 已过会 / 已注册 / 已完成 / 已终止
3. 输出到 merger_pool.json，供后续分析和前端展示
4. 增量更新：每次只搜最近 N 天的新公告，合并到已有池子

数据源：
- iFinD MCP search_notice（公告）
- iFinD MCP search_news（新闻/舆情）

用法：
  python3 merger_pool.py                # 增量更新（默认搜最近7天）
  python3 merger_pool.py --full         # 全量扫描（搜924以来全部）
  python3 merger_pool.py --days 30      # 搜最近30天
  python3 merger_pool.py --stats        # 只输出统计，不更新
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
        # 解析嵌套 JSON
        content = data['data']['result']['content'][0]['text']
        parsed = json.loads(content)
        items_str = parsed.get('data', {}).get('data', '[]')
        return json.loads(items_str)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[ERROR] Parse failed: {e}", file=sys.stderr)
        return None


def determine_stage(title, content):
    """根据标题和内容判断并购阶段"""
    text = (title or '') + (content or '')
    for stage, keywords in STAGE_RULES:
        if any(kw in text for kw in keywords):
            return stage
    return '筹划中'


def extract_stock_info(title, content):
    """从公告标题提取公司名称（简单规则）"""
    # 公告标题通常格式："XXX：关于..."  或 "XXX:..."
    for sep in ['：', ':', '|']:
        if sep in title:
            name = title.split(sep)[0].strip()
            # 过滤掉太长的（不是公司名）
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
                'source': 'notice',
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
                'source': 'news',
                'keyword': kw,
                'title': title,
                'content_snippet': content[:200] if content else '',
                'date': date,
                'stock_name': None,  # 新闻标题格式不统一，后续人工补
                'stage': determine_stage(title, content),
            })
    return results


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
        },
        'stocks': {},  # key: stock_name or title_hash
        'raw_hits': [],  # 原始命中记录（用于去重和审计）
    }


def merge_results(pool, new_results):
    """将新扫描结果合并到池子"""
    added = 0
    updated = 0

    for item in new_results:
        # 用标题做去重 key
        title_key = item['title'][:50]
        
        # 检查是否已存在（raw_hits 去重）
        existing_titles = {h.get('title', '')[:50] for h in pool['raw_hits']}
        if title_key in existing_titles:
            continue

        pool['raw_hits'].append(item)

        # 如果能提取到公司名，更新 stocks 字典
        stock_name = item.get('stock_name')
        if stock_name and stock_name not in ['备注']:
            if stock_name in pool['stocks']:
                # 更新阶段（取更新的）
                existing = pool['stocks'][stock_name]
                if item['date'] > existing.get('last_date', ''):
                    existing['stage'] = item['stage']
                    existing['last_date'] = item['date']
                    existing['last_title'] = item['title']
                    existing['history'].append({
                        'date': item['date'],
                        'stage': item['stage'],
                        'title': item['title'][:60],
                    })
                    updated += 1
            else:
                pool['stocks'][stock_name] = {
                    'name': stock_name,
                    'stage': item['stage'],
                    'first_date': item['date'],
                    'last_date': item['date'],
                    'last_title': item['title'],
                    'type': '',  # 待人工补充：控制权转让/资产注入/吸收合并/...
                    'target': '',  # 待人工补充：标的名称
                    'amount': '',  # 待人工补充：交易金额
                    'industry': '',  # 待人工补充：行业
                    'history': [{
                        'date': item['date'],
                        'stage': item['stage'],
                        'title': item['title'][:60],
                    }],
                }
                added += 1

    return added, updated


def save_pool(pool):
    """保存并购池"""
    pool['meta']['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    pool['meta']['total_scans'] += 1
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
    print(f"  原始命中: {len(pool['raw_hits'])} 条")
    print(f"  最后更新: {pool['meta'].get('last_updated', '从未')}")
    print(f"  累计扫描: {pool['meta'].get('total_scans', 0)} 次")
    print(f"\n  按阶段分布:")
    for stage in ['筹划中', '方案公布', '审核中', '已过会', '已注册', '已完成', '已终止']:
        count = by_stage.get(stage, 0)
        if count > 0:
            print(f"    {stage}: {count}")
    print(f"{'='*50}\n")

    # 列出活跃票（非终止/非完成）
    active = [s for s in stocks.values() if s['stage'] not in ('已终止', '已完成')]
    if active:
        print("  活跃标的:")
        active.sort(key=lambda x: x.get('last_date', ''), reverse=True)
        for s in active[:20]:
            print(f"    {s['name']:8s} | {s['stage']:6s} | {s.get('last_date','')} | {s.get('last_title','')[:40]}")
        if len(active) > 20:
            print(f"    ... 还有 {len(active)-20} 只")


def main():
    parser = argparse.ArgumentParser(description='并购池扫描器')
    parser.add_argument('--full', action='store_true', help='全量扫描（924以来）')
    parser.add_argument('--days', type=int, default=7, help='增量扫描天数（默认7）')
    parser.add_argument('--stats', action='store_true', help='只输出统计')
    parser.add_argument('--size', type=int, default=20, help='每个关键字搜索条数')
    args = parser.parse_args()

    pool = load_pool()

    if args.stats:
        print_stats(pool)
        return

    # 确定时间范围
    time_end = datetime.now().strftime('%Y-%m-%d')
    if args.full:
        time_start = '2024-09-24'
        print(f"[全量扫描] 2024-09-24 ~ {time_end}")
    else:
        time_start = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
        print(f"[增量扫描] {time_start} ~ {time_end}（最近{args.days}天）")

    # 扫描公告
    print(f"  扫描公告（{len(NOTICE_KEYWORDS)} 组关键字）...")
    notice_results = scan_notices(time_start, time_end, size=args.size)
    print(f"    命中 {len(notice_results)} 条")

    # 扫描新闻
    print(f"  扫描新闻（{len(NEWS_KEYWORDS)} 组关键字）...")
    news_results = scan_news(time_start, time_end, size=args.size)
    print(f"    命中 {len(news_results)} 条")

    # 合并
    all_results = notice_results + news_results
    added, updated = merge_results(pool, all_results)
    print(f"\n  新增 {added} 只，更新 {updated} 只")

    # 保存
    save_pool(pool)
    print(f"  已保存到 {POOL_PATH}")

    # 输出统计
    print_stats(pool)


if __name__ == '__main__':
    main()
