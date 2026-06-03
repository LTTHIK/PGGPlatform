# 阶段一验收测试记录与手动操作手册

> **用途**：记录 2026-05-27～05-28 阶段一（GraphRAG 索引）端到端测试的**过程、结果、产物路径**，并提供可复现的**逐步命令**。  
> **关联**：[`PHASE1_STARTUP_GUIDE_ZH.md`](PHASE1_STARTUP_GUIDE_ZH.md)（启动顺序与排错）、[`PHASE1_GRAPHRAG_PIPELINE_ZH.md`](PHASE1_GRAPHRAG_PIPELINE_ZH.md)（七步 API 专册）、[`workspace/docs/PROJECT_FULL_GUIDE_ZH.md`](../../docs/PROJECT_FULL_GUIDE_ZH.md)（总册）。

**路径约定**（下文命令可直接复制）：

```bash
export LTT_ROOT=/mnt/dockerContainerSave/memory/ltt
export BP="$LTT_ROOT/workspace/base_Platform"
export GR="$LTT_ROOT/workspace/graphrag"
export DEMO="$GR/qwen_graphrag_demo"
export VLLM="$LTT_ROOT/../vllm-big-model"   # 即 /mnt/dockerContainerSave/vllm-big-model
```

---

## 一、测试结论（摘要）

| 项 | 结果 |
|----|------|
| 验收任务 `analysis_tasks.id` | `1b8dd1f5-1325-40df-a36c-5d1b5577f7a8` |
| 8090 `model_task_id` | `582a9ce2091246b4b1cdc664ef960cc7` |
| 最终状态 | `completed`，`progress=100`，`current_step=phase1_done` |
| GraphRAG CLI 退出码 | `0`（`artifact_manifest.json` → `validation_ok: true`） |
| 索引耗时（8090 任务内） | 约 **25s**（`output/stats.json` → `total_runtime`） |
| 输入 | 1 个 txt（阶段 A 验收文案，145 字节） |
| 图谱规模（本次） | 实体 **5**、关系 **4**、text_units **1**、社区 **1** |

**前置修复（本次能通过的关键）**：

1. `workspace/graphrag/packages/graphrag/graphrag/index/run/profiling.py` 去掉 `tracemalloc`（否则第二步 `create_base_text_units` 永久挂死）。  
2. 8090 使用 `scripts/start_graphrag_8090.sh` 加载 `qwen_graphrag_demo/.env` 与 `settings.yaml`。  
3. vLLM **8001/8002** 已运行；MinIO staging 配置正确。

---

## 二、测试时间线与失败记录

同一分析任务 `1b8dd1f5-…` 曾多次重试，事件顺序见库表 `analysis_task_events`：

| 时间 (UTC) | 事件 | 原因 | 8090 目录 / 日志 |
|------------|------|------|------------------|
| 05-27 07:19 | `phase1_failed` | `LLM_MODEL` 环境变量缺失，CLI 秒退 code=1 | `graphrag_runs/83d32739…/`（仅 `service_index.stderr.log`） |
| 05-27 09:54～10:54 | `phase1_failed` | `tracemalloc` 挂死 → 轮询 **3600s** 超时 | `graphrag_runs/886ee009…/logs/indexing-engine.log` 停在 `create_base_text_units` |
| **05-28 01:57～01:58** | **`phase1_completed`** | profiling 修复 + 环境就绪 | **`graphrag_runs/582a9ce2…/`**（完整产物） |

**勿混淆的日志路径**：

| 路径 | 日期 | 说明 |
|------|------|------|
| `qwen_graphrag_demo/logs/indexing-engine.log` | 05-11 | demo 目录**手跑**索引，非平台任务 |
| `graphrag_runs/2fd48ba9…/logs/` | 05-09 | 旧挂死任务，**不是**本次成功测试 |
| **`graphrag_runs/582a9ce2…/logs/indexing-engine.log`** | **05-28** | **本次成功测试的权威日志** |

---

## 三、调用链与目录（三个「根」）

