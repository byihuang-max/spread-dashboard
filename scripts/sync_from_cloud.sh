#!/usr/bin/env bash
# 从腾讯云生产环境单向拉取业务数据到本地（只读副本）。
# 真源永远是腾讯云，本地仅供查看/开发，绝不反向推。
# 用法: bash scripts/sync_from_cloud.sh
set -euo pipefail

CLOUD="ubuntu@111.229.129.146"
CLOUD_DIR="/home/ubuntu/gamt-dashboard"
LOCAL_DIR="/Users/apple/Desktop/gamt-dashboard"

echo "== 从腾讯云同步业务数据（单向，云 -> 本地）=="

# 1) 看板用户库
echo "[1/2] 看板用户库 server/users.db ..."
rsync -az --checksum \
  "${CLOUD}:${CLOUD_DIR}/server/users.db" \
  "${LOCAL_DIR}/server/users.db"

# 2) 邮件订阅者名单
echo "[2/2] 邮件订阅 env_fit/momentum_stock/email_subscribers.json ..."
rsync -az --checksum \
  "${CLOUD}:${CLOUD_DIR}/env_fit/momentum_stock/email_subscribers.json" \
  "${LOCAL_DIR}/env_fit/momentum_stock/email_subscribers.json"

# 统计
echo "== 同步完成，本地当前状态 =="
/opt/homebrew/bin/python3 - <<'PY'
import sqlite3, json
db = "/Users/apple/Desktop/gamt-dashboard/server/users.db"
n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM users").fetchone()[0]
print(f"  看板用户: {n} 人")
j = json.load(open("/Users/apple/Desktop/gamt-dashboard/env_fit/momentum_stock/email_subscribers.json", encoding="utf-8"))
subs = j.get("subscribers", j if isinstance(j, list) else [])
print(f"  邮件订阅: {len(subs)} 人")
PY

echo "提示: 本地为只读副本，任何增删改请在腾讯云操作后再跑此脚本。"
