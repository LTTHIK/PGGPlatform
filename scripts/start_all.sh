#!/usr/bin/env bash
# 一键启动 workspace 全栈：PostgreSQL → 远程 MinIO 自检 → vLLM → GraphRAG 8090 → 后端 18000 → 前端 5173
#
# 用法（在任意目录）：
#   /path/to/workspace/scripts/start_all.sh
#   START_SKIP_VLLM=1 ./scripts/start_all.sh      # 跳过模型（已手动起 vLLM 时）
#   START_SKIP_FRONTEND=1 ./scripts/start_all.sh  # 仅后端与服务
#
# 日志与 PID：workspace/.runtime/logs/  workspace/.runtime/pids/
# 停止：./scripts/stop_all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LTT_ROOT="$(cd "$WS_ROOT/.." && pwd)"
BP="$WS_ROOT/base_Platform"
GR="$WS_ROOT/graphrag"
DEMO="${GRAPHRAG_DEMO_ROOT:-$GR/qwen_graphrag_demo}"
GMS="$BP/graphrag-model-service"
GR_ENV="${GRAPHRAG_VENV:-$GR/graphragltt_env}"
BP_ENV="$BP/basePlatformltt_env"
VLLM_ROOT="${VLLM_ROOT:-/mnt/dockerContainerSave/vllm-big-model}"

RUNTIME="$WS_ROOT/.runtime"
LOG_DIR="$RUNTIME/logs"
PID_DIR="$RUNTIME/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

START_SKIP_VLLM="${START_SKIP_VLLM:-0}"
START_SKIP_FRONTEND="${START_SKIP_FRONTEND:-0}"
START_SKIP_DOCKER="${START_SKIP_DOCKER:-0}"
START_SKIP_MINIO_CHECK="${START_SKIP_MINIO_CHECK:-0}"
MINIO_CHECK_STRICT="${MINIO_CHECK_STRICT:-1}"
VLLM_START_TIMEOUT="${VLLM_START_TIMEOUT:-900}"
SERVICE_WAIT_TIMEOUT="${SERVICE_WAIT_TIMEOUT:-120}"

# MinIO 必须由部署环境或 base_Platform/.env 显式配置
MINIO_ENDPOINT="${MINIO_ENDPOINT:-}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" 2>/dev/null || echo "000"
}

wait_http() {
  local name="$1" url="$2" expect="${3:-200}" max="${4:-$SERVICE_WAIT_TIMEOUT}"
  local i=0
  while (( i < max )); do
    if [[ "$(http_code "$url")" == "$expect" ]]; then
      log "OK  $name → $url"
      return 0
    fi
    sleep 2
    ((i += 2)) || true
  done
  log "超时 $name → $url（期望 HTTP $expect，${max}s 内未就绪）"
  return 1
}

write_pid() {
  echo "$2" > "$PID_DIR/$1.pid"
}

