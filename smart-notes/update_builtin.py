"""
更新 Smart Notes index.html 的 BUILTIN_NOTES
读取 notes/、sessions/、concepts/ 目录下所有 md 文件，重建嵌入数据
"""
import json, re
from pathlib import Path

_BASE = Path(__file__).resolve().parent
INDEX_HTML = _BASE / "index.html"

# 读取所有目录的笔记
entries = []

# 1. notes/ 目录（通过index.json）
NOTES_DIR = _BASE / "notes"
index_json = NOTES_DIR / "index.json"
if index_json.exists():
    with open(index_json, encoding="utf-8") as f:
        index = json.load(f)
    for item in index:
        note_path = NOTES_DIR / item["path"]
        if note_path.exists():
            content = note_path.read_text(encoding="utf-8")
            entries.append({
                "name": item["name"],
                "path": f"notes/{item['path']}",
                "category": item["category"],
                "content": content
            })

# 2. sessions/ 目录（直接扫描）
SESSIONS_DIR = _BASE / "sessions"
if SESSIONS_DIR.exists():
    for md_file in SESSIONS_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        # 从文件名提取标题（去掉日期前缀）
        name = md_file.stem
        if "_" in name:
            name = name.split("_", 1)[1]
        entries.append({
            "name": name,
            "path": f"sessions/{md_file.name}",
            "category": "sessions",
            "content": content
        })

# 3. concepts/ 目录（直接扫描）
CONCEPTS_DIR = _BASE / "concepts"
if CONCEPTS_DIR.exists():
    for md_file in CONCEPTS_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        entries.append({
            "name": md_file.stem,
            "path": f"concepts/{md_file.name}",
            "category": "concepts",
            "content": content
        })

# 序列化
notes_json = json.dumps(entries, ensure_ascii=False)

# 替换 index.html 中的 BUILTIN_NOTES
html = INDEX_HTML.read_text(encoding="utf-8")

pattern = r'const BUILTIN_NOTES = \[.*?\];'
match = re.search(pattern, html, re.DOTALL)
if match:
    new_line = f'const BUILTIN_NOTES = {notes_json};'
    html = html[:match.start()] + new_line + html[match.end():]
    INDEX_HTML.write_text(html, encoding="utf-8")
    print(f"✅ 更新完成，共 {len(entries)} 条笔记")
else:
    print("❌ 找不到 BUILTIN_NOTES 模式")
