# LTT 知识分析平台 — 项目总册

> **文档定位**：全项目架构、改造操作记录、接口索引与联调入口。  
> **重建说明**：本文于 2026-06-03 依据验收记录、现有代码与分册重建（非 git 历史还原）。

---

## 〇、文档体系

| 顺序 | 文档 | 内容 |
|------|------|------|
| 1 | **本文** `workspace/docs/PROJECT_FULL_GUIDE_ZH.md` | 总册 |
| 2 | [`base_Platform/docs/PROJECT_CHANGES_AND_OPERATIONS_ZH.md`](../base_Platform/docs/PROJECT_CHANGES_AND_OPERATIONS_ZH.md) | 改造与运维明细 |
| 3 | [`base_Platform/docs/PROJECT_STRUCTURE.md`](../base_Platform/docs/PROJECT_STRUCTURE.md) | 目录树 |
| 4 | [`base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md`](../base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md) | 启动与排错 |
| 5 | [`base_Platform/docs/PHASE1_GRAPHRAG_PIPELINE_ZH.md`](../base_Platform/docs/PHASE1_GRAPHRAG_PIPELINE_ZH.md) | 七步 API |
| 6 | [`base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md`](../base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md) | 验收手册 |
| 7 | [`base_Platform/docs/SCHEMA_GRAPHRAG_IR_WORKSPACE.md`](../base_Platform/docs/SCHEMA_GRAPHRAG_IR_WORKSPACE.md) | 9 张扩展表 |
| 8 | [`base_Platform/docs/WIKI_WORKSPACE_TEMPLATE.md`](../base_Platform/docs/WIKI_WORKSPACE_TEMPLATE.md) | Wiki 模板设计 |
| 9 | [`graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md`](../base_Platform/graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md) | 8090 HTTP |
| 10 | [`workspace/docs/GRAPHRAG_PIPELINE_FULL_ZH.md`](GRAPHRAG_PIPELINE_FULL_ZH.md) | GraphRAG 引擎 |
| 11 | [`workspace/scripts/README_STARTUP_ZH.md`](../scripts/README_STARTUP_ZH.md) | 一键启动 |

---

## 一、项目目标

将 **原始文档（MinIO）** 经 **GraphRAG 索引** 转为 **知识图谱底座**，再进入 CRR / IR / Wiki 沉淀（后三阶段规划中）。

```mermaid
flowchart LR
  UP[上传 file_records] --> T[analysis_task]
  T --> G[GraphRAG Phase1]
  G --> C[CRR Phase2]
  C --> I[IR Phase3]
  I --> W[Wiki Phase5]
```

**当前完成度**：Phase1 后端已实现并验收；CRR/IR/Wiki 自动写入未接；前端 Phase1 触发未完成。

---

## 二、改造操作总览

| # | 操作 | 状态 | 路径/说明 |
|---|------|------|-----------|
| 1 | 新建 PostgreSQL `ltt_craft` | ✅ | `docker-compose.ltt-pg.yml`，宿主机 **5434** |
| 2 | 扩展表 DDL（9 张） | ✅ | `database/schema_graphrag_ir_workspace.sql` |
| 3 | `.env` 运行时配置 | ✅ | `base_Platform/.env` |
| 4 | 后端分层 routers/services | ✅ | `backend/routers/` 等 |
| 5 | Wiki 模板 `base_wiki` | ✅ | `backend/resources/wiki_template/` |
| 6 | GraphRAG 8090 子服务 | ✅ | `graphrag-model-service/` |
| 7 | Phase1 七步流水线 | ✅ | `analysis_pipeline_service.py` |
| 8 | profiling tracemalloc 补丁 | ✅ | `graphrag/.../profiling.py` |
| 9 | 一键启动脚本 | ✅ | `workspace/scripts/start_all.sh` |
| 10 | 前端 Phase1 联调 | ⬜ | 待做 |
| 11 | CRR / IR / Wiki 写入 | ⬜ | 表已建，业务未接 |

---

## 三、代码与目录变更明细

### 3.1 新增后端模块（Phase1 + Workspace）

| 路径 | 职责 |
|------|------|
| `backend/routers/workspace.py` | init / tree / file |
| `backend/routers/analysis_tasks.py` | 任务 / stage / run-phase1 |
| `backend/routers/ir.py` | IR 占位 |
| `backend/services/analysis_*` | 阶段一编排 |
| `backend/services/workspace_*` | 路径 / 初始化 / 树 |
| `backend/services/wiki_writer.py` | Wiki 写页（Phase5 用） |
| `backend/repositories/*` | PostgreSQL 访问 |

### 3.2 `app.py` 改造

- 保留 legacy：上传、ASR、MinIO、认证
- 新增：`include_router(workspace|analysis_tasks|ir)`
- `load_env_file` 须在 routers import **之前**执行

### 3.3 运行时目录

