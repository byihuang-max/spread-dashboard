#!/bin/bash
# GitHub 月度备份推送
# 用途：把 Gitee 主链的代码定期镜像到 GitHub 做异地备份
# 依赖：本地代理 http://127.0.0.1:7897（Clash/Shadowsocks 等）

set -e

REPO_DIR="$HOME/Desktop/gamt-dashboard"
PROXY="http://127.0.0.1:7897"

cd "$REPO_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 GAMT 看板 · GitHub 备份推送"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. 检测代理
echo "🔍 检测代理 $PROXY ..."
if ! curl -s -x "$PROXY" --max-time 5 -o /dev/null -w "%{http_code}" https://api.github.com | grep -qE "^(200|401)$"; then
    echo "❌ 代理未开启或无法访问 GitHub。请先打开 Clash/代理工具，再重试。"
    exit 1
fi
echo "✅ 代理可用"

# 2. 先和 Gitee 同步（主链）
echo ""
echo "🔄 同步 Gitee 主链..."
git fetch gitee main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse gitee/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    echo "⚠️ 本地落后于 Gitee，先 pull 对齐"
    git pull --no-rebase -X theirs gitee main
fi

# 3. 比较 GitHub 落后多少
echo ""
echo "📊 检查 GitHub 状态..."
HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY git fetch origin main
BEHIND=$(git rev-list --count origin/main..HEAD)
if [ "$BEHIND" = "0" ]; then
    echo "✅ GitHub 已是最新，无需推送"
    exit 0
fi
echo "📈 GitHub 落后本地 $BEHIND 个 commit"

# 4. 推送
echo ""
echo "🚀 推送到 GitHub（通过代理）..."
HTTPS_PROXY=$PROXY HTTP_PROXY=$PROXY git push origin main

echo ""
echo "✅ GitHub 备份推送完成（$BEHIND 个 commit）"
