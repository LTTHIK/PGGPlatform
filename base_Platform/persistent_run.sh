#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${SCRIPT_DIR}/backend" && -d "${SCRIPT_DIR}/frontend" ]]; then
  PROJECT_ROOT="${SCRIPT_DIR}"
else
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
LOG_DIR="${PROJECT_ROOT}/runtime-logs"
PID_DIR="${PROJECT_ROOT}/runtime-pids"

BACKEND_PID_FILE="${PID_DIR}/backend.pid"
FRONTEND_PID_FILE="${PID_DIR}/frontend.pid"
BACKEND_LOG_FILE="${LOG_DIR}/backend.log"
FRONTEND_LOG_FILE="${LOG_DIR}/frontend.log"
BACKEND_EXIT_LOG_FILE="${LOG_DIR}/backend-exit.log"
BACKEND_MEM_LOG_FILE="${LOG_DIR}/backend-mem.log"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-18000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FRONTEND_STRICT_PORT="${FRONTEND_STRICT_PORT:-true}"
VENV_DIR="${VENV_DIR:-${PROJECT_ROOT}/.venv}"
AUTO_INSTALL_BACKEND_DEPS="${AUTO_INSTALL_BACKEND_DEPS:-true}"

resolve_python_bin() {
  local candidate
  local venv_python="${VENV_DIR}/bin/python"
  local venv_python3="${VENV_DIR}/bin/python3"
  local venv_python310="${VENV_DIR}/bin/python3.10"
  for candidate in "${venv_python}" "${venv_python3}" "${venv_python310}"; do
    if [[ -x "${candidate}" ]] && "${candidate}" --version >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done

  if [[ -d "${VENV_DIR}" ]] && [[ -x "/usr/bin/python3.10" ]]; then
    echo "[self-heal] repairing broken venv python entrypoints: ${VENV_DIR}" >&2
    if /usr/bin/python3.10 -m venv --upgrade --copies "${VENV_DIR}" >/dev/null 2>&1; then
      ln -sf python3.10 "${venv_python3}" || true
      ln -sf python3 "${venv_python}" || true
      for candidate in "${venv_python}" "${venv_python3}" "${venv_python310}"; do
        if [[ -x "${candidate}" ]] && "${candidate}" --version >/dev/null 2>&1; then
          echo "${candidate}"
          return 0
        fi
      done
    fi
  fi
  if [[ "${ALLOW_SYSTEM_PYTHON:-false}" != "true" ]]; then
    return 1
  fi
  for candidate in \
    "$(command -v python3 2>/dev/null || true)" \
    "$(command -v python 2>/dev/null || true)"; do
    [[ -n "${candidate}" ]] || continue
    [[ -x "${candidate}" ]] || continue
    if "${candidate}" --version >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

if [[ -x "${FRONTEND_DIR}/node_modules/.bin/vite" ]]; then
  FRONTEND_CMD="${FRONTEND_DIR}/node_modules/.bin/vite"
else
  FRONTEND_CMD="npx vite"
fi

mkdir -p "${LOG_DIR}" "${PID_DIR}"

iso_now() {
  date -Iseconds
}

is_pid_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

port_listener_pids() {
  local host="$1"
  local port="$2"
  ss -ltnp 2>/dev/null \
    | awk -v h="${host}:${port}" '
        $4 ~ h {
          if (match($0, /pid=[0-9]+/)) {
            pidkv = substr($0, RSTART, RLENGTH)
            gsub("pid=", "", pidkv)
            print pidkv
          }
        }
      ' \
    | sort -u
}

cleanup_backend_port() {
  local pids
  pids="$(port_listener_pids "${BACKEND_HOST}" "${BACKEND_PORT}" || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  echo "[backend-port-cleanup] ts=$(iso_now) found listeners on ${BACKEND_HOST}:${BACKEND_PORT}: ${pids}" >>"${BACKEND_LOG_FILE}"
  for pid in ${pids}; do
    if is_pid_running "${pid}"; then
      kill "${pid}" 2>/dev/null || true
    fi
  done
  sleep 1
  pids="$(port_listener_pids "${BACKEND_HOST}" "${BACKEND_PORT}" || true)"
  if [[ -n "${pids}" ]]; then
    for pid in ${pids}; do
      if is_pid_running "${pid}"; then
        kill -9 "${pid}" 2>/dev/null || true
      fi
    done
    sleep 1
  fi
}

start_backend() {
  local python_bin
  if ! python_bin="$(resolve_python_bin)"; then
    echo "Backend start failed: virtualenv is missing or broken: ${VENV_DIR}"
    echo "Run: rm -rf \"${VENV_DIR}\" && python3 -m venv --copies \"${VENV_DIR}\""
    echo "Then install deps: \"${VENV_DIR}/bin/pip\" install -r backend/requirements.txt && \"${VENV_DIR}/bin/pip\" install -e ./_wenet_pkg"
    echo "If you really need system python fallback, set ALLOW_SYSTEM_PYTHON=true."
    return 1
  fi
  if ! "${python_bin}" -c "import uvicorn, psycopg" >/dev/null 2>&1; then
    if [[ "${AUTO_INSTALL_BACKEND_DEPS}" == "true" ]]; then
      local pip_bin="${python_bin%/python}/pip"
      if [[ ! -x "${pip_bin}" ]]; then
        pip_bin="${python_bin} -m pip"
      fi
      echo "[self-heal] backend deps missing (uvicorn/psycopg), installing requirements..."
      cd "${PROJECT_ROOT}"
      if [[ "${pip_bin}" == *" -m pip" ]]; then
        ${python_bin} -m pip install -r backend/requirements.txt >/dev/null
      else
        "${pip_bin}" install -r backend/requirements.txt >/dev/null
      fi
      if ! "${python_bin}" -c "import uvicorn, psycopg" >/dev/null 2>&1; then
        echo "Backend start failed: dependencies still missing in ${python_bin}"
        echo "Run manually: \"${python_bin}\" -m pip install -r backend/requirements.txt"
        return 1
      fi
    else
      echo "Backend start failed: uvicorn/psycopg missing in selected interpreter: ${python_bin}"
      echo "Run: \"${python_bin}\" -m pip install -r backend/requirements.txt"
      return 1
    fi
  fi

  if [[ -f "${BACKEND_PID_FILE}" ]] && is_pid_running "$(cat "${BACKEND_PID_FILE}")"; then
    echo "Backend already running (pid: $(cat "${BACKEND_PID_FILE}"))"
    return
  fi

  cleanup_backend_port
  cd "${PROJECT_ROOT}"
  echo "[backend-start] ts=$(iso_now) python=${python_bin} host=${BACKEND_HOST} port=${BACKEND_PORT}" >>"${BACKEND_LOG_FILE}"
  nohup bash -lc "\"${python_bin}\" -m uvicorn backend.app:app --host \"${BACKEND_HOST}\" --port \"${BACKEND_PORT}\" >>\"${BACKEND_LOG_FILE}\" 2>&1; ec=\$?; reason='exit'; if [[ \"\${ec}\" -eq 0 ]]; then reason='normal'; fi; if [[ \"\${ec}\" -eq 1 ]]; then reason='runtime/startup failure'; fi; if [[ \"\${ec}\" -eq 137 ]]; then reason='SIGKILL(possible OOM or external kill)'; fi; if [[ \"\${ec}\" -eq 143 ]]; then reason='SIGTERM(graceful stop)'; fi; echo \"[backend-exit] ts=$(iso_now) exit_code=\${ec} reason=\${reason}\" >>\"${BACKEND_EXIT_LOG_FILE}\"" &
  echo $! > "${BACKEND_PID_FILE}"
  local backend_pid
  backend_pid="$(cat "${BACKEND_PID_FILE}")"
  nohup bash -lc "pid=${backend_pid}; while kill -0 \"\${pid}\" 2>/dev/null; do ts=\$(date -Iseconds); rss_kb=\$(awk '/VmRSS/{print \$2}' /proc/\${pid}/status 2>/dev/null || echo 0); vms_kb=\$(awk '/VmSize/{print \$2}' /proc/\${pid}/status 2>/dev/null || echo 0); echo \"[backend-mem] ts=\${ts} pid=\${pid} rss_kb=\${rss_kb} vms_kb=\${vms_kb}\" >>\"${BACKEND_MEM_LOG_FILE}\"; sleep 5; done" >/dev/null 2>&1 &
  sleep 1
  if ! is_pid_running "$(cat "${BACKEND_PID_FILE}")"; then
    echo "Backend failed right after start. Last backend log:"
    awk 'NR>0{a[NR]=$0} END{start=(NR-29>1?NR-29:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_LOG_FILE}"
    rm -f "${BACKEND_PID_FILE}"
    return 1
  fi
  local health_url="http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
  local ok=0
  for _ in 1 2 3 4 5; do
    if curl -fsS "${health_url}" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "${ok}" -eq 1 ]]; then
    echo "[backend-ready] ts=$(iso_now) health=${health_url}" >>"${BACKEND_LOG_FILE}"
  else
    echo "[backend-warn] ts=$(iso_now) health check failed: ${health_url}" >>"${BACKEND_LOG_FILE}"
  fi
  echo "Backend started (pid: $(cat "${BACKEND_PID_FILE}"))"
}