```text
┌─────────────────────────────────────────────────────────────────┐
│ ① graphrag/（引擎）                                              │
│    graphragltt_env/bin/graphrag  ← packages/graphrag 源码       │
│    profiling.py 补丁在此生效                                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│ ② qwen_graphrag_demo/（配置模板，8090 启动时指定）                 │
│    settings.yaml、prompts/、.env（LOCAL_* → :8001/:8002）         │
└────────────────────────────┬────────────────────────────────────┘
                             │ 每次 index-tasks 复制到
┌────────────────────────────▼────────────────────────────────────┐
│ ③ graphrag-model-service/graphrag_runs/{model_task_id}/（本次运行根）│
│    input/normalized/*.txt → graphrag index --root 这里           │
│    output/*.parquet、lancedb/、logs/indexing-engine.log          │
└────────────────────────────┬────────────────────────────────────┘
                             │ run-phase1 完成后写副本/指针
┌────────────────────────────▼────────────────────────────────────┐
│ ④ base_Platform/workspace/projects/pcg/runtime/tasks/{task_id}/ │
│    inputs/、graphrag_out/artifact_manifest.json、logs/           │
└─────────────────────────────────────────────────────────────────┘
```

**平台 Phase1 不会**在 `qwen_graphrag_demo/` 根目录下跑索引；只看 demo 的 log 会误判日期与结果。

---

## 四、端到端过程说明（自动编排）

### 4.1 服务依赖

```text
PostgreSQL :5434  →  analysis_tasks / model_artifacts / events
MinIO          →  file_records 对象存储
vLLM :8001     →  qwen3-vl（GraphRAG 抽图 LLM）
vLLM :8002     →  qwen3-embedding（向量）
8090           →  graphrag index 子进程
18000          →  staging + run-phase1 编排
```

### 4.2 七步在本次测试中的实际执行

| 步骤 | 动作 | 本次如何触发 | 产物 |
|------|------|--------------|------|
| 1–3 | 建任务、绑文件、建目录 | 此前 `POST /api/analysis/tasks` | `runtime/tasks/1b8dd1f5-…/` |
| 4 | MinIO → `inputs/` | `run-phase1` 内 staging（或事先 `stage`） | `inputs/1_20260527_070853_165aa3ae.txt` |
| 5 | 调 8090 | `GraphragModelClient.create_index_task` | 新建 `graphrag_runs/582a9ce2…/` |
| 5a | 8090 内转 txt | `prepare_normalized_inputs` | `…/input/normalized/20260527_070853_165aa3ae.txt` |
| 5b | 8090 内索引 | `graphrag index --root graphrag_runs/582a9ce2…` | `output/*.parquet`、`lancedb/` |
| 5c | 18000 轮询 | `poll_until_done` 直至 completed/failed | 阻塞 HTTP 最多 3600s |
| 6 | 写 `model_artifacts` | `upsert_from_manifest` | PG 表 + 平台 `graphrag_out/` 副本 |
| 7 | 更新任务 | `status=completed` | `phase1_completed` 事件 |

### 4.3 GraphRAG 索引子流程（582 任务，约 25s）

日志顺序（`582a9ce2…/logs/indexing-engine.log`，UTC）：

1. `load_input_documents` — 加载 1 行文档  
2. `create_base_text_units` — 分块（profiling 修复后 **0.47s** 完成）  
3. `create_final_documents`  
4. `extract_graph` — 调 **8001** 抽实体关系（约 **9.4s**）  
5. `finalize_graph` → `create_communities` → `create_final_text_units`  
6. `create_community_reports` — 再调 LLM  
7. `generate_text_embeddings` — 调 **8002** 写 LanceDB  

---

## 五、产物清单（本次成功运行）

### 5.1 8090 任务根（主副本，权威数据）

**目录**：`$BP/graphrag-model-service/graphrag_runs/582a9ce2091246b4b1cdc664ef960cc7/`

| 类别 | 路径 | 说明 |
|------|------|------|
| 清单 | `artifact_manifest.json` | `validation_ok: true`，列出 parquet / lancedb |
| 输入 | `input/normalized/20260527_070853_165aa3ae.txt` | UTF-8 验收文案 |
| 配置 | `settings.yaml`、`prompts/*.txt` | 从 demo 复制 |
| 日志 | `logs/indexing-engine.log` | GraphRAG 主日志（**05-28 01:57–01:58**） |
| 日志 | `logs/service_index.stdout.log`、`service_index.stderr.log` | CLI 标准输出/错误 |
| 统计 | `output/stats.json` | 各 workflow 耗时 |
| 表 | `output/documents.parquet` | 1 行 |
| 表 | `output/text_units.parquet` | 1 行 |
| 表 | `output/entities.parquet` | **5** 行 |
| 表 | `output/relationships.parquet` | **4** 行 |
| 表 | `output/communities.parquet` | 1 行 |
| 表 | `output/community_reports.parquet` | 1 行 |
| 图 | `output/graph.graphml` | GraphML 导出 |
| 向量库 | `output/lancedb/vector_index.lance/` | 嵌入索引 |

### 5.2 平台任务目录（副本与指针）