```text
base_Platform/workspace/projects/{project_slug}/
└── runtime/tasks/{task_id}/inputs|graphrag_out|logs|...

graphrag-model-service/graphrag_runs/{model_task_id}/
└── input/normalized|output|logs|...
```

---

## 四、数据库

- **基础表**：`users`、`file_records` 等（见 `docs/DATABASE_SCHEMA.md`）
- **扩展 9 表**：`projects`、`analysis_tasks`、`analysis_task_files`、`model_artifacts`、`analysis_task_events`、`crr_snapshots`、`candidate_ir_items`、`ir_assets`、`wiki_pages`

详见 [`SCHEMA_GRAPHRAG_IR_WORKSPACE.md`](../base_Platform/docs/SCHEMA_GRAPHRAG_IR_WORKSPACE.md)。

---

## 五、Wiki 磁盘约定

- **模板**：`backend/resources/wiki_template/base_wiki/`（只读金样）
- **实例**：`workspace/projects/{project_slug}/`（`.gitignore` 忽略）
- **设计**：[`WIKI_WORKSPACE_TEMPLATE.md`](../base_Platform/docs/WIKI_WORKSPACE_TEMPLATE.md)

---

## 六、主流程完成度（①～⑨）

| 流程 | 状态 |
|------|------|
| ① 项目 + workspace init | ✅ 后端 |
| ② 上传 → file_records | ✅ legacy |
| ③ 创建 analysis_task | ✅ |
| ④ Phase1 GraphRAG | ✅ 已验收 |
| ⑤ CRR 组装 | ⬜ |
| ⑥ 候选 IR | ⬜ |
| ⑦ 正式 IR 入库 | ⬜ |
| ⑧ Wiki 页面沉淀 | ⬜ |
| ⑨ 前端全流程 | ⬜ |

---

## 七、HTTP 接口全集

### 7.1 Legacy（`app.py`）

上传、ASR、MinIO 树、认证等 — 见 [`FILE_UPLOAD_AND_PROCESSING_FLOW_ZH.md`](../base_Platform/docs/FILE_UPLOAD_AND_PROCESSING_FLOW_ZH.md)。

### 7.2 Workspace

| 方法 | 路径 |
|------|------|
| POST | `/api/workspace/init` |
| GET | `/api/workspace/tree?project_code=` |
| GET | `/api/workspace/file?project_code=&path=wiki/...` |

### 7.3 Analysis（Phase1）

| 方法 | 路径 |
|------|------|
| POST | `/api/analysis/tasks` |
| GET | `/api/analysis/tasks?project_id=` |
| GET | `/api/analysis/tasks/{id}` |
| GET | `/api/analysis/tasks/{id}/files` |
| POST | `/api/analysis/tasks/{id}/stage` |
| POST | `/api/analysis/tasks/{id}/run-phase1` |
| GET | `/api/analysis/graphrag/health` |

### 7.4 8090（GraphRAG 服务）

| 方法 | 路径 |
|------|------|
| GET | `/api/health` |
| POST | `/api/graphrag/index-tasks` |
| GET | `/api/graphrag/index-tasks/{id}` |
| GET | `/api/graphrag/index-tasks/{id}/artifacts` |
| GET | `/api/graphrag/index-tasks/{id}/logs` |

---

## 八、graphrag-model-service 与平台

- 8090 **不**直连 MinIO；读平台 staging 后的 `local_path`
- 平台通过 `GraphragModelClient` 轮询至完成
- 契约：[`GRAPHRAG_MODEL_SERVICE_ZH.md`](../base_Platform/graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md)

---

## 九、典型联调步骤

```bash
export BP=/mnt/dockerContainerSave/memory/ltt/workspace/base_Platform
cd "$BP"
docker compose -f docker-compose.ltt-pg.yml up -d
./scripts/start_graphrag_8090.sh          # 终端 1
source basePlatformltt_env/bin/activate
python -m uvicorn backend.app:app --host 127.0.0.1 --port 18000   # 终端 2
# 登录 → workspace/init → 上传 → POST tasks → run-phase1
```

完整命令：[`PHASE1_ACCEPTANCE_TEST_ZH.md`](../base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md)。

---

## 十、启动顺序与维护

1. PostgreSQL → vLLM 8001/8002 → 8090 → 18000 → 前端  
2. 一键：`workspace/scripts/start_all.sh`  
3. 修改 `.env` 后重启 18000

### 已知问题与本地补丁：WorkflowProfiler / tracemalloc

GraphRAG 索引第二步可能挂死；已 patch `profiling.py`。详见 [`PHASE1_STARTUP_GUIDE_ZH.md` 八点一](../base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md#八一-graphrag-workflowprofiler--tracemalloc-挂死2026-05-27)。

### 维护 checklist

- [x] Phase1 后端七步
- [x] 8090 HTTP 封装
- [x] tracemalloc 补丁
- [x] 2026-05-28 验收记录
- [ ] git 提交 docs + backend
- [ ] 前端 Phase1
- [ ] CRR / IR

---

*总册版本：2026-06-03*
