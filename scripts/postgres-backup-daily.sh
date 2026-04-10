#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${APPCENTER_PG_BACKUP_ROOT:-/backup/appcenter-postgresql}"
RETENTION_DAYS="${APPCENTER_PG_RETENTION_DAYS:-30}"
CONFIG_FILE="${APPCENTER_SERVER_CONFIG:-/opt/appcenter/server/config/server.ini}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "missing required command: $1"
    exit 1
  fi
}

require_cmd python3
require_cmd psql
require_cmd pg_dump
require_cmd pg_restore
require_cmd sha256sum

if [[ ! -f "$CONFIG_FILE" ]]; then
  log "config file not found: $CONFIG_FILE"
  exit 1
fi

readarray -t DB_INFO < <(
  python3 - "$CONFIG_FILE" <<'PY'
import configparser
import sys
from urllib.parse import urlparse, unquote

path = sys.argv[1]
parser = configparser.ConfigParser()
with open(path, "r", encoding="utf-8") as fh:
    parser.read_file(fh)
url = parser.get("database", "database_url", fallback="").strip()
if not url:
    raise SystemExit("database_url missing")
parsed = urlparse(url)
dbname = (parsed.path or "/").lstrip("/")
items = [
    parsed.hostname or "",
    str(parsed.port or 5432),
    unquote(parsed.username or ""),
    unquote(parsed.password or ""),
    dbname,
]
for item in items:
    print(item)
PY
)

if [[ "${#DB_INFO[@]}" -lt 5 ]]; then
  log "failed to parse database config"
  exit 1
fi

DB_HOST="${DB_INFO[0]}"
DB_PORT="${DB_INFO[1]}"
DB_USER="${DB_INFO[2]}"
DB_PASSWORD="${DB_INFO[3]}"
PRIMARY_DB="${DB_INFO[4]}"

if [[ -z "$DB_HOST" || -z "$DB_USER" || -z "$PRIMARY_DB" ]]; then
  log "database config is incomplete"
  exit 1
fi

mkdir -p "$BACKUP_ROOT"

readarray -t DATABASES < <(
  PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d postgres \
    -tA \
    -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true AND datname IN ('${PRIMARY_DB}', 'appcenter_test') ORDER BY datname;"
)

if [[ "${#DATABASES[@]}" -eq 0 ]]; then
  log "no target databases found"
  exit 1
fi

backup_database() {
  local db_name="$1"
  local db_dir="$BACKUP_ROOT/$db_name"
  local dump_file="$db_dir/${db_name}_${TIMESTAMP}.dump"
  local sha_file="${dump_file}.sha256"
  local latest_link="$db_dir/latest.dump"
  local latest_sha_link="$db_dir/latest.dump.sha256"

  mkdir -p "$db_dir"

  log "starting backup for database=$db_name path=$dump_file"
  PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$db_name" \
    -Fc \
    -f "$dump_file"

  pg_restore --list "$dump_file" >/dev/null
  sha256sum "$dump_file" > "$sha_file"
  ln -sfn "$(basename "$dump_file")" "$latest_link"
  ln -sfn "$(basename "$sha_file")" "$latest_sha_link"

  find "$db_dir" -maxdepth 1 -type f -name '*.dump' -mtime +"$RETENTION_DAYS" -delete
  find "$db_dir" -maxdepth 1 -type f -name '*.sha256' -mtime +"$RETENTION_DAYS" -delete

  log "backup completed for database=$db_name"
}

for db_name in "${DATABASES[@]}"; do
  [[ -n "$db_name" ]] || continue
  backup_database "$db_name"
done

log "all PostgreSQL backups completed under $BACKUP_ROOT"