start_frontend() {
  if [[ -f "${FRONTEND_PID_FILE}" ]] && is_pid_running "$(cat "${FRONTEND_PID_FILE}")"; then
    echo "Frontend already running (pid: $(cat "${FRONTEND_PID_FILE}"))"
    return
  fi

  cd "${FRONTEND_DIR}"
  if [[ "${FRONTEND_STRICT_PORT}" == "true" ]]; then
    nohup bash -lc "cd \"${FRONTEND_DIR}\" && exec ${FRONTEND_CMD} --host \"${FRONTEND_HOST}\" --port \"${FRONTEND_PORT}\" --strictPort" \
      >>"${FRONTEND_LOG_FILE}" 2>&1 &
  else
    nohup bash -lc "cd \"${FRONTEND_DIR}\" && exec ${FRONTEND_CMD} --host \"${FRONTEND_HOST}\" --port \"${FRONTEND_PORT}\"" \
      >>"${FRONTEND_LOG_FILE}" 2>&1 &
  fi
  echo $! > "${FRONTEND_PID_FILE}"
  echo "Frontend started (pid: $(cat "${FRONTEND_PID_FILE}"))"
}

stop_process() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "${pid_file}" ]]; then
    echo "${name} not running (pid file missing)"
    return
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if is_pid_running "${pid}"; then
    kill "${pid}" || true
    sleep 1
    if is_pid_running "${pid}"; then
      kill -9 "${pid}" || true
    fi
    echo "${name} stopped"
  else
    echo "${name} not running (stale pid file)"
  fi
  rm -f "${pid_file}"
}

