#!/bin/bash
# 同步看板代码到腾讯云
# 用法：bash scripts/sync-to-cloud.sh
# 自动尝试 22 → 2222 端口

REMOTE="ubuntu@111.229.129.146"
REMOTE_PATH="~/gamt-dashboard/"
LOCAL_PATH="$(dirname "$0")/../"

RSYNC_EXCLUDE="--exclude=.git --exclude=__pycache__ --exclude=*.pyc --exclude=venv/ --exclude=_cache/ --exclude=*.db --exclude=server/update_log.json"

echo "[$(date '+%H:%M:%S')] 同步到云端..."

# 先试 22 端口
rsync -az --delete $RSYNC_EXCLUDE \
  -e "ssh -o ConnectTimeout=5 -o ServerAliveInterval=15" \
  "$LOCAL_PATH" "$REMOTE:$REMOTE_PATH" 2>/dev/null

if [ $? -eq 0 ]; then
  echo "[$(date '+%H:%M:%S')] ✅ 同步完成"
  ssh -o ConnectTimeout=5 "$REMOTE" 'sudo systemctl restart gamt' 2>/dev/null
  echo "[$(date '+%H:%M:%S')] ✅ 后端已重启"
  exit 0
fi

# 22 失败，试 2222 端口
echo "[$(date '+%H:%M:%S')] 端口22不通，尝试2222..."
rsync -az --delete $RSYNC_EXCLUDE \
  -e "ssh -p 2222 -o ConnectTimeout=5 -o ServerAliveInterval=15" \
  "$LOCAL_PATH" "$REMOTE:$REMOTE_PATH" 2>/dev/null

if [ $? -eq 0 ]; then
  echo "[$(date '+%H:%M:%S')] ✅ 同步完成（端口2222）"
  ssh -p 2222 -o ConnectTimeout=5 "$REMOTE" 'sudo systemctl restart gamt' 2>/dev/null
  echo "[$(date '+%H:%M:%S')] ✅ 后端已重启"
  exit 0
fi

echo "[$(date '+%H:%M:%S')] ❌ 同步失败（22和2222端口都不通）"
exit 1
