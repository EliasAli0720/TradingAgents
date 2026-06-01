#!/usr/bin/env bash
# Start the React frontend for local development.
#
# Defaults to the Electron desktop shell because that is the usual frontend
# development target in this repo. Use FRONTEND_TARGET=browser for Vite only.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"

HOST="${FRONTEND_HOST:-127.0.0.1}"
PORT="${FRONTEND_PORT:-5173}"
TARGET="${FRONTEND_TARGET:-electron}"
API_HEALTH_URL="${FRONTEND_API_HEALTH_URL:-http://127.0.0.1:8000/health}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Missing command: $1" >&2
    exit 1
  fi
}

healthcheck_api() {
  if command -v curl >/dev/null 2>&1 && curl -fsS "$API_HEALTH_URL" >/dev/null 2>&1; then
    echo "[INFO] API is reachable: $API_HEALTH_URL"
    return 0
  fi

  echo "[WARN] API is not reachable at $API_HEALTH_URL" >&2
  echo "[WARN] In another terminal, run: ./start.sh api" >&2
}

ensure_node_modules() {
  if [ -d "$WEB_DIR/node_modules" ]; then
    return 0
  fi

  echo "[INFO] Installing frontend dependencies with pnpm..."
  (cd "$WEB_DIR" && pnpm install)
}

run_cmd() {
  echo "[INFO] $*"
  if [ "${FRONTEND_DRY_RUN:-}" = "1" ]; then
    return 0
  fi
  exec "$@"
}

require_command pnpm
ensure_node_modules
healthcheck_api

if [ -x "$ROOT_DIR/.venv/bin/python" ] && [ -z "${SIDECAR_PYTHON:-}" ]; then
  export SIDECAR_PYTHON="$ROOT_DIR/.venv/bin/python"
fi

cd "$WEB_DIR"

case "$TARGET" in
  browser)
    run_cmd pnpm exec vite --host "$HOST" --port "$PORT"
    ;;
  electron|desktop)
    DEV_URL="http://$HOST:$PORT"
    run_cmd pnpm exec concurrently -k -n vite,electron \
      "vite --host $HOST --port $PORT" \
      "wait-on tcp:$HOST:$PORT && cross-env VITE_DEV_SERVER_URL=$DEV_URL electron ."
    ;;
  *)
    echo "[ERROR] Unknown FRONTEND_TARGET: $TARGET" >&2
    echo "        Expected: electron, desktop, or browser" >&2
    exit 1
    ;;
esac
