#!/usr/bin/env bash
# TradingAgents 启动脚本
# 用法：
#   ./start.sh            — 启动 Streamlit 仪表盘（默认）
#   ./start.sh dashboard  — 启动 Streamlit 仪表盘
#   ./start.sh cli        — 交互式 CLI 分析
#   ./start.sh bot        — 自动交易机器人（定时模式）
#   ./start.sh bot-once [TICKER] [DATE]  — 单次运行机器人
#   ./start.sh bot-once AAPL 2024-05-10 --approval  — 附带人工审批
#   ./start.sh api        — 启动本地 API 全套：PostgreSQL + Redis + API + worker
#   ./start.sh api-stop   — 停止本地 API 和 worker（保留 PostgreSQL/Redis 容器）
#   ./start.sh api-status — 查看本地 API/worker 与 Docker 依赖状态

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
MODE="${1:-dashboard}"
RUN_DIR="${TRADINGAGENTS_RUN_DIR:-$HOME/.tradingagents/run}"
LOG_DIR="${TRADINGAGENTS_LOG_DIR:-$HOME/.tradingagents/logs}"
API_HOST="${TRADINGAGENTS_API_HOST:-0.0.0.0}"
API_PORT="${TRADINGAGENTS_API_PORT:-8000}"

# 加载 .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$SCRIPT_DIR/.env"
  set +a
fi

# 检查虚拟环境
if [ ! -x "$VENV_PYTHON" ]; then
  echo "[ERROR] 虚拟环境不存在：$VENV_PYTHON"
  echo "       请先运行：uv sync"
  exit 1
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] 缺少命令：$1"
    exit 1
  fi
}

wait_for_postgres() {
  echo "[INFO] 等待 PostgreSQL ready..."
  for _ in {1..30}; do
    if docker compose exec -T postgres pg_isready -U tradingagents -d tradingagents >/dev/null 2>&1; then
      echo "[INFO] PostgreSQL ready"
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] PostgreSQL 未在预期时间内 ready"
  exit 1
}

wait_for_redis() {
  echo "[INFO] 等待 Redis ready..."
  for _ in {1..30}; do
    if [ "$(docker compose exec -T redis redis-cli ping 2>/dev/null || true)" = "PONG" ]; then
      echo "[INFO] Redis ready"
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] Redis 未在预期时间内 ready"
  exit 1
}

is_pid_running() {
  local pid_file="$1"
  [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1
}

start_background_process() {
  local name="$1"
  shift
  local pid_file="$RUN_DIR/${name}.pid"
  local log_file="$LOG_DIR/${name}.log"

  if is_pid_running "$pid_file"; then
    echo "[INFO] ${name} 已运行，PID=$(cat "$pid_file")"
    return 0
  fi

  rm -f "$pid_file"
  echo "[INFO] 启动 ${name}，日志：$log_file"
  nohup "$@" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
  sleep 1
  if ! is_pid_running "$pid_file"; then
    echo "[ERROR] ${name} 启动失败，查看日志：$log_file"
    tail -n 80 "$log_file" || true
    exit 1
  fi
}

stop_background_process() {
  local name="$1"
  local pid_file="$RUN_DIR/${name}.pid"
  if ! is_pid_running "$pid_file"; then
    echo "[INFO] ${name} 未运行"
    rm -f "$pid_file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  echo "[INFO] 停止 ${name}，PID=$pid"
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..10}; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$pid_file"
      return 0
    fi
    sleep 1
  done
  echo "[WARN] ${name} 未正常退出，强制停止"
  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$pid_file"
}

show_background_status() {
  local name="$1"
  local pid_file="$RUN_DIR/${name}.pid"
  if is_pid_running "$pid_file"; then
    echo "[INFO] ${name} running，PID=$(cat "$pid_file")"
  else
    echo "[INFO] ${name} stopped"
  fi
}

