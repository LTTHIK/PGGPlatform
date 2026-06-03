# 阶段一：GraphRAG 七步后端流水线

> **专册说明**：本文是 [`PROJECT_FULL_GUIDE_ZH.md`](../../docs/PROJECT_FULL_GUIDE_ZH.md) 第十一节的展开版；与 `workspace/docs/PHASE1_BACKEND_PIPELINE_ZH.md` 内容同步。  
> **启动前置**：请先阅读 [`PHASE1_STARTUP_GUIDE_ZH.md`](PHASE1_STARTUP_GUIDE_ZH.md)。  
> **代码根目录**：`workspace/base_Platform/backend/`。

---

## 一、目标与范围

**阶段一目标**：用户选定 `file_records` 后，平台完成：

1. 建任务与磁盘目录；
2. 从 MinIO 拉原始文件到任务目录；
3. 调用 GraphRAG HTTP 服务建索引；
4. 把 manifest 写入 `model_artifacts` 并更新任务状态。

**本阶段不做**：CRR/IR 生成、Wiki 自动写入（表已预留，代码未接）。

**主要用到的表**：`analysis_tasks`、`analysis_task_files`、`model_artifacts`、`analysis_task_events`。

---

## 二、七步动作映射

| Step | 动作 | HTTP / 代码 | 表与磁盘 |
|------|------|-------------|----------|
| **1** | 创建 `analysis_tasks` | `POST /api/analysis/tasks` | `status=pending` |
| **2** | 创建 `analysis_task_files` | 同上 | `parse_status=pending` |
| **3** | 创建任务目录 | `ensure_task_subdirs` | `runtime/tasks/{id}/inputs|…` |
| **4** | staging | `POST .../stage` 或 run-phase1 内 | `inputs/`；`parse_status=staged` |
| **5** | 调 8090 | `GraphragModelClient` | `graphrag_runs/{model_task_id}/` |
| **6** | 写 `model_artifacts` | `ArtifactRepository.upsert_from_manifest` | `graphrag_out/artifact_manifest.json` |
| **7** | 更新任务 | `status=completed`，`progress=100` | event `phase1_completed` |

### API 调用顺序

```text
POST /api/analysis/tasks
POST /api/analysis/tasks/{task_id}/run-phase1?skip_staging=false
GET  /api/analysis/tasks/{task_id}
GET  /api/analysis/tasks/{task_id}/files
```

---

## 三、任务目录结构

```text
workspace/projects/{project_slug}/runtime/tasks/{task_id}/
├── inputs/           # Step 4：MinIO 原始副本
├── parsed/           # 兼容保留
├── graphrag_input/   # 平台预留；本阶段路径多在 8090
├── graphrag_out/     # manifest 副本 + graphrag_service_task_root.txt
├── snapshots/        # Phase2 CRR/IR（当前可空）
└── logs/             # graphrag stdout/stderr 副本
```

8090 实际产物在 `graphrag-model-service/graphrag_runs/{model_task_id}/output/`。

---

## 四、核心代码文件

| 文件 | 职责 |
|------|------|
| `routers/analysis_tasks.py` | HTTP 路由 |
| `services/analysis_task_service.py` | Step 1–3 |
| `services/analysis_file_prepare_service.py` | Step 4 staging |
| `services/analysis_pipeline_service.py` | Step 4–7 编排 |
| `services/graphrag_model_client.py` | 8090 客户端 |
| `services/minio_download.py` | MinIO 下载 |
| `repositories/analysis_repository.py` | 任务/文件/events |
| `repositories/artifact_repository.py` | `model_artifacts` |
| `schemas/analysis.py` | 请求/响应模型 |

---

## 五、环境变量

### 7.1 base_Platform（18000）

| 变量 | 用途 |
|------|------|
| `FILE_INDEX_DATABASE_URL` | PostgreSQL |
| `MINIO_*` | Step 4 下载 |
| `GRAPHRAG_HTTP_BASE_URL` | 8090 基址 |
| `GRAPHRAG_POLL_INTERVAL_S` | 轮询间隔（`.env` 建议 5） |
| `GRAPHRAG_POLL_TIMEOUT_S` | 超时（默认 3600） |

### 7.2 graphrag-model-service（8090）

