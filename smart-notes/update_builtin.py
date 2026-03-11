"""
更新 Smart Notes index.html 的 BUILTIN_NOTES
读取 notes/ 目录下所有 md 文件，重建嵌入数据
"""
import json, re
from pathlib import Path

_BASE = Path(__file__).resolve().parent
NOTES_DIR = _BASE / "notes"
INDEX_HTML = _BASE / "index.html"

# 读 index.json
with open(NOTES_DIR / "index.json", encoding="utf-8") as f:
    index = json.load(f)

# 读每个 note 的内容
entries = []
for item in index:
    note_path = NOTES_DIR / item["path"]
    if note_path.exists():
        content = note_path.read_text(encoding="utf-8")
        entries.append({
            "name": item["name"],
            "path": item["path"],
            "category": item["category"],
            "content": content
        })
    else:
        print(f"⚠️ 找不到: {note_path}")

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
