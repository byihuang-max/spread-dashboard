#!/usr/bin/env python3
"""
自动更新 index.html 的 BUILTIN_NOTES
=====================================

在 save_note.py 写完笔记后调用，自动把新笔记插入前端 BUILTIN_NOTES 数组。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "index.html"


def update_builtin_notes(note_path: str, category: str) -> bool:
    """
    把新笔记加入 index.html 的 BUILTIN_NOTES 数组。
    
    Args:
        note_path: 笔记相对路径，如 "notes/engineering/2026-05-07_xxx.md"
        category: 笔记类别，如 "engineering"
    
    Returns:
        True 成功，False 失败
    """
    if not INDEX_HTML.exists():
        return False
    
    # 读取笔记内容
    note_file = ROOT / note_path
    if not note_file.exists():
        return False
    
    content = note_file.read_text(encoding="utf-8")
    
    # 提取标题（第一个 # 开头的行）
    title = ""
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if not title:
        title = note_file.stem
    
    # 类别映射到前端 label
    label_map = {
        "concepts": "概念定义",
        "conversations": "研究对话",
        "decisions": "决策记录",
        "sessions": "会话记录",
        "research/factors": "因子研究",
        "research/strategy": "策略研究",
        "research/narrative": "叙事研究",
        "engineering": "工程",
        "reports": "研报",
        "emerging_markets": "新兴市场",
    }
    label = label_map.get(category, "其他")
    
    # 推断 group（前端用）
    if note_path.startswith("notes/"):
        group = str(Path(note_path).parent)
    else:
        group = category
    
    # 构造新笔记对象
    new_entry = {
        "title": title,
        "path": note_path,
        "content": content,
        "group": group,
        "label": label,
    }
    
    # 读取 index.html
    html = INDEX_HTML.read_text(encoding="utf-8")
    
    # 找到 BUILTIN_NOTES 数组
    pattern = r"(const BUILTIN_NOTES = \[)(.*?)(\];)"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return False
    
    prefix = match.group(1)
    arr_str = match.group(2)
    suffix = match.group(3)
    
    # 解析现有数组
    try:
        arr = json.loads("[" + arr_str + "]")
    except json.JSONDecodeError:
        return False
    
    # 检查是否已存在（避免重复）
    for entry in arr:
        if entry.get("path") == note_path:
            # 已存在，更新内容
            entry["content"] = content
            entry["title"] = title
            # 重新序列化
            new_arr_str = ",\n".join(json.dumps(e, ensure_ascii=False, separators=(',', ': ')) for e in arr)
            new_html = html[:match.start()] + prefix + "\n" + new_arr_str + "\n" + suffix + html[match.end():]
            INDEX_HTML.write_text(new_html, encoding="utf-8")
            return True
    
    # 不存在，追加到末尾
    arr.append(new_entry)
    
    # 重新序列化（单行 JSON，与前端格式一致）
    new_arr_str = ",\n".join(json.dumps(e, ensure_ascii=False, separators=(',', ': ')) for e in arr)
    
    # 替换
    new_html = html[:match.start()] + prefix + "\n" + new_arr_str + "\n" + suffix + html[match.end():]
    
    # 写回
    INDEX_HTML.write_text(new_html, encoding="utf-8")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法：python3 update_builtin_notes.py <note_path> <category>")
        sys.exit(1)
    
    note_path = sys.argv[1]
    category = sys.argv[2]
    
    if update_builtin_notes(note_path, category):
        print(f"✓ 已更新 BUILTIN_NOTES：{note_path}")
    else:
        print(f"✗ 更新失败：{note_path}")
        sys.exit(1)
