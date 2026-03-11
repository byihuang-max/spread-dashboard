#!/bin/bash
# 同步看板代码到腾讯云
# 用法：bash scripts/sync-to-cloud.sh

REMOTE="ubuntu@111.229.129.146"
REMOTE_PATH="~/gamt-dashboard/"
LOCAL_PATH="$(dirname "$0")/../"

echo "[$(date '+%H:%M:%S')] 同步到云端..."

rsync -az --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='venv/' \
  --exclude='_cache/' \
  --exclude='*.db' \
  -e "ssh -o ConnectTimeout=10 -o ServerAliveInterval=15" \
  "$LOCAL_PATH" "$REMOTE:$REMOTE_PATH"

if [ $? -eq 0 ]; then
  echo "[$(date '+%H:%M:%S')] ✅ 同步完成"
  # 重启后端服务让新代码生效
  ssh -o ConnectTimeout=10 "$REMOTE" 'sudo systemctl restart gamt' 2>/dev/null
  echo "[$(date '+%H:%M:%S')] ✅ 后端已重启"
else
  echo "[$(date '+%H:%M:%S')] ❌ 同步失败"
  exit 1
fi
