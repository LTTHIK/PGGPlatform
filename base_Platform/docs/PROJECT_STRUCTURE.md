# base_Platform 项目结构

> **总册**：[`workspace/docs/PROJECT_FULL_GUIDE_ZH.md`](../../docs/PROJECT_FULL_GUIDE_ZH.md)

---

## 一、仓库根布局

```text
workspace/
├── base_Platform/              # 本平台主工程
├── graphrag/                   # GraphRAG 引擎 + qwen_graphrag_demo
├── scripts/                    # 全栈 start_all.sh / stop_all.sh
└── docs/                       # 跨工程文档（总册、引擎说明）

base_Platform/
├── backend/                    # FastAPI 后端
├── frontend/                   # Vite + React
├── graphrag-model-service/     # GraphRAG HTTP :8090
├── database/                   # SQL 迁移脚本
├── docs/                       # 平台专册
├── scripts/                    # 8090 / settings 同步
├── workspace/projects/         # 运行时 Wiki（gitignore）
├── .env                        # 18000 环境变量
└── docker-compose.ltt-pg.yml   # PostgreSQL only
```

---

## 二、backend 目录

```text
backend/
├── app.py                      # 入口：legacy 路由 + include_router
├── auth_users.py
├── transcriber.py
├── routers/
│   ├── workspace.py            # /api/workspace/*
│   ├── analysis_tasks.py       # /api/analysis/*
│   └── ir.py                   # /api/ir/* stub
├── services/
│   ├── analysis_task_service.py
│   ├── analysis_file_prepare_service.py
│   ├── analysis_pipeline_service.py
│   ├── graphrag_model_client.py
│   ├── minio_download.py
│   ├── workspace_path_service.py
│   ├── workspace_initializer.py
│   ├── workspace_tree_service.py
│   └── wiki_writer.py
├── repositories/
│   ├── analysis_repository.py
│   ├── artifact_repository.py
│   └── workspace_repository.py
├── schemas/
│   ├── analysis.py
│   └── workspace.py
└── resources/
    └── wiki_template/base_wiki/
```

---

## 三、graphrag-model-service

```text
graphrag-model-service/
├── app/
│   ├── main.py                 # FastAPI 8090
│   ├── config.py
│   └── services/               # input_preparer, graphrag_runner, …
├── graphrag_runs/              # 每次 index 运行根
├── templates/                  # settings 同步目标
└── docs/
    └── GRAPHRAG_MODEL_SERVICE_ZH.md
```

---

## 四、graphrag 引擎

```text
graphrag/
├── packages/graphrag/          # 源码（含 profiling.py 补丁）
├── graphragltt_env/            # Python venv
└── qwen_graphrag_demo/         # settings.yaml, prompts/, .env
```

---

## 五、运行时数据路径

| 用途 | 路径 |
|------|------|
| 项目 Wiki | `base_Platform/workspace/projects/{slug}/` |
| 分析任务 | `.../runtime/tasks/{task_id}/` |
| 8090 索引 | `graphrag-model-service/graphrag_runs/{model_task_id}/` |
| 上传录音等 | `recordings/`、`paraformer_model/` |

---

## 六、数据库脚本

| 文件 | 说明 |
|------|------|
| `database/schema_all_tables.sql` | 基础表 |
| `database/schema_graphrag_ir_workspace.sql` | 9 张扩展表 |
| `database/schema_recording_index.sql` | 录音索引 |

---

## 七、文档索引

| 文档 | 路径 |
|------|------|
| 总册 | `workspace/docs/PROJECT_FULL_GUIDE_ZH.md` |
| 改造记录 | `docs/PROJECT_CHANGES_AND_OPERATIONS_ZH.md` |
| 启动 | `docs/PHASE1_STARTUP_GUIDE_ZH.md` |
| Phase1 API | `docs/PHASE1_GRAPHRAG_PIPELINE_ZH.md` |
| 验收 | `docs/PHASE1_ACCEPTANCE_TEST_ZH.md` |
| 表结构 | `docs/SCHEMA_GRAPHRAG_IR_WORKSPACE.md` |
| Wiki | `docs/WIKI_WORKSPACE_TEMPLATE.md` |
| 8090 | `graphrag-model-service/docs/GRAPHRAG_MODEL_SERVICE_ZH.md` |
| 上传链路 | `docs/FILE_UPLOAD_AND_PROCESSING_FLOW_ZH.md` |
| Wiki 资源 | `backend/resources/WIKI_RESOURCES_ANALYSIS_ZH.md` |

---

## 八、端口一览

| 端口 | 服务 |
|------|------|
| 5434 | PostgreSQL |
| 8001 | vLLM Chat |
| 8002 | vLLM Embedding |
| 8003 | vLLM Reranker（可选） |
| 8090 | GraphRAG HTTP |
| 18000 | base_Platform API |
| 5173 | 前端 Vite |
| 9000 | MinIO（远程） |

---

## 九、启动脚本

| 脚本 | 说明 |
|------|------|
| [`../../scripts/start_all.sh`](../../scripts/start_all.sh) | workspace 全栈 |
| [`../scripts/start_graphrag_8090.sh`](../scripts/start_graphrag_8090.sh) | 8090 |
| [`../scripts/sync_graphrag_settings.sh`](../scripts/sync_graphrag_settings.sh) | settings 同步 |

详见 [`PHASE1_STARTUP_GUIDE_ZH.md`](PHASE1_STARTUP_GUIDE_ZH.md)。

---

*版本：2026-06-03*