**目录**：`$BP/workspace/projects/pcg/runtime/tasks/1b8dd1f5-1325-40df-a36c-5d1b5577f7a8/`

| 路径 | 说明 |
|------|------|
| `inputs/1_20260527_070853_165aa3ae.txt` | staging 原始副本 |
| `graphrag_out/artifact_manifest.json` | 与 8090 manifest 同步的 JSON 副本 |
| `graphrag_out/graphrag_service_task_root.txt` | 一行：8090 `task_root` 绝对路径 |
| `logs/graphrag.stdout.log`、`graphrag.stderr.log` | 8090 子进程 stdout/stderr 拉回 |

### 5.3 PostgreSQL

| 表 | 本次关键行 |
|----|------------|
| `analysis_tasks` | `id=1b8dd1f5-…`，`model_task_id=582a9ce2…`，`status=completed` |
| `analysis_task_files` | `parse_status=normalized`，`graphrag_input_path` 指向 8090 normalized txt |
| `model_artifacts` | `status=completed`，`output_dir` 指向 8090 `output/` |
| `analysis_task_events` | 末条 `phase1_completed` @ 2026-05-28 01:58:04 UTC |

### 5.4 输入文本内容（验收用）

```text
阶段A验收测试文档。
本项目用于验证 GraphRAG 索引流水线。
需求：支持文件上传、分析任务与知识图谱构建。
```

---

## 六、手动操作手册（逐步命令）

以下假设 **4 个终端** + Docker PG；命令按顺序执行。每步附**说明**与**预期结果**。

### 阶段 0：环境检查（一次性）

**说明**：确认 GraphRAG 补丁、Python 环境、GPU 上无重复 vLLM 导致 OOM。

```bash
export LTT_ROOT=/mnt/dockerContainerSave/memory/ltt
export BP="$LTT_ROOT/workspace/base_Platform"
export GR="$LTT_ROOT/workspace/graphrag"
export DEMO="$GR/qwen_graphrag_demo"
export VLLM=/mnt/dockerContainerSave/vllm-big-model

# 0.1 确认 profiling 已去掉 tracemalloc（应无 import tracemalloc）
grep -n tracemalloc "$GR/packages/graphrag/graphrag/index/run/profiling.py" || echo "OK: no tracemalloc"

# 0.2 确认 graphrag CLI 加载的是本地 packages 源码
"$GR/graphragltt_env/bin/python" -c "import graphrag.index.run.profiling as p; print(p.__file__)"

# 0.3 查看 GPU（若 0–5 已被 VLLM 占满，不要重复 bash start_all.sh）
nvidia-smi
```

**预期**：profiling 路径在 `…/packages/graphrag/…`；若 vLLM 已在跑，显存 0–5 约 14GB/卡占用属正常。

---

### 阶段 A：启动基础服务

#### 步骤 A1 — PostgreSQL

**说明**：阶段一任务状态、产物元数据入库。

```bash
cd "$BP"
docker compose -f docker-compose.ltt-pg.yml up -d
docker exec ltt-craft-pg pg_isready -U craft -d ltt_craft
```

**预期**：`accepting connections`。

#### 步骤 A2 — vLLM（8001 Chat + 8002 Embedding）

**说明**：GraphRAG 通过 OpenAI 兼容 API 访问本地模型；**须先于 8090**。

```bash
cd "$VLLM"
# 若 nvidia-smi 显示 8001/8002 已在监听，可跳过本步
bash start_all.sh
```

**说明（常见失败）**：若报 `Free memory on device cuda:X … less than desired GPU memory utilization`，表示 GPU 已被旧 vLLM 占满，应：

```bash
pkill -f 'vllm serve' || true
sleep 3
nvidia-smi
bash start_all.sh
```

**验证**：

```bash
curl -s -o /dev/null -w "8001:%{http_code}\n" http://127.0.0.1:8001/v1/models
curl -s -o /dev/null -w "8002:%{http_code}\n" http://127.0.0.1:8002/v1/models
```

**预期**：均为 `200`。

#### 步骤 A3 — GraphRAG 索引服务 8090

**说明**：加载 `qwen_graphrag_demo/.env` 与 settings；**不要**裸起 uvicorn 以免缺 `LOCAL_*`。

```bash
cd "$BP"
./scripts/start_graphrag_8090.sh
# 保持终端运行；另开终端做后续步骤
```

**验证**（新终端）：

```bash
curl -s http://127.0.0.1:8090/api/health | python3 -m json.tool
```

**预期**：`status: ok`，`settings_template` 指向 `…/qwen_graphrag_demo/settings.yaml`，`graphrag_cli` 指向 `graphragltt_env/bin/graphrag`。

