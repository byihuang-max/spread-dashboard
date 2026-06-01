#!/usr/bin/env python3
"""
Kimi 联网搜索工具 — 通用封装

用法:
    from kimi_search import search, search_batch

    result = search("2024年北向资金披露规则变化")
    results = search_batch(["query1", "query2"])

命令行:
    python3 kimi_search.py "你的搜索问题"
"""

import json
import os
import sys
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config', 'api_keys.json')


def _load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


_CONFIG = _load_config()
API_KEY = _CONFIG.get('kimi_api_key', '')
BASE_URL = _CONFIG.get('kimi_base_url', 'https://api.moonshot.cn/v1')

if not API_KEY:
    raise ValueError("kimi_api_key 未配置")


def search(query: str, model: str = 'moonshot-v1-128k', temperature: float = 0.3,
           timeout: int = 60, max_retries: int = 2) -> str:
    """
    调用 Kimi 联网搜索，返回文本结果。

    Kimi 的联网搜索通过 tool_calls 机制实现：
    1. 第一轮请求带 $web_search 工具，Kimi 决定是否搜索
    2. 如果触发搜索，返回 tool_calls + 搜索结果
    3. 第二轮把搜索结果喂回去，得到最终回答

    Args:
        query: 搜索问题
        model: 模型名称
        temperature: 温度参数
        timeout: 请求超时秒数
        max_retries: 最大重试次数

    Returns:
        搜索结果文本，失败返回空字符串
    """
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    messages = [{'role': 'user', 'content': query}]
    payload = {
        'model': model,
        'messages': messages,
        'tools': [{'type': 'builtin_function', 'function': {'name': '$web_search'}}],
        'temperature': temperature,
    }

    for attempt in range(max_retries + 1):
        try:
            # Step 1: 发送请求，可能触发 tool_calls
            resp = requests.post(
                f'{BASE_URL}/chat/completions',
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data['choices'][0]
            msg = choice['message']

            # 如果有 tool_calls，需要第二轮
            if msg.get('tool_calls'):
                tool_call = msg['tool_calls'][0]
                tool_id = tool_call['id']
                search_result = msg.get('content', '') or ''

                messages_round2 = messages + [
                    msg,  # assistant with tool_calls
                    {
                        'role': 'tool',
                        'tool_call_id': tool_id,
                        'content': search_result,
                    }
                ]
                payload2 = {
                    'model': model,
                    'messages': messages_round2,
                    'temperature': temperature,
                }
                resp2 = requests.post(
                    f'{BASE_URL}/chat/completions',
                    headers=headers,
                    json=payload2,
                    timeout=timeout,
                )
                resp2.raise_for_status()
                data2 = resp2.json()
                return data2['choices'][0]['message']['content']
            else:
                return msg.get('content', '')

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  [Kimi] 频率限制，等待 {wait}s...")
                time.sleep(wait)
                continue
            if attempt < max_retries:
                time.sleep(2)
                continue
            print(f"  [Kimi] 搜索失败: {e}")
            return ''
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            print(f"  [Kimi] 搜索失败: {e}")
            return ''


def search_batch(queries: list, interval: float = 1.5, verbose: bool = True) -> list:
    """
    批量搜索，带间隔避免频率限制。

    Args:
        queries: 问题列表
        interval: 每次搜索间隔秒数
        verbose: 是否打印进度

    Returns:
        结果列表，与 queries 一一对应
    """
    results = []
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(interval)
        if verbose:
            print(f"  [Kimi] ({i+1}/{len(queries)}) {q[:50]}...")
        result = search(q)
        results.append(result)
    return results


# ── 命令行入口 ──
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 kimi_search.py \"你的搜索问题\"")
        sys.exit(1)

    query = ' '.join(sys.argv[1:])
    print(f"搜索: {query}\n")
    result = search(query)
    print(result)
