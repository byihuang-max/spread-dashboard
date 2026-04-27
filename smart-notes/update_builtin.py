"""
更新 Smart Notes index.html 的 BUILTIN_NOTES
递归扫描所有 .md 文件，重建嵌入数据
"""
import json, re
from pathlib import Path

_BASE = Path(__file__).resolve().parent
INDEX_HTML = _BASE / "index.html"

entries = []
seen_paths = set()

def add_entry(name, rel_path, category, content):
    if rel_path in seen_paths:
        return
    seen_paths.add(rel_path)
    entries.append({
        "name": name,
        "path": rel_path,
        "category": category,
        "content": content
    })

def guess_category(rel_path):
    """从相对路径推断分类"""
    parts = rel_path.split("/")
    if "concepts" in parts:
        return "concepts"
    elif "conversations" in parts:
        return "conversations"
    elif "decisions" in parts:
        return "decisions"
    elif "sessions" in parts:
        return "sessions"
    elif "notes" in parts:
        return "notes"
    else:
        return "notes"

def name_from_stem(stem):
    """从文件名提取显示名"""
    # 去掉日期前缀 (如 2026-03-15_xxx 或 001_xxx)
    name = stem
    if re.match(r'^\d{4}-\d{2}-\d{2}_', name):
        name = name.split("_", 1)[1]
    elif re.match(r'^\d{3}_', name):
        name = name.split("_", 1)[1]
    return name

# 1. 先读 notes/index.json（如果存在）
NOTES_DIR = _BASE / "notes"
index_json = NOTES_DIR / "index.json"
if index_json.exists():
    with open(index_json, encoding="utf-8") as f:
        index = json.load(f)
    for item in index:
        note_path = NOTES_DIR / item["path"]
        if note_path.exists():
            content = note_path.read_text(encoding="utf-8")
            rel = f"notes/{item['path']}"
            add_entry(item["name"], rel, item.get("category", "notes"), content)

# 2. 递归扫描所有 .md 文件
for md_file in sorted(_BASE.rglob("*.md")):
    rel = str(md_file.relative_to(_BASE))
    if rel in seen_paths:
        continue
    content = md_file.read_text(encoding="utf-8")
    category = guess_category(rel)
    name = name_from_stem(md_file.stem)
    add_entry(name, rel, category, content)

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
