#!/bin/bash
# Smart Notes 一键对齐：扫描所有 md → 更新 index.html
cd "$(dirname "$0")"
TOTAL=$(find . -name "*.md" | wc -l | tr -d ' ')
CURRENT=$(grep -o '"name":' index.html | wc -l | tr -d ' ')
echo "📝 文件: ${TOTAL} 条 | HTML: ${CURRENT} 条"
if [ "$TOTAL" != "$CURRENT" ]; then
  /opt/homebrew/bin/python3 update_builtin.py
else
  echo "✅ 已对齐，无需更新"
fi