status_process() {
  local name="$1"
  local pid_file="$2"
  if [[ -f "${pid_file}" ]] && is_pid_running "$(cat "${pid_file}")"; then
    echo "${name}: running (pid: $(cat "${pid_file}"))"
  else
    echo "${name}: stopped"
    if [[ "${name}" == "Backend" ]]; then
      if [[ -f "${BACKEND_EXIT_LOG_FILE}" ]]; then
        echo "Backend last exits:"
        awk 'NR>0{a[NR]=$0} END{start=(NR-4>1?NR-4:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_EXIT_LOG_FILE}"
      fi
      if [[ -f "${BACKEND_LOG_FILE}" ]]; then
        echo "Backend recent log tail:"
        awk 'NR>0{a[NR]=$0} END{start=(NR-14>1?NR-14:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_LOG_FILE}"
      fi
    fi
  fi
}

logs() {
  echo "==== backend.log (last 40 lines) ===="
  if [[ -f "${BACKEND_LOG_FILE}" ]]; then
    awk 'NR>0{a[NR]=$0} END{start=(NR-39>1?NR-39:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_LOG_FILE}"
  else
    echo "(no backend log yet)"
  fi

  echo "==== backend-exit.log (last 20 lines) ===="
  if [[ -f "${BACKEND_EXIT_LOG_FILE}" ]]; then
    awk 'NR>0{a[NR]=$0} END{start=(NR-19>1?NR-19:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_EXIT_LOG_FILE}"
  else
    echo "(no backend exit log yet)"
  fi

  echo "==== backend-mem.log (last 20 lines) ===="
  if [[ -f "${BACKEND_MEM_LOG_FILE}" ]]; then
    awk 'NR>0{a[NR]=$0} END{start=(NR-19>1?NR-19:1); for(i=start;i<=NR;i++) print a[i]}' "${BACKEND_MEM_LOG_FILE}"
  else
    echo "(no backend memory log yet)"
  fi

  echo "==== frontend.log (last 40 lines) ===="
  if [[ -f "${FRONTEND_LOG_FILE}" ]]; then
    awk 'NR>0{a[NR]=$0} END{start=(NR-39>1?NR-39:1); for(i=start;i<=NR;i++) print a[i]}' "${FRONTEND_LOG_FILE}"
  else
    echo "(no frontend log yet)"
  fi
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|restart|status|logs>

Environment variables:
  BACKEND_HOST   (default: 127.0.0.1)
  BACKEND_PORT   (default: 18000)
  FRONTEND_HOST  (default: 0.0.0.0)
  FRONTEND_PORT  (default: 5173)
  FRONTEND_STRICT_PORT (default: true)
  VENV_DIR (default: ${PROJECT_ROOT}/.venv)
  AUTO_INSTALL_BACKEND_DEPS (default: true)
EOF
}

cmd="${1:-}"
case "${cmd}" in
  start)
    start_backend
    start_frontend
    ;;
  stop)
    stop_process "Frontend" "${FRONTEND_PID_FILE}"
    stop_process "Backend" "${BACKEND_PID_FILE}"
    ;;
  restart)
    stop_process "Frontend" "${FRONTEND_PID_FILE}"
    stop_process "Backend" "${BACKEND_PID_FILE}"
    start_backend
    start_frontend
    ;;
  status)
    status_process "Backend" "${BACKEND_PID_FILE}"
    status_process "Frontend" "${FRONTEND_PID_FILE}"
    ;;
  logs)
    logs
    ;;
  *)
    usage
    exit 1
    ;;
esac
