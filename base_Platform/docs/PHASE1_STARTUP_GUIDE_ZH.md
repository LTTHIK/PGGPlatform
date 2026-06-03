# 阶段一：服务启动与排错指南

> **用途**：日常启动 PostgreSQL / vLLM / GraphRAG 8090 / base_Platform 18000 的顺序、脚本与常见问题。  
> **关联**：[`PHASE1_ACCEPTANCE_TEST_ZH.md`](PHASE1_ACCEPTANCE_TEST_ZH.md)（端到端验收）、[`PHASE1_GRAPHRAG_PIPELINE_ZH.md`](PHASE1_GRAPHRAG_PIPELINE_ZH.md)（七步 API）、[`../../scripts/README_STARTUP_ZH.md`](../../scripts/README_STARTUP_ZH.md)（一键脚本）。

**路径约定**：

```bash
export LTT_ROOT=/mnt/dockerContainerSave/memory/ltt
export WS="$LTT_ROOT/workspace"
export BP="$WS/base_Platform"
export GR="$WS/graphrag"
export DEMO="$GR/qwen_graphrag_demo"
export VLLM=/mnt/dockerContainerSave/vllm-big-model
```

---

## 一、四服务架构

```text
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  vLLM       │     │  GraphRAG   │     │ base_Platform│
│  :8001 Chat │────▶│  8090       │◀────│  :18000      │
│  :8002 Emb  │     │  index CLI  │     │  staging/API │
└─────────────┘     └──────┬──────┘     └──────┬───────┘
                           │                    │
                    graphrag_runs/         PostgreSQL :5434
                    (8090 运行根)          MinIO (远程)
```

| 服务 | 端口 | 虚拟环境 / 容器 | 职责 |
|------|------|-----------------|------|
| PostgreSQL | **5434** | Docker `ltt-craft-pg` | `analysis_tasks`、`file_records` 等 |
| vLLM Chat | **8001** | `vllm-big-model/vllm_env` | GraphRAG 抽图 LLM |
| vLLM Embedding | **8002** | 同上 | GraphRAG 向量 |
| GraphRAG 8090 | **8090** | `graphrag/graphragltt_env` | `graphrag index` HTTP 封装 |
| base_Platform | **18000** | `base_Platform/basePlatformltt_env` | staging、`run-phase1` 编排 |
| 前端 Vite | **5173** | `frontend/node_modules` | HTTPS 开发服（可选） |
| MinIO | **9000** | 远程 `111.228.12.207` | 上传对象存储（不在本机 Docker） |

---

## 二、三套 Python 环境分工

| 环境 | 路径 | 用于 |
|------|------|------|
| `basePlatformltt_env` | `base_Platform/` | 18000 后端（FastAPI、psycopg、boto3） |
| `graphragltt_env` | `graphrag/` | 8090 uvicorn + `graphrag` CLI |
| `vllm_env` | `vllm-big-model/` | vLLM 推理（与 GraphRAG **独立**） |

**不要混用**：8090 的 LLM/Embedding 通过 HTTP 调 `:8001/:8002`，不是直接 import vLLM。

---

## 三、settings / prompts / .env 三件套

8090 索引使用的配置**来源**是 `qwen_graphrag_demo/`，不是直接在 demo 根目录跑平台任务：

| 文件 | 路径 | 作用 |
|------|------|------|
| `settings.yaml` | `graphrag/qwen_graphrag_demo/` | GraphRAG 索引/查询配置模板 |
| `prompts/` | 同上 | 抽图 prompt 模板 |
| `.env` | 同上 | `LOCAL_CHAT_API_BASE=http://127.0.0.1:8001/v1` 等 |

每次 8090 创建索引任务时，会将 settings/prompts **复制**到 `graphrag_runs/{model_task_id}/`。

同步脚本（settings 变更后执行）：

```bash
cd "$BP"
./scripts/sync_graphrag_settings.sh
```

---

## 四、启动脚本总表

| 脚本 | 路径 | 作用 |
|------|------|------|
| **一键全栈** | `workspace/scripts/start_all.sh` | PG → MinIO 自检 → vLLM → 8090 → 18000 → 前端 |
| **一键停止** | `workspace/scripts/stop_all.sh` | 停 8090/18000/前端（默认保留 vLLM、PG） |
| **8090 专用** | `base_Platform/scripts/start_graphrag_8090.sh` | 加载 demo 配置并起 uvicorn |
| **settings 同步** | `base_Platform/scripts/sync_graphrag_settings.sh` | demo settings → 8090 templates |
| **vLLM** | `vllm-big-model/start_all.sh` | Qwen3-VL + Embedding + Reranker |

---

## 五、推荐启动顺序

### 方式 A：一键（推荐）

```bash
cd "$WS"
# vLLM 已在跑时避免 GPU OOM：
START_SKIP_VLLM=1 ./scripts/start_all.sh
```

### 方式 B：四终端手动

**终端 1 — PostgreSQL**

```bash
cd "$BP"
docker compose -f docker-compose.ltt-pg.yml up -d
docker exec ltt-craft-pg pg_isready -U craft -d ltt_craft
```

**终端 2 — vLLM**（若 8001/8002 已 200 则跳过）

```bash
cd "$VLLM"
bash start_all.sh
curl -s http://127.0.0.1:8001/v1/models | head -c 200
curl -s http://127.0.0.1:8002/v1/models | head -c 200
```

**终端 3 — GraphRAG 8090**

```bash
cd "$BP"
./scripts/start_graphrag_8090.sh
# 预期：INFO Uvicorn running on http://127.0.0.1:8090
curl -s http://127.0.0.1:8090/api/health | python3 -m json.tool
```

