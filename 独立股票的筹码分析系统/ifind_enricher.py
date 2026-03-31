#!/usr/bin/env python3
"""
iFind MCP 基本面增强模块（暂时禁用）
"""

def get_fundamentals(ts_code: str, stock_name: str = None) -> dict:
    """暂时返回空，避免 node 依赖问题"""
    return {
        'summary_text': '',
        'financials_text': '',
        'info_text': '',
        'raw_ok': {'summary': False, 'financials': False, 'info': False}
    }