| 变量 | 用途 |
|------|------|
| `GRAPHRAG_CLI` | `graphragltt_env/bin/graphrag` |
| `GRAPHRAG_SETTINGS_TEMPLATE` | `qwen_graphrag_demo/settings.yaml` |
| `GRAPHRAG_PROMPTS_DIR` | `qwen_graphrag_demo/prompts` |

8090 进程还需 `source qwen_graphrag_demo/.env`（`LOCAL_CHAT_API_BASE` → `:8001`）。

启动示例见 [`../scripts/start_graphrag_8090.sh`](../scripts/start_graphrag_8090.sh) 与 [`../graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md`](../graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md)。

---

## 六、响应示例

### `POST .../run-phase1` 成功

```json
{
  "task_id": "1b8dd1f5-1325-40df-a36c-5d1b5577f7a8",
  "phase": "phase1",
  "status": "completed",
  "model_task_id": "582a9ce2091246b4b1cdc664ef960cc7",
  "manifest_path": ".../graphrag_out/artifact_manifest.json",
  "graphrag_service_task_root": ".../graphrag_runs/582a9ce2..."
}
```

---

## 七、环境验收（阶段 A）

| 步骤 | 检查项 |
|------|--------|
| A1 | PostgreSQL `ltt-craft-pg` @ :5434 |
| A2 | vLLM 8001/8002 HTTP 200 |
| A3 | 8090 `GET /api/health` |
| A4 | 18000 `/docs` + analysis 路由 |
| A5–A10 | workspace init、上传、建任务、stage、run-phase1、model_artifacts |

完整命令见 [`PHASE1_ACCEPTANCE_TEST_ZH.md`](PHASE1_ACCEPTANCE_TEST_ZH.md)。

---

## 八、事件类型

| event_type | 时机 |
|------------|------|
| `task_created` | Step 1–3 |
| `files_staged` | Step 4 |
| `graphrag_started` | 提交 8090 |
| `phase1_completed` | 成功 |
| `phase1_failed` | 失败 |

---

## 九、限制

| 限制 | 说明 |
|------|------|
| 8090 须能读平台 `inputs/` 路径 | 同机或共享盘 |
| `run-phase1` 同步阻塞 | 长任务占 HTTP 连接 |
| 前端未接 Phase1 | 需轮询 GET 任务 |

---

## 十、联调检查清单

- [ ] `projects` 已 init，`file_records` 有 MinIO 键
- [ ] 8090 + vLLM + MinIO 可达
- [ ] `run-phase1` → `status=completed`
- [ ] `graphrag_out/artifact_manifest.json` 存在
- [ ] `model_artifacts` 有行

---

## 十一、与 GraphRAG 引擎补丁

`run-phase1` 依赖 `graphrag index` 子进程。若卡在 `create_base_text_units`，见 [`PHASE1_STARTUP_GUIDE_ZH.md` 八点一](PHASE1_STARTUP_GUIDE_ZH.md#八一-graphrag-workflowprofiler--tracemalloc-挂死2026-05-27)。

补丁文件：`workspace/graphrag/packages/graphrag/graphrag/index/run/profiling.py`（去掉 tracemalloc）。

---

## 十二、8090 与平台边界

| 组件 | 写入位置 |
|------|----------|
| 8090 | `graphrag_runs/{id}/input/normalized/`、`output/`、`lancedb/` |
| 18000 | `inputs/`、`graphrag_out/`（manifest 副本）、DB 路径字段 |

平台 **不复制** normalized txt 到 `graphrag_input/`，仅在 DB 回填 8090 路径。

---

## 十三、tracemalloc 挂死（Step 5–7 相关）

详见启动指南 [八点一](PHASE1_STARTUP_GUIDE_ZH.md#八一-graphrag-workflowprofiler--tracemalloc-挂死2026-05-27)。重试前：

```bash
pkill -f 'graphrag index' || true
```

---

## 十四、验收记录

2026-05-28 成功样例：

| 项 | 值 |
|----|-----|
| `analysis_tasks.id` | `1b8dd1f5-1325-40df-a36c-5d1b5577f7a8` |
| `model_task_id` | `582a9ce2091246b4b1cdc664ef960cc7` |
| 实体/关系 | 5 / 4 |

完整过程见 [`PHASE1_ACCEPTANCE_TEST_ZH.md`](PHASE1_ACCEPTANCE_TEST_ZH.md)。

---

*与 `workspace/docs/PHASE1_BACKEND_PIPELINE_ZH.md` 同步；总册见 `PROJECT_FULL_GUIDE_ZH.md`。*