#### 步骤 A4 — 业务平台 18000

**说明**：`.env` 含 `GRAPHRAG_HTTP_BASE_URL`；修改 `.env` 后须重启本进程。

```bash
cd "$BP"
# 确认 .env
grep GRAPHRAG_HTTP_BASE_URL "$BP/.env"
basePlatformltt_env/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 18000
```

**验证**：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18000/docs
```

**预期**：`200`。

---

### 阶段 B：准备数据与登录

#### 步骤 B1 — 登录拿 JWT

**说明**：后续分析 API 需 `Authorization: Bearer`。

```bash
export TOKEN=$(curl -s -X POST http://127.0.0.1:18000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"wyt","password":"123456"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "TOKEN_LEN=${#TOKEN}"
```

**预期**：`TOKEN_LEN` 为数百（非 0）。账号须已在库中（见项目联调文档）。

#### 步骤 B2 — 确认 MinIO 与 file_records（若已测过可跳过）

**说明**：staging 从 MinIO 拉对象；`file_records.id=1` 为本次任务绑定文件。

```bash
docker exec ltt-craft-pg psql -U craft -d ltt_craft -c \
  "SELECT id, bucket_name, object_key, filename FROM file_records ORDER BY id DESC LIMIT 3;"
```

**预期**：至少一条记录，`bucket_name` / `object_key` 非空。

---

### 阶段 C：创建分析任务（Step 1–3）

#### 步骤 C1 — 创建任务

**说明**：写入 `analysis_tasks`、`analysis_task_files`，创建 `runtime/tasks/{uuid}/` 子目录。

```bash
curl -s -X POST http://127.0.0.1:18000/api/analysis/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "project_code": "pcg",
    "skill_id": "requirement_analysis",
    "mode": "auto",
    "file_record_ids": [1]
  }' | python3 -m json.tool
```

**预期**：返回 `task_id`（UUID）。记下：

```bash
export TASK_ID="<上一步返回的 task_id>"
```

**说明**：若复用本次已成功的任务，可：

```bash
export TASK_ID=1b8dd1f5-1325-40df-a36c-5d1b5577f7a8
```

---

### 阶段 D：执行阶段一（Step 4–7）

#### 步骤 D1 — 一键 run-phase1

**说明**：

- 默认 `skip_staging=false`：先从 MinIO 下载到 `inputs/`。  
- 内部：POST 8090 → 转 txt → `graphrag index` → 轮询（最长 3600s）→ 写库。  
- **HTTP 会阻塞**直到结束，小文档约 **30s～2min**。

```bash
cd "$BP"
echo "Starting run-phase1 at $(date -Iseconds) ..."
curl -s -w "\nHTTP_CODE:%{http_code}\n" --max-time 3600 \
  -X POST "http://127.0.0.1:18000/api/analysis/tasks/${TASK_ID}/run-phase1?skip_staging=false" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -o /tmp/run_phase1_result.json
echo "Finished at $(date -Iseconds)"
python3 -m json.tool /tmp/run_phase1_result.json
```

**若文件已 staged**，可跳过 Step 4：

```bash
curl -s -w "\nHTTP_CODE:%{http_code}\n" --max-time 3600 \
  -X POST "http://127.0.0.1:18000/api/analysis/tasks/${TASK_ID}/run-phase1?skip_staging=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' | python3 -m json.tool
```

**预期**：JSON 中 `status: completed` 或 `phase1` 成功；`HTTP_CODE:200`。

#### 步骤 D2 — 查询任务状态

```bash
curl -s "http://127.0.0.1:18000/api/analysis/tasks/${TASK_ID}" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**预期**：`status: completed`，`progress: 100`，`current_step: phase1_done`，`model_task_id` 非空。

#### 步骤 D3 — 查 8090 任务与健康

```bash
export MODEL_TASK_ID=$(curl -s "http://127.0.0.1:18000/api/analysis/tasks/${TASK_ID}" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_task_id',''))")
echo "MODEL_TASK_ID=$MODEL_TASK_ID"

curl -s "http://127.0.0.1:8090/api/graphrag/index-tasks/${MODEL_TASK_ID}" | python3 -m json.tool
```

**预期**：`status: completed`，`returncode: 0`（或已完成后的终态）。

---

### 阶段 E：验收产物与日志

#### 步骤 E1 — 平台目录

```bash
ls -la "$BP/workspace/projects/pcg/runtime/tasks/${TASK_ID}/"
ls -la "$BP/workspace/projects/pcg/runtime/tasks/${TASK_ID}/graphrag_out/"
cat "$BP/workspace/projects/pcg/runtime/tasks/${TASK_ID}/graphrag_out/graphrag_service_task_root.txt"
```

