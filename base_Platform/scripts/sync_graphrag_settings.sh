#!/usr/bin/env bash
# 将 qwen_graphrag_demo/settings.yaml 同步到 graphrag-model-service/templates/
# 供未设置 GRAPHRAG_SETTINGS_TEMPLATE 时的默认模板使用
set -euo pipefail

LTT_ROOT="${LTT_ROOT:-/mnt/dockerContainerSave/memory/ltt}"
DEMO="$LTT_ROOT/workspace/graphrag/qwen_graphrag_demo"
TPL="$LTT_ROOT/workspace/base_Platform/graphrag-model-service/templates"

if [[ ! -f "$DEMO/settings.yaml" ]]; then
  echo "错误: 未找到 $DEMO/settings.yaml" >&2
  exit 1
fi

mkdir -p "$TPL"
cp "$DEMO/settings.yaml" "$TPL/settings.yaml"
echo "已同步: $DEMO/settings.yaml -> $TPL/settings.yaml"