already_running() {
  local pidfile="$PID_DIR/$1.pid"
  [[ -f "$pidfile" ]] || return 1
  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

load_platform_env() {
  if [[ -f "$BP/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$BP/.env"
    set +a
  fi
  : "${MINIO_ENDPOINT:?Set MINIO_ENDPOINT in base_Platform/.env}"
  : "${MINIO_ACCESS_KEY:?Set MINIO_ACCESS_KEY in base_Platform/.env}"
  : "${MINIO_SECRET_KEY:?Set MINIO_SECRET_KEY in base_Platform/.env}"
  export MINIO_ENDPOINT MINIO_ACCESS_KEY MINIO_SECRET_KEY
}

# ── 1. PostgreSQL ─────────────────────────────────────────────
start_postgres() {
  if [[ "$START_SKIP_DOCKER" == "1" ]]; then
    log "跳过 Docker PostgreSQL（START_SKIP_DOCKER=1）"
    return 0
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'ltt-craft-pg'; then
    log "PostgreSQL 容器 ltt-craft-pg 已在运行"
  else
    log "启动 PostgreSQL（docker compose -f docker-compose.ltt-pg.yml）"
    (cd "$BP" && docker compose -f docker-compose.ltt-pg.yml up -d)
  fi
  local i=0
  while (( i < 60 )); do
    if docker exec ltt-craft-pg pg_isready -U craft -d ltt_craft >/dev/null 2>&1; then
      log "OK  PostgreSQL ltt_craft @ 127.0.0.1:5434"
      return 0
    fi
    sleep 2
    ((i += 2)) || true
  done
  log "PostgreSQL 健康检查超时"
  return 1
}

# ── 2. 远程 MinIO（不启动容器，仅连通性自检）────────────────────
check_remote_minio() {
  if [[ "$START_SKIP_MINIO_CHECK" == "1" ]]; then
    log "跳过 MinIO 自检（START_SKIP_MINIO_CHECK=1）"
    return 0
  fi
  log "远程 MinIO: $MINIO_ENDPOINT（不在本机 Docker 内启动）"
  local health_url="${MINIO_ENDPOINT%/}/minio/health/live"
  local code
  code="$(http_code "$health_url")"
  if [[ "$code" == "200" ]]; then
    log "OK  MinIO 健康检查 → $health_url"
    return 0
  fi
  log "MinIO 不可达: $health_url（HTTP $code）" >&2
  log "  请确认网络可达，或检查 base_Platform/.env 中 MINIO_*" >&2
  if [[ "$MINIO_CHECK_STRICT" == "1" ]]; then
    return 1
  fi
  log "警告: MINIO_CHECK_STRICT=0，继续启动（上传/staging 可能失败）"
  return 0
}

# ── 3. vLLM ───────────────────────────────────────────────────
start_vllm() {
  if [[ "$START_SKIP_VLLM" == "1" ]]; then
    log "跳过 vLLM（START_SKIP_VLLM=1）"
    return 0
  fi
  if [[ "$(http_code http://127.0.0.1:8001/v1/models)" == "200" ]] \
    && [[ "$(http_code http://127.0.0.1:8002/v1/models)" == "200" ]]; then
    log "vLLM 已在运行（8001/8002 HTTP 200），跳过 start_all.sh"
    return 0
  fi
  if [[ ! -f "$VLLM_ROOT/start_all.sh" ]]; then
    log "错误: 未找到 $VLLM_ROOT/start_all.sh，请设置 VLLM_ROOT" >&2
    return 1
  fi
  log "启动 vLLM（$VLLM_ROOT/start_all.sh，可能需数分钟）…"
  log "      日志: $VLLM_ROOT/logs/qwen3_vl.log 等"
  if ! timeout "$VLLM_START_TIMEOUT" bash "$VLLM_ROOT/start_all.sh" \
    > "$LOG_DIR/vllm_start_all.log" 2>&1; then
    log "vLLM 启动失败，见 $LOG_DIR/vllm_start_all.log 与 $VLLM_ROOT/logs/" >&2
    tail -30 "$LOG_DIR/vllm_start_all.log" >&2 || true
    return 1
  fi
  wait_http "vLLM Chat" "http://127.0.0.1:8001/v1/models" 200 30
  wait_http "vLLM Embedding" "http://127.0.0.1:8002/v1/models" 200 30
}

# ── 4. GraphRAG 8090 ──────────────────────────────────────────
start_graphrag_8090() {
  if [[ "$(http_code http://127.0.0.1:8090/api/health)" == "200" ]]; then
    log "GraphRAG 8090 已在运行，跳过"
    return 0
  fi
  if already_running graphrag_8090; then
    log "GraphRAG 8090 PID 文件存在且进程存活，跳过"
    return 0
  fi
  if [[ ! -x "$GR_ENV/bin/uvicorn" ]]; then
    log "错误: 未找到 $GR_ENV/bin/uvicorn" >&2
    return 1
  fi
  if [[ ! -f "$DEMO/settings.yaml" ]]; then
    log "错误: 未找到 $DEMO/settings.yaml" >&2
    return 1
  fi
  export GRAPHRAG_CLI="$GR_ENV/bin/graphrag"
  export GRAPHRAG_SETTINGS_TEMPLATE="$DEMO/settings.yaml"
  export GRAPHRAG_PROMPTS_DIR="$DEMO/prompts"
  if [[ -f "$DEMO/.env" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$DEMO/.env"
    set +a
  fi
  log "后台启动 GraphRAG 8090 → $LOG_DIR/graphrag_8090.log"
  (
    cd "$GMS"
    export PATH="$GR_ENV/bin:$PATH"
    exec "$GR_ENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8090
  ) >> "$LOG_DIR/graphrag_8090.log" 2>&1 &
  write_pid graphrag_8090 "$!"
  wait_http "GraphRAG 8090" "http://127.0.0.1:8090/api/health" 200 "$SERVICE_WAIT_TIMEOUT"
}

# ── 5. 后端 18000 ─────────────────────────────────────────────
start_backend() {
  if [[ "$(http_code http://127.0.0.1:18000/docs)" == "200" ]]; then
    log "后端 18000 已在运行，跳过"
    return 0
  fi
  if already_running backend_18000; then
    log "后端 18000 PID 文件存在且进程存活，跳过"
    return 0
  fi
  if [[ ! -x "$BP_ENV/bin/python" ]]; then
    log "错误: 未找到 $BP_ENV/bin/python" >&2
    return 1
  fi
  log "后台启动 base_Platform 18000 → $LOG_DIR/backend_18000.log"
  (
    cd "$BP"
    exec "$BP_ENV/bin/python" -m uvicorn backend.app:app --host 127.0.0.1 --port 18000
  ) >> "$LOG_DIR/backend_18000.log" 2>&1 &
  write_pid backend_18000 "$!"
  wait_http "后端 API" "http://127.0.0.1:18000/docs" 200 "$SERVICE_WAIT_TIMEOUT"
}

# ── 6. 前端 5173 ──────────────────────────────────────────────
start_frontend() {
  if [[ "$START_SKIP_FRONTEND" == "1" ]]; then
    log "跳过前端（START_SKIP_FRONTEND=1）"
    return 0
  fi
  if [[ "$(http_code https://127.0.0.1:5173/)" == "200" ]] \
    || [[ "$(http_code http://127.0.0.1:5173/)" == "200" ]]; then
    log "前端 5173 已在运行，跳过"
    return 0
  fi
  if already_running frontend_5173; then
    log "前端 PID 文件存在且进程存活，跳过"
    return 0
  fi
  if [[ ! -d "$BP/frontend/node_modules" ]]; then
    log "前端 node_modules 不存在，请先: cd $BP/frontend && npm install" >&2
    return 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    log "错误: 未找到 npm" >&2
    return 1
  fi
  log "后台启动 Vite 前端 → $LOG_DIR/frontend_5173.log"
  (
    cd "$BP/frontend"
    exec npm run dev -- --host 0.0.0.0 --port 5173
  ) >> "$LOG_DIR/frontend_5173.log" 2>&1 &
  write_pid frontend_5173 "$!"
  # Vite HTTPS 自签证书，curl 可能失败；仅等待日志出现 Local 或 Network
  local i=0
  while (( i < SERVICE_WAIT_TIMEOUT )); do
    if grep -qE 'Local:|ready in' "$LOG_DIR/frontend_5173.log" 2>/dev/null; then
      log "OK  前端 Vite 已就绪（见 $LOG_DIR/frontend_5173.log）"
      return 0
    fi
    sleep 2
    ((i += 2)) || true
  done
  log "前端启动超时，请查看 $LOG_DIR/frontend_5173.log"
  return 1
}

print_summary() {
  echo ""
  echo "========================================"
  echo " workspace 全栈启动完成"
  echo "========================================"
  echo "  PostgreSQL     postgresql://craft@127.0.0.1:5434/ltt_craft（口令来自环境变量）"
  echo "  MinIO (远程)   $MINIO_ENDPOINT"
  echo "  vLLM Chat      http://127.0.0.1:8001/v1"
  echo "  vLLM Embedding http://127.0.0.1:8002/v1"
  echo "  GraphRAG       http://127.0.0.1:8090/api/health"
  echo "  后端 API       http://127.0.0.1:18000/docs"
  echo "  前端 (HTTPS)   https://127.0.0.1:5173"
  echo "  日志目录       $LOG_DIR"
  echo "  停止命令       $SCRIPT_DIR/stop_all.sh"
  echo "========================================"
  echo ""
  curl -s http://127.0.0.1:8090/api/health 2>/dev/null | python3 -m json.tool 2>/dev/null | head -8 || true
}

main() {
  log "workspace=$WS_ROOT"
  log "base_Platform=$BP"
  load_platform_env
  start_postgres
  check_remote_minio
  start_vllm
  start_graphrag_8090
  start_backend
  start_frontend
  print_summary
}

main "$@"
