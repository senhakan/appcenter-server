#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/publish-agent-update.sh --version <x.y.z> [options]

Options:
  --version <x.y.z>       Target agent version to publish (required)
  --server-url <url>      AppCenter server base URL (default: http://127.0.0.1:8000)
  --agent-dir <path>      Agent repo path (default: /root/appcenter/agent)
  --username <user>       Admin username (or APPCENTER_ADMIN_USERNAME env)
  --password <pass>       Admin password (or APPCENTER_ADMIN_PASSWORD env)
  --no-build              Skip build and use --file directly
  --file <path>           Existing .exe/.msi file to upload (required with --no-build)
  -h, --help              Show help

Examples:
  APPCENTER_ADMIN_USERNAME=admin APPCENTER_ADMIN_PASSWORD=admin123 \
    scripts/publish-agent-update.sh --version 0.1.18

  scripts/publish-agent-update.sh --version 0.1.19 \
    --username admin --password '***' \
    --file /tmp/appcenter-service.exe --no-build
EOF
}

SERVER_URL="http://127.0.0.1:8000"
AGENT_DIR="/root/appcenter/agent"
VERSION=""
USERNAME="${APPCENTER_ADMIN_USERNAME:-}"
PASSWORD="${APPCENTER_ADMIN_PASSWORD:-}"
NO_BUILD="0"
INPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --server-url) SERVER_URL="${2:-}"; shift 2 ;;
    --agent-dir) AGENT_DIR="${2:-}"; shift 2 ;;
    --username) USERNAME="${2:-}"; shift 2 ;;
    --password) PASSWORD="${2:-}"; shift 2 ;;
    --no-build) NO_BUILD="1"; shift ;;
    --file) INPUT_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "ERROR: --version is required." >&2
  usage
  exit 1
fi

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
  echo "ERROR: username/password required. Use --username/--password or APPCENTER_ADMIN_USERNAME/APPCENTER_ADMIN_PASSWORD." >&2
  exit 1
fi

if [[ "$NO_BUILD" == "1" ]]; then
  if [[ -z "$INPUT_FILE" ]]; then
    echo "ERROR: --file is required with --no-build." >&2
    exit 1
  fi
  if [[ ! -f "$INPUT_FILE" ]]; then
    echo "ERROR: file not found: $INPUT_FILE" >&2
    exit 1
  fi
  ARTIFACT="$INPUT_FILE"
else
  if [[ ! -d "$AGENT_DIR" ]]; then
    echo "ERROR: agent dir not found: $AGENT_DIR" >&2
    exit 1
  fi
  if ! command -v go >/dev/null 2>&1; then
    echo "ERROR: go not found in PATH." >&2
    exit 1
  fi

  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT
  ARTIFACT="$TMP_DIR/appcenter-service-${VERSION}.exe"

  echo "[1/3] Running tests in agent repo..."
  (
    cd "$AGENT_DIR"
    go test ./...
  )

  echo "[2/3] Building Windows service binary..."
  (
    cd "$AGENT_DIR"
    GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o "$ARTIFACT" ./cmd/service
  )
fi

echo "[3/3] Publishing update package via API..."
LOGIN_JSON="$(curl -fsS -X POST \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" \
  "${SERVER_URL%/}/api/v1/auth/login")"

TOKEN="$(
  python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("access_token",""))' <<<"$LOGIN_JSON"
)"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: login failed, no access_token returned." >&2
  exit 1
fi

UPLOAD_JSON="$(curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "version=${VERSION}" \
  -F "file=@${ARTIFACT}" \
  "${SERVER_URL%/}/api/v1/agent-update/upload")"

echo "Publish response:"
python3 -m json.tool <<<"$UPLOAD_JSON"