**终端 4 — base_Platform 18000**

```bash
cd "$BP"
source basePlatformltt_env/bin/activate
python -m uvicorn backend.app:app --host 127.0.0.1 --port 18000
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/docs
```

---

## 六、环境变量（18000）

文件：`base_Platform/.env`（修改后须**重启** 18000）

```env
FILE_INDEX_DATABASE_URL=postgresql://craft:craft@127.0.0.1:5434/ltt_craft
GRAPHRAG_HTTP_BASE_URL=http://127.0.0.1:8090
GRAPHRAG_POLL_INTERVAL_S=5
GRAPHRAG_POLL_TIMEOUT_S=3600
MINIO_ENDPOINT=http://111.228.12.207:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=Minio@123456
JWT_SECRET=dev-insecure-jwt-secret-change-me
```

未配置 `MINIO_*` 时，代码默认连同一远程地址（见 `backend/app.py`）。

---

## 七、自检命令

```bash
curl -s http://127.0.0.1:8001/v1/models | head -c 80; echo " 8001"
curl -s http://127.0.0.1:8002/v1/models | head -c 80; echo " 8002"
curl -s http://127.0.0.1:8090/api/health | python3 -m json.tool
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18000/docs
curl -s "${MINIO_ENDPOINT:-http://111.228.12.207:9000}/minio/health/live"
```

---

## 八、验收问题归档

| # | 现象 | 原因 | 处理 |
|---|------|------|------|
| 1 | staging 报 `MINIO_* required` | 18000 未加载 `.env` 或未重启 | 补 `.env` 并重启 18000 |
| 2 | 8090 index 秒退 code=1 | `LLM_MODEL` / settings 环境变量缺失 | 用 `start_graphrag_8090.sh` 并 `source demo/.env` |
| 3 | 8001/8002 不可达 | vLLM 未起或 GPU OOM | 检查 `nvidia-smi`；**勿重复** `start_all.sh` |
| 4 | vLLM 启动失败「Free memory … less than desired」 | GPU 已被旧 vLLM 占满 | 若 8001/8002 已 200 则跳过；否则先 `pkill -f 'vllm serve'` |
| 5 | `run-phase1` 3600s 超时、`progress=40` | GraphRAG 子进程挂死 | 见 [八点一](#八一-graphrag-workflowprofiler--tracemalloc-挂死2026-05-27) |
| 6 | 看错日志日期 | 看了 `qwen_graphrag_demo/logs/` 手跑 log | 平台任务看 `graphrag_runs/{model_task_id}/logs/` |
| 7 | 8090 重启后旧 task 404 | `TaskRegistry` 在内存 | 重新 `run-phase1` 即可 |
| 8 | 18000 import 失败 | `FILE_INDEX_DATABASE_URL` 缺失 | 检查 `.env` |
| 9 | GraphRAG 第二步起无日志 | tracemalloc 挂死 | profiling 补丁（八点一） |

---

## 八点一、GraphRAG WorkflowProfiler / tracemalloc 挂死（2026-05-27）

### 现象

- `POST /api/analysis/tasks/{id}/run-phase1` 长时间无返回（最多 3600s）
- DB：`progress=40`，`current_step=graphrag_polling`
- 8090 任务 `status=running`，但 `indexing-engine.log` 停在：

```text
Workflow load_input_documents completed successfully
Workflow started: create_base_text_units
（之后无任何新行）
```

### 根因

GraphRAG 3.x 的 `WorkflowProfiler` 在每个 workflow 步骤使用 `tracemalloc` 追踪内存，在本环境第二步 `create_base_text_units` **永久挂死**（非 vLLM/MinIO 问题）。

### 修复

文件：`workspace/graphrag/packages/graphrag/graphrag/index/run/profiling.py`

- **去掉** `tracemalloc.start/stop`
- **保留** `time.time()` 计时；内存字段置 `0`

验证：本地 `graphrag index` 应在 `create_base_text_units` 后继续并完成（约 25～50s）。

### 与业务边界

| 层级 | 是否受影响 |
|------|------------|
| 上传 → MinIO → staging | 否 |
| 8090 `prepare_normalized_inputs` | 否 |
| `graphrag index` 内部 profiling 壳 | **是**（仅此层） |

### 重试前清理

```bash
pkill -f 'graphrag index' || true
# 可选：删除半截 graphrag_runs/{id}/
```

---

## 九、阶段一 API 调用顺序（服务就绪后）

```text
POST /api/workspace/init
POST /api/analysis/tasks          # Step 1–3
POST /api/analysis/tasks/{id}/run-phase1   # Step 4–7
GET  /api/analysis/tasks/{id}     # 轮询直至 completed
```

详见 [`PHASE1_GRAPHRAG_PIPELINE_ZH.md`](PHASE1_GRAPHRAG_PIPELINE_ZH.md) 与 [`PHASE1_ACCEPTANCE_TEST_ZH.md`](PHASE1_ACCEPTANCE_TEST_ZH.md)。

---

## 十、三个「根」路径（勿混淆）

| 路径 | 角色 |
|------|------|
| `graphrag/` + `graphragltt_env` | 引擎源码与 CLI |
| `graphrag/qwen_graphrag_demo/` | **配置模板**（8090 启动指定） |
| `graphrag-model-service/graphrag_runs/{model_task_id}/` | **每次索引真实 `--root`** |
| `workspace/projects/{slug}/runtime/tasks/{task_id}/` | 平台任务目录（inputs、graphrag_out） |

---

*文档版本：2026-06-03，依据 2026-05-28 验收成功态重建。*