wait_for_api() {
  echo "[INFO] 等待 API ready..."
  for _ in {1..30}; do
    if "$VENV_PYTHON" - <<PY >/dev/null 2>&1
from urllib.request import urlopen
with urlopen("http://127.0.0.1:${API_PORT}/health", timeout=1) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
    then
      echo "[INFO] API ready: http://127.0.0.1:${API_PORT}"
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] API 未在预期时间内 ready，查看日志：$LOG_DIR/tradingagents-api.log"
  tail -n 80 "$LOG_DIR/tradingagents-api.log" || true
  exit 1
}

start_api_stack() {
  require_command docker
  mkdir -p "$RUN_DIR" "$LOG_DIR"

  echo "[INFO] 启动 Docker 依赖：PostgreSQL + Redis"
  docker compose up -d postgres redis
  wait_for_postgres
  wait_for_redis

  : "${DATABASE_URL:?DATABASE_URL 未设置，请检查 .env}"
  : "${REDIS_URL:?REDIS_URL 未设置，请检查 .env}"

  echo "[INFO] 初始化 PostgreSQL 表"
  "$VENV_PYTHON" -c "from tradingagents.api.db import init_db; init_db()"

  start_background_process \
    tradingagents-api \
    "$VENV_PYTHON" -m uvicorn tradingagents.api.app:app \
      --host "$API_HOST" \
      --port "$API_PORT"
  wait_for_api

  start_background_process \
    tradingagents-worker \
    "$VENV_PYTHON" -m celery -A tradingagents.worker.celery_app worker \
      --loglevel=info \
      --concurrency=1

  echo "[INFO] 本地 API 全套已启动"
  echo "       API:    http://127.0.0.1:${API_PORT}"
  echo "       DB:     ${DATABASE_URL}"
  echo "       Redis:  ${REDIS_URL}"
  echo "       Logs:   $LOG_DIR"
  echo "[INFO] 当前脚本保持前台运行。按 Ctrl-C 会停止 API/worker，保留 PostgreSQL/Redis 容器。"

  trap stop_api_stack INT TERM EXIT
  wait "$(cat "$RUN_DIR/tradingagents-api.pid")"
}

stop_api_stack() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  stop_background_process tradingagents-worker
  stop_background_process tradingagents-api
  echo "[INFO] PostgreSQL/Redis 容器仍保留运行。如需停止：docker compose stop postgres redis"
}

status_api_stack() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  show_background_status tradingagents-api
  show_background_status tradingagents-worker
  docker compose ps postgres redis
}

case "$MODE" in
  dashboard)
    echo "[INFO] 启动 Streamlit 仪表盘 → http://localhost:8501"
    STREAMLIT_EMAIL="" exec "$VENV_PYTHON" -m streamlit run \
      "$SCRIPT_DIR/tradingbot/dashboard/app.py" \
      --server.headless true \
      --theme.base dark \
      --server.port 8501
    ;;

  cli)
    echo "[INFO] 启动交互式 CLI 分析"
    exec "$VENV_PYTHON" -m cli.main "${@:2}"
    ;;

  bot)
    echo "[INFO] 启动自动交易机器人（定时模式）— Ctrl-C 退出"
    exec "$VENV_PYTHON" "$SCRIPT_DIR/run_bot.py" "${@:2}"
    ;;

  bot-once)
    TICKER="${2:-}"
    DATE="${3:-}"
    EXTRA_ARGS="${@:4}"
    CMD=("$VENV_PYTHON" "$SCRIPT_DIR/run_bot.py" --once)
    [ -n "$TICKER" ] && CMD+=(--ticker "$TICKER")
    [ -n "$DATE"   ] && CMD+=(--date   "$DATE")
    # shellcheck disable=SC2206
    [ -n "$EXTRA_ARGS" ] && CMD+=($EXTRA_ARGS)
    echo "[INFO] 单次运行机器人：${CMD[*]}"
    exec "${CMD[@]}"
    ;;

  api)
    start_api_stack
    ;;

  api-stop)
    stop_api_stack
    ;;

  api-status)
    status_api_stack
    ;;

  *)
    echo "未知模式：$MODE"
    echo "可选：dashboard | cli | bot | bot-once | api | api-stop | api-status"
    exit 1
    ;;
esac
