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


def _parse_pipe_table(text: str) -> str:
    """把 iFind 返回的竖线分隔表格转成 key: value 格式，支持多表格拼接"""
    if not text or '|' not in text:
        return text
    
    # 先去掉 # 参数说明 和 ```json 块
    clean_lines = []
    in_code_block = False
    in_param_section = False
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped.startswith('# '):
            in_param_section = True
            continue
        if in_param_section:
            if '|' in stripped:
                in_param_section = False
            else:
                continue
        clean_lines.append(stripped)
    
    # 按空行分割成多个表格块
    blocks = []
    current = []
    for line in clean_lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    
    # 简化表头名称
    _header_map = {
        '营业总收入(同比增长率)': '营收同比',
        '营业收入(同比增长率)': '营收同比',
        '净利润(同比增长率)': '净利润同比',
        '归属母公司股东的净利润(同比增长率)': '归母净利润同比',
        '业绩快报-同比增长率：归属母公司股东的净利润': '归母净利润同比(快报)',
        '净资产收益率ROE(加权,公布值)': 'ROE(加权)',
        '净资产收益率ROE(TTM)': 'ROE(TTM)',
        '净资产收益率ROE（TTM，平均）': 'ROE(TTM均)',
        '净资产收益率ROE(扣除／摊薄)': 'ROE(扣非)',
        '净资产收益率ROE(摊薄，含少数股东)': 'ROE(摊薄)',
        '净资产收益率ROE(平均，含少数股东)': 'ROE(平均)',
        '净资产收益率ROE(扣除／加权)': 'ROE(扣非加权)',
        '净资产收益率ROE(平均,同花顺计算)': 'ROE(平均)',
        '净资产收益率ROE(摊薄,公布值)': 'ROE(摊薄)',
        '市净率(PB,MRQ)分位数': 'PB分位数',
        '市盈率(PE,TTM)分位数': 'PE分位数',
    }
    
    all_results = []
    skip = {'证券代码', '证券简称', '日期', '代码', '简称', '交易日期'}
    
    for block in blocks:
        pipe_lines = [l for l in block if '|' in l]
        if len(pipe_lines) < 2:
            continue
        
        # 找表头（第一个非分隔符的竖线行）
        header_line = None
        data_start = 0
        for i, line in enumerate(pipe_lines):
            if not all(c in '-| ' for c in line):
                header_line = line
                data_start = i + 1
                break
        if not header_line:
            continue
        
        headers = [h.strip() for h in header_line.split('|')]
        
        # 找数据行
        data_lines = []
        for i in range(data_start, len(pipe_lines)):
            if not all(c in '-| ' for c in pipe_lines[i]):
                data_lines.append(pipe_lines[i])
        
        if not data_lines:
            continue
        
        # 取第一行数据（最新的）
        values = [v.strip() for v in data_lines[0].split('|')]
        
        # 对齐长度
        min_len = min(len(headers), len(values))
        
        for i in range(min_len):
            h = headers[i].strip()
            v = values[i].strip()
            if h and h not in skip and v and v != '--':
                # 去掉单位后缀
                import re
                h_clean = re.sub(r'（单位[：:].*?）', '', h).strip()
                # 简化表头
                h_clean = _header_map.get(h_clean, h_clean)
                all_results.append(f'{h_clean}：{v}')
    
    return '\n'.join(all_results) if all_results else text


def get_fundamentals(ts_code: str, stock_name: str = None) -> dict:
    name = stock_name or ts_code
    summary = _run_ifind('get_stock_summary', f'{name}公司简介、所属行业、主营业务')
    financials = _run_ifind('get_stock_financials', f'{name}最新一期ROE、营收同比增长率、净利润同比增长率')
    info = _run_ifind('get_stock_info', f'{name}总市值、市净率、市盈率TTM、所属申万行业')
    return {
        'summary_text': _extract_summary_fields(_extract_text(summary)),
        'financials_text': _parse_pipe_table(_extract_text(financials)),
        'info_text': _parse_pipe_table(_extract_text(info)),
        'raw_ok': {
            'summary': bool(_extract_text(summary)),
            'financials': bool(_extract_text(financials)),
            'info': bool(_extract_text(info)),
        }
    }


def _extract_summary_fields(text: str) -> str:
    """从 iFind summary 的复杂表格中提取关键字段"""
    if not text:
        return ''
    
    # 尝试从竖线表格中提取
    lines = text.split('\n')
    pipe_lines = [l.strip() for l in lines if '|' in l and not l.strip().startswith('#')]
    
    if len(pipe_lines) < 2:
        return text
    
    # 找表头
    header_line = None
    for line in pipe_lines:
        if not all(c in '-| :' for c in line):
            header_line = line
            break
    if not header_line:
        return text
    
    headers = [h.strip() for h in header_line.split('|')]
    
    # 找数据行（跳过分隔符）
    data_line = None
    found_header = False
    for line in pipe_lines:
        if line == header_line:
            found_header = True
            continue
        if found_header and not all(c in '-| :' for c in line):
            data_line = line
            break
    
    if not data_line:
        return text
    
    values = [v.strip() for v in data_line.split('|')]
    
    skip = {'证券代码', '证券简称', '日期', '代码', '简称'}
    want = {'所属申万行业', '主营业务', '主营产品名称', '竞争公司', '可比公司', '所属同花顺行业'}
    
    result = []
    min_len = min(len(headers), len(values))
    for i in range(min_len):
        h = headers[i].strip()
        v = values[i].strip()
        if h in want and v and v != '--' and not all(c in '-: ' for c in v):
            result.append(f'{h}：{v}')
    
    return '\n'.join(result) if result else text
