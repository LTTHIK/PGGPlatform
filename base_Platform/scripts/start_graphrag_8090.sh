#!/usr/bin/env bash
# 启动 GraphRAG 索引 HTTP 服务（8090）
# 加载 qwen_graphrag_demo 的 settings.yaml / prompts / .env
set -euo pipefail

LTT_ROOT="${LTT_ROOT:-/mnt/dockerContainerSave/memory/ltt}"
BP="$LTT_ROOT/workspace/base_Platform"
GR="$LTT_ROOT/workspace/graphrag"
DEMO="$GR/qwen_graphrag_demo"
GMS="$BP/graphrag-model-service"
GR_ENV="$GR/graphragltt_env"

if [[ ! -x "$GR_ENV/bin/uvicorn" ]]; then
  echo "错误: 未找到 $GR_ENV/bin/uvicorn" >&2
  exit 1
fi
if [[ ! -f "$DEMO/settings.yaml" ]]; then
  echo "错误: 未找到 $DEMO/settings.yaml" >&2
  exit 1
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

cd "$GMS"
export PATH="$GR_ENV/bin:$PATH"
exec "$GR_ENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8090
