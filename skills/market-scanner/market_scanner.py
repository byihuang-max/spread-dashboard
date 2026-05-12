#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全市场公告扫描器
每日扫描全市场公告，按关键词分类推送
"""

import os
import sys
import json
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
SCRIPT_DIR = Path(__file__).resolve().parent
GAMT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(GAMT_ROOT))

# 飞书配置
FEISHU_APP_ID = 'cli_a91c36caf5785cb2'
FEISHU_APP_SECRET = 'HWhYR833N0xObKumrjNCKdRSHq3jg0zi'

# iFinD MCP 配置
IFIND_MCP_DIR = Path.home() / ".openclaw/extensions/ifind-finance-data"

# 关键词配置
KEYWORDS = {
    "并购重组": ["并购", "重组", "收购", "资产注入", "吸收合并", "要约收购"],
    "处罚": ["处罚", "立案", "调查", "违规", "警示函", "监管函"],
    "增持": ["增持", "买入", "购买股份"],
    "减持": ["减持", "出售股份", "股份转让"],
    "定增": ["定向增发", "非公开发行", "增发", "配股"],
    "ST风险": ["ST", "*ST", "退市风险", "暂停上市", "终止上市"]
}


def ifind_call(server_type: str, tool_name: str, params: dict) -> dict:
    """调用 iFinD MCP Node.js 接口（与 stock-monitor 同方式）"""
    call_script = IFIND_MCP_DIR / 'call-node.js'
    if not call_script.exists():
        return {'ok': False, 'error': 'iFinD call-node.js not found'}

    js_code = f"""
const {{ call }} = require('{call_script}');
async function main() {{
    const r = await call("{server_type}", "{tool_name}", {json.dumps(params, ensure_ascii=False)});
    process.stdout.write(JSON.stringify(r));
}}
main().catch(e => {{ console.error(e); process.exit(1); }});
"""
    result = subprocess.run(
        ['node', '-e', js_code],
        capture_output=True, text=True, timeout=60,
        cwd=str(IFIND_MCP_DIR)
    )
    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr[:500]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'ok': False, 'error': f'JSON parse failed: {result.stdout[:200]}'}


def _parse_ifind_response(result: dict) -> list:
    """解析 iFinD MCP 多层嵌套响应
    
    实际结构：
    {ok, status_code, data: {jsonrpc, result: {content: [{text: JSON_STRING, type}]}, id}}
    其中 JSON_STRING 解析后为：{code, msg, data: {data: JSON_STRING_2}}
    JSON_STRING_2 解析后为实际数据列表
    """
    if not result or not result.get('ok', False):
        err = result.get('error', 'unknown') if result else 'empty'
        print(f"    [WARN] iFinD 返回失败: {err}")
        return []
    
    try:
        # 第一层：result -> data -> result -> content
        data_outer = result.get('data', {})
        rpc_result = data_outer.get('result', {})
        content_list = rpc_result.get('content', [])
        
        if not content_list:
            return []
        
        # 第二层：content[0].text -> JSON parse
        text_str = content_list[0].get('text', '')
        if not text_str:
            return []
        
        parsed = json.loads(text_str)
        
        # 第三层：parsed.data.data -> 可能是 string 或 list
        if isinstance(parsed, dict) and parsed.get('code') == 1:
            inner_data = parsed.get('data', {})
            if isinstance(inner_data, dict):
                data_field = inner_data.get('data', '[]')
                if isinstance(data_field, str):
                    items = json.loads(data_field)
                else:
                    items = data_field
            elif isinstance(inner_data, str):
                items = json.loads(inner_data)
            else:
                items = inner_data
        elif isinstance(parsed, list):
            items = parsed
        else:
            return []
        
        # 过滤掉"备注"类条目
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict) and '备注' not in item]
        
        return []
        
    except Exception as e:
        print(f"    [WARN] 解析 iFinD 响应失败: {e}")
        return []


def _extract_stock_from_title(title: str) -> tuple:
    """从公告标题中提取股票名称
    格式通常为：'中芯国际：中芯国际关于...' 或 '中芯国际:关于...'
    返回 (stock_name, clean_title)
    """
    for sep in ['：', ':']:
        if sep in title:
            parts = title.split(sep, 1)
            stock_name = parts[0].strip()
            # 有些标题重复了股票名，如 "中芯国际：中芯国际关于..."
            clean_title = parts[1].strip()
            if clean_title.startswith(stock_name):
                clean_title = clean_title[len(stock_name):].strip()
                if clean_title.startswith('：') or clean_title.startswith(':'):
                    clean_title = clean_title[1:].strip()
            return stock_name, clean_title
    return "", title


def scan_market_announcements(date_str: str = None):
    """扫描全市场公告"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    print(f"开始扫描 {date_str} 的全市场公告...")
    
    results = {}
    
    for category, keywords in KEYWORDS.items():
        print(f"\n扫描类别: {category}")
        category_results = []
        
        for keyword in keywords:
            print(f"  关键词: {keyword}")
            raw = ifind_call('news', 'search_notice', {
                'query': keyword,
                'time_start': date_str,
                'time_end': date_str,
                'size': 100,
            })
            notices = _parse_ifind_response(raw)
            
            for notice in notices:
                # iFinD 返回字段：公告标题、公告片段内容、日期
                raw_title = notice.get("公告标题", notice.get("title", ""))
                stock_name, clean_title = _extract_stock_from_title(raw_title)
                
                item = {
                    "stock_name": stock_name,
                    "title": clean_title or raw_title,
                    "raw_title": raw_title,
                    "pub_date": notice.get("日期", notice.get("date", "")),
                    "snippet": notice.get("公告片段内容", "")[:200],
                    "keyword": keyword
                }
                
                # 去重（同一公告可能匹配多个关键词）
                if item["raw_title"] and not any(
                    r["raw_title"] == item["raw_title"]
                    for r in category_results
                ):
                    category_results.append(item)
        
        results[category] = category_results
        print(f"  找到 {len(category_results)} 条公告")
    
    # 按股票名聚合
    aggregated = {}
    for category, items in results.items():
        stock_groups = {}
        for item in items:
            stock_name = item.get('stock_name', '未知')
            if stock_name not in stock_groups:
                stock_groups[stock_name] = []
            stock_groups[stock_name].append(item)
        aggregated[category] = stock_groups
    
    return aggregated


