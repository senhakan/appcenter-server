#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="${1:-/root/appcenter/server/}"
DST_DIR="${2:-/opt/appcenter/server/}"
SERVICE_NAME="${3:-appcenter.service}"

echo "[deploy] rsync ${SRC_DIR} -> ${DST_DIR}"
rsync -az --delete \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  "${SRC_DIR}" "${DST_DIR}"

echo "[deploy] restart ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl is-active "${SERVICE_NAME}"
echo "[deploy] done"
