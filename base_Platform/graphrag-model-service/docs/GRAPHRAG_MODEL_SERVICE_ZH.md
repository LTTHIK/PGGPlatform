# GraphRAG Model Service（8090）HTTP 契约

> **代码**：`graphrag-model-service/app/main.py`  
> **启动**：[`../scripts/start_graphrag_8090.sh`](../../scripts/start_graphrag_8090.sh)  
> **平台客户端**：`backend/services/graphrag_model_client.py`

---

## 一、服务职责

HTTP 封装 `graphrag index`：

1. 接收平台传入的 **本地文件路径**（staging 后的 `inputs/`）
2. 复制 settings/prompts 到任务目录
3. `prepare_normalized_inputs` → `input/normalized/*.txt`
4. 后台线程执行 `graphrag index --root {task_root}`
5. 写 `artifact_manifest.json`，供平台拉取

**不**连接 MinIO；**不**写 PostgreSQL。

---

## 二、运行根

默认：`graphrag-model-service/graphrag_runs/{model_task_id}/`

```text
graphrag_runs/{model_task_id}/
├── settings.yaml          # 从模板复制
├── prompts/               # 从模板复制
├── input/
│   └── normalized/*.txt
├── output/
│   ├── *.parquet
│   └── lancedb/
├── logs/
│   ├── indexing-engine.log
│   ├── service_index.stdout.log
│   └── service_index.stderr.log
└── artifact_manifest.json
```

---

## 三、环境变量

| 变量 | 说明 |
|------|------|
| `GRAPHRAG_CLI` | graphrag 可执行文件 |
| `GRAPHRAG_SETTINGS_TEMPLATE` | 通常 `qwen_graphrag_demo/settings.yaml` |
| `GRAPHRAG_PROMPTS_DIR` | 通常 `qwen_graphrag_demo/prompts` |
| `GRAPHRAG_RUN_ROOT` | 可选，覆盖 graphrag_runs 父目录 |

8090 启动脚本会 `source qwen_graphrag_demo/.env`：

```env
LOCAL_CHAT_API_BASE=http://127.0.0.1:8001/v1
LOCAL_EMBEDDING_API_BASE=http://127.0.0.1:8002/v1
LOCAL_API_KEY=...
```

---

## 四、API

### GET `/api/health`

```json
{
  "status": "ok",
  "run_root": ".../graphrag_runs",
  "graphrag_cli": ".../graphragltt_env/bin/graphrag",
  "settings_template": ".../qwen_graphrag_demo/settings.yaml",
  "prompts_dir_configured": true
}
```

### POST `/api/graphrag/index-tasks`

**请求**：

```json
{
  "source_files": [
    {
      "local_path": "/abs/.../inputs/1_file.txt",
      "logical_name": "file.txt"
    }
  ],
  "index_options": {}
}
```

**响应**：

```json
{
  "model_task_id": "582a9ce2091246b4b1cdc664ef960cc7",
  "status": "queued"
}
```

- `local_path` 须对 **8090 进程可读**（与 18000 同机或共享盘）
- 异步：立即返回，后台线程跑 index

### GET `/api/graphrag/index-tasks/{model_task_id}`

```json
{
  "model_task_id": "...",
  "status": "running|completed|failed|queued",
  "message": null,
  "task_root": ".../graphrag_runs/...",
  "started_at": "...",
  "finished_at": "...",
  "returncode": 0
}
```

**注意**：8090 **重启后**内存 TaskRegistry 清空，旧 id 会 **404**。

### GET `/api/graphrag/index-tasks/{model_task_id}/artifacts`

任务 completed 后返回 `manifest`（与磁盘 `artifact_manifest.json` 一致）。

运行中返回 **409**。

### GET `/api/graphrag/index-tasks/{model_task_id}/logs`

```json
{ "stdout": "...", "stderr": "..." }
```

---

## 五、与 base_Platform 协作

```text
18000 run-phase1
  → POST index-tasks
  → poll GET status（间隔 GRAPHRAG_POLL_INTERVAL_S）
  → GET artifacts + logs
  → upsert model_artifacts
  → 回填 analysis_task_files.graphrag_input_path
```

轮询超时：`GRAPHRAG_POLL_TIMEOUT_S`（默认 3600）。

---

## 六、启动示例

```bash
cd /mnt/dockerContainerSave/memory/ltt/workspace/base_Platform
./scripts/start_graphrag_8090.sh
```

或手动：

```bash
export GRAPHRAG_CLI=/path/to/graphragltt_env/bin/graphrag
export GRAPHRAG_SETTINGS_TEMPLATE=/path/to/qwen_graphrag_demo/settings.yaml
export GRAPHRAG_PROMPTS_DIR=/path/to/qwen_graphrag_demo/prompts
cd graphrag-model-service
source ../graphrag/qwen_graphrag_demo/.env
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

---

## 七、排错

| 现象 | 处理 |
|------|------|
| prepare 400 | 检查 `local_path` 是否存在、8090 能否读 |
| CLI exit 1 | 看 logs；常见 LLM/Embedding 未起 |
| 挂死在 create_base_text_units | GraphRAG profiling 补丁 |
| 404 model_task_id | 8090 重启，需重新提交任务 |

详见 [`PHASE1_STARTUP_GUIDE_ZH.md`](../../docs/PHASE1_STARTUP_GUIDE_ZH.md)。

---

*版本：2026-06-03*
