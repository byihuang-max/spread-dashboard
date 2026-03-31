#!/usr/bin/env python3
"""
iFind MCP 基本面增强模块
"""
import json
import subprocess
from pathlib import Path

IFIND_DIR = Path.home() / '.openclaw' / 'extensions' / 'ifind-finance-data'
CALL_NODE = IFIND_DIR / 'call-node.js'


def _run_ifind(tool_name: str, query: str) -> dict:
    script = f"""
const {{ call }} = require('{CALL_NODE.as_posix()}');
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
        return json.loads(out) if out else {'ok': False, 'error': 'empty output'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _extract_text(resp: dict) -> str:
    if not isinstance(resp, dict):
        return ''
    data = resp.get('data')
    if isinstance(data, dict):
        if isinstance(data.get('text'), str):
            return data.get('text', '')
        if isinstance(data.get('answer'), str):
            return data.get('answer', '')
    if isinstance(resp.get('error'), str):
        return resp['error']
    return ''


def get_fundamentals(ts_code: str, stock_name: str = None) -> dict:
    name = stock_name or ts_code
    summary = _run_ifind('get_stock_summary', f'{name}公司简介、所属行业、主营业务')
    financials = _run_ifind('get_stock_financials', f'{name}最新一期的ROE、营业总收入同比增长率、净利润同比增长率')
    info = _run_ifind('get_stock_info', f'{name}总市值、市净率、市盈率TTM、所属申万行业')

    return {
        'summary_text': _extract_text(summary),
        'financials_text': _extract_text(financials),
        'info_text': _extract_text(info),
        'raw_ok': {
            'summary': bool(summary.get('ok')),
            'financials': bool(financials.get('ok')),
            'info': bool(info.get('ok')),
        }
    }
