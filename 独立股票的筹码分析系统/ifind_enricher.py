#!/usr/bin/env python3
"""
iFind MCP 基本面增强模块
"""
import json
import subprocess
import os
from pathlib import Path


def _find_call_node():
    candidates = [
        Path.home() / '.openclaw/extensions/ifind-finance-data/call-node.js',
        Path('/home/ubuntu/.openclaw/extensions/ifind-finance-data/call-node.js'),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

CALL_NODE = _find_call_node()


def _run_ifind(tool_name: str, query: str) -> dict:
    if not CALL_NODE:
        return {'ok': False, 'error': 'call-node.js not found'}
    script = f"""
const {{ call }} = require('{CALL_NODE}');
(async () => {{
  try {{
    const r = await call('stock', '{tool_name}', {{ query: {json.dumps(query, ensure_ascii=False)} }});
    console.log(JSON.stringify(r));
  }} catch (e) {{
    console.log(JSON.stringify({{ ok:false, error:String(e) }}));
  }}
}})();
"""
    try:
        proc = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=40)
        out = (proc.stdout or '').strip()
        return json.loads(out) if out else {'ok': False, 'error': 'empty'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _extract_text(resp: dict) -> str:
    """从 iFind MCP 嵌套响应中提取文本"""
    if not isinstance(resp, dict):
        return ''
    try:
        # 路径: resp.data.result.content[0].text -> JSON string -> .data.text
        content = resp.get('data', {}).get('result', {}).get('content', [])
        if content and isinstance(content[0], dict):
            inner_str = content[0].get('text', '')
            if inner_str:
                inner = json.loads(inner_str)
                text = inner.get('data', {}).get('text', '')
                if text:
                    return text.strip()
                answer = inner.get('data', {}).get('answer', '')
                if answer:
                    return answer.strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        pass
    # fallback: 直接看顶层
    data = resp.get('data')
    if isinstance(data, dict):
        for key in ('text', 'answer'):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''


def get_fundamentals(ts_code: str, stock_name: str = None) -> dict:
    name = stock_name or ts_code
    summary = _run_ifind('get_stock_summary', f'{name}公司简介、所属行业、主营业务')
    financials = _run_ifind('get_stock_financials', f'{name}最新一期ROE、营收同比增长率、净利润同比增长率')
    info = _run_ifind('get_stock_info', f'{name}总市值、市净率、市盈率TTM、所属申万行业')
    return {
        'summary_text': _extract_text(summary),
        'financials_text': _extract_text(financials),
        'info_text': _extract_text(info),
        'raw_ok': {
            'summary': bool(_extract_text(summary)),
            'financials': bool(_extract_text(financials)),
            'info': bool(_extract_text(info)),
        }
    }