**预期**：存在 `artifact_manifest.json`、`graphrag_service_task_root.txt` 指向 `graphrag_runs/${MODEL_TASK_ID}`。

#### 步骤 E2 — 8090 输出与日志

```bash
RUN_ROOT="$BP/graphrag-model-service/graphrag_runs/${MODEL_TASK_ID}"
ls -la "$RUN_ROOT/output/"
tail -20 "$RUN_ROOT/logs/indexing-engine.log"
python3 -m json.tool "$RUN_ROOT/artifact_manifest.json"
```

**预期**：日志末行含 `generate_text_embeddings` completed / pipeline complete；manifest `validation_ok: true`。

#### 步骤 E3 — 数据库

```bash
docker exec ltt-craft-pg psql -U craft -d ltt_craft -c \
  "SELECT event_type, message, created_at FROM analysis_task_events WHERE task_id='${TASK_ID}' ORDER BY created_at;"
docker exec ltt-craft-pg psql -U craft -d ltt_craft -c \
  "SELECT status, entity_count, relationship_count, output_dir FROM model_artifacts WHERE task_id='${TASK_ID}';"
```

**预期**：末条 `phase1_completed`；`model_artifacts.status=completed`。

#### 步骤 E4 — 可选：查看 parquet 行数

```bash
"$GR/graphragltt_env/bin/python" -c "
import pandas as pd
from pathlib import Path
out = Path('$RUN_ROOT/output')
for n in ['documents','entities','relationships','text_units','communities','community_reports']:
    p = out / f'{n}.parquet'
    print(n, len(pd.read_parquet(p)) if p.exists() else 'MISSING')
"
```

---

### 阶段 F：仅 8090 直连测试（不经过 18000）

**说明**：排查平台与 8090 分层问题时可用。

```bash
# 准备本地源文件路径（已 staged 的文件）
export LOCAL_FILE="$BP/workspace/projects/pcg/runtime/tasks/${TASK_ID}/inputs/1_20260527_070853_165aa3ae.txt"

curl -s -X POST http://127.0.0.1:8090/api/graphrag/index-tasks \
  -H 'Content-Type: application/json' \
  -d "{\"source_files\":[{\"local_path\":\"${LOCAL_FILE}\",\"logical_name\":\"20260527_070853_165aa3ae.txt\"}]}" \
  | python3 -m json.tool

# 记下 model_task_id 后轮询
export MODEL_TASK_ID="<返回的 id>"
watch -n 3 "curl -s http://127.0.0.1:8090/api/graphrag/index-tasks/${MODEL_TASK_ID} | python3 -m json.tool"
```

---

### 阶段 G：仅 GraphRAG CLI 手跑（demo 目录，非平台任务）

**说明**：开发调试引擎用；日志写在 `qwen_graphrag_demo/logs/`，**不要**与 `graphrag_runs/` 混淆。

```bash
cd "$DEMO"
set -a && source .env && set +a
# 确保 input/normalized/*.txt 存在
"$GR/graphragltt_env/bin/graphrag" index --root . --method standard --verbose
```

---

## 七、清理与重试

```bash
# 结束卡死的 graphrag 子进程（挂死排查后建议执行）
pkill -f 'graphrag index' || true

# 仅当需要完整重启 vLLM
# pkill -f 'vllm serve' || true
```

**说明**：`graphrag_runs/` 下旧任务目录**不会自动删除**；新跑一次 `run-phase1` 会生成新 `model_task_id` 目录。

---

## 八、相关文档索引

| 文档 | 内容 |
|------|------|
| [`PHASE1_STARTUP_GUIDE_ZH.md`](PHASE1_STARTUP_GUIDE_ZH.md) | 四服务启动、验收问题表、tracemalloc 八点一 |
| [`PHASE1_GRAPHRAG_PIPELINE_ZH.md`](PHASE1_GRAPHRAG_PIPELINE_ZH.md) | 七步 API、字段、环境变量 |
| [`../graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md`](../graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md) | 8090 HTTP 契约 |
| [`../../docs/PROJECT_FULL_GUIDE_ZH.md`](../../docs/PROJECT_FULL_GUIDE_ZH.md) | 项目总册 |

---

*本文随仓库验收结果更新；成功样例：`model_task_id=582a9ce2091246b4b1cdc664ef960cc7`，`task_id=1b8dd1f5-1325-40df-a36c-5d1b5577f7a8`（2026-05-28 UTC）。*
