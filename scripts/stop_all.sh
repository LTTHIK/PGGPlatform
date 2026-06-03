#!/usr/bin/env bash
# 停止由 start_all.sh 拉起的后台进程（8090 / 18000 / 前端）
# 默认不停止 vLLM 与 PostgreSQL（GPU 模型重启慢）
#
# 用法：
#   ./scripts/stop_all.sh
#   STOP_VLLM=1 ./scripts/stop_all.sh
#   STOP_DOCKER=1 ./scripts/stop_all.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$WS_ROOT/.runtime/pids"
VLLM_ROOT="${VLLM_ROOT:-/mnt/dockerContainerSave/vllm-big-model}"
BP="$WS_ROOT/base_Platform"

STOP_VLLM="${STOP_VLLM:-0}"
STOP_DOCKER="${STOP_DOCKER:-0}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

stop_pidfile() {
  local name="$1"
  local file="$PID_DIR/$name.pid"
  if [[ ! -f "$file" ]]; then
    log "无 PID 文件: $name"
    return 0
  fi
  local pid
  pid="$(cat "$file" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    log "停止 $name (pid=$pid)"
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  else
    log "$name 进程已不存在 (pid=$pid)"
  fi
  rm -f "$file"
}

log "停止 workspace 后台服务…"
stop_pidfile frontend_5173
stop_pidfile backend_18000
stop_pidfile graphrag_8090

# 清理可能遗留的 graphrag index 僵尸
if pgrep -f 'graphrag index' >/dev/null 2>&1; then
  log "结束 graphrag index 子进程"
  pkill -f 'graphrag index' || true
fi

if [[ "$STOP_VLLM" == "1" ]]; then
  log "停止 vLLM (STOP_VLLM=1)"
  pkill -f 'vllm serve' || true
else
  log "保留 vLLM（需停止请: STOP_VLLM=1 $0）"
fi

if [[ "$STOP_DOCKER" == "1" ]]; then
  log "停止 PostgreSQL 容器"
  (cd "$BP" && docker compose -f docker-compose.ltt-pg.yml down) || true
else
  log "保留 PostgreSQL 容器（需停止请: STOP_DOCKER=1 $0）"
fi

log "完成"
