#!/bin/bash
# 修复 gamt-dashboard 文件权限（幂等，可反复跑）
# 目的：让 nginx(www-data) 能读前端资产，同时锁死敏感目录不被公网下载
#
# 为什么需要它：
#   git reset --hard / 目录重建 会把权限退回默认(常为700)，
#   导致 nginx 进不去目录 → 页面/数据 404。此脚本统一修对。
#
# 用法：bash ~/gamt-dashboard/scripts/fix-perms.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 1) 前端资产目录：允许 www-data 进入(o+x)
#    排除敏感/无关目录
find . -type d \
  ! -path './.git/*' ! -path './.git' \
  ! -path './venv/*' ! -path './venv' \
  ! -path './server/*' ! -path './server' \
  ! -path './zsxq/*' ! -path './zsxq' \
  -exec chmod o+x {} \;

# 2) 前端资产文件：允许 www-data 读取(o+r)
#    只放开静态资产类型，不碰 .py/.db/.env 等
find . -type f \( \
    -name '*.html' -o -name '*.json' -o -name '*.js' -o -name '*.css' \
    -o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.svg' \
    -o -name '*.ico' -o -name '*.webp' -o -name '*.gif' -o -name '*.woff*' \
    -o -name '*.csv' -o -name '*.txt' \
  \) \
  ! -path './.git/*' ! -path './venv/*' \
  ! -path './server/*' ! -path './zsxq/*' \
  -exec chmod o+r {} \;

# 3) 敏感目录：锁死，禁止 www-data 进入(公网访问返回404)
#    server/ 含 users.db、auth.py、源码备份；zsxq/ 含 config.json
chmod o-rwx server zsxq 2>/dev/null || true

echo "[fix-perms] 完成：前端资产已放开，server/ 与 zsxq/ 已锁死"