def get_feishu_token():
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': FEISHU_APP_ID, 'app_secret': FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    return data.get('tenant_access_token')


def send_feishu_msg(receive_id: str, receive_id_type: str, card: dict):
    """发送飞书卡片消息"""
    token = get_feishu_token()
    if not token:
        print("[ERROR] 获取飞书 token 失败")
        return False

    resp = requests.post(
        'https://open.feishu.cn/open-apis/im/v1/messages',
        params={'receive_id_type': receive_id_type},
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json={
            'receive_id': receive_id,
            'msg_type': 'interactive',
            'content': json.dumps(card, ensure_ascii=False),
        },
        timeout=15,
    )
    data = resp.json()
    if data.get('code') == 0:
        print(f"[OK] 飞书卡片发送成功 → {receive_id}")
        return True
    else:
        print(f"[ERROR] 飞书发送失败: {data}")
        return False


def build_feishu_card(results: dict, date_str: str):
    """构建飞书卡片（按股票聚合，可折叠面板）
    
    results 结构：{category: {stock_name: [items]}}
    """
    
    # 统计总数（股票数和公告数）
    total_stocks = sum(len(stock_groups) for stock_groups in results.values())
    total_notices = sum(
        sum(len(items) for items in stock_groups.values())
        for stock_groups in results.values()
    )
    
    if total_notices == 0:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"📊 全市场公告扫描 {date_str}"
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": "今日无重要公告"
                        }
                    }
                ]
            }
        }
    
    # 构建分类内容
    elements = []
    
    # 添加总览
    elements.append({
        "tag": "div",
        "text": {
            "tag": "plain_text",
            "content": f"共 {total_stocks} 只股票，{total_notices} 条公告"
        }
    })
    
    elements.append({"tag": "hr"})
    
    # 按类别展示（可折叠）
    for category, stock_groups in results.items():
        if not stock_groups:
            continue
        
        # 构建该类别的股票列表
        category_elements = []
        
        for stock_name, items in stock_groups.items():
            # 股票名作为小标题
            category_elements.append({
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"▸ {stock_name} ({len(items)}条)"
                }
            })
            
            # 该股票的公告列表
            for item in items:
                title = item.get('title', item.get('raw_title', ''))
                category_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"  • {title}"
                    }
                })
        
        # 可折叠面板
        elements.append({
            "tag": "collapsible_panel",
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{category} ({len(stock_groups)}只股票)"
                }
            },
            "elements": category_elements
        })
    
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 全市场公告扫描 {date_str}"
                },
                "template": "blue"
            },
            "elements": elements
        }
    }


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="全市场公告扫描器")
    parser.add_argument("--date", help="扫描日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--output", help="输出 JSON 文件路径（额外保存）")
    parser.add_argument("--send", action="store_true", help="发送飞书卡片")
    parser.add_argument("--chat-id", help="飞书群 chat_id")
    
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    # 扫描公告
    results = scan_market_announcements(date_str)
    
    # 默认保存到 detail/ 目录（供前端读取）
    detail_dir = SCRIPT_DIR / "detail"
    detail_dir.mkdir(parents=True, exist_ok=True)
    detail_path = detail_dir / f"{date_str}.json"
    
    output_data = {
        "date": date_str,
        "scan_time": datetime.now().isoformat(),
        "results": results
    }
    
    with open(detail_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {detail_path}")
    
    # 额外保存
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"额外保存到: {output_path}")
    
    # 发送飞书
    if args.send:
        card = build_feishu_card(results, date_str)
        chat_id = args.chat_id or "oc_1e941df394190b21d4c4edd83deae4f3"
        receive_id_type = "open_id" if chat_id.startswith("ou_") else "chat_id"
        
        success = send_feishu_msg(
            receive_id=chat_id,
            receive_id_type=receive_id_type,
            card=card["card"]
        )
        
        if success:
            print(f"\n飞书卡片已发送到: {chat_id}")
        else:
            print("\n飞书卡片发送失败")
    
    # 打印统计
    print("\n=== 扫描统计 ===")
    total = 0
    for category, stock_groups in results.items():
        count = sum(len(items) for items in stock_groups.values())
        stocks = len(stock_groups)
        print(f"{category}: {stocks} 只股票, {count} 条公告")
        total += count
    print(f"总计: {total} 条")


if __name__ == "__main__":
    main()
