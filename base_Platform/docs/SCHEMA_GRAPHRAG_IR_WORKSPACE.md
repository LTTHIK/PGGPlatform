# GraphRAG / IR / Wiki 扩展表说明

> **DDL 源文件**：[`database/schema_graphrag_ir_workspace.sql`](../database/schema_graphrag_ir_workspace.sql)  
> **基础表**：[`workspace/docs/DATABASE_SCHEMA.md`](../../docs/DATABASE_SCHEMA.md)（`users`、`file_records` 等）

在 `ltt_craft` 库、基础表就绪后执行扩展 SQL。依赖 `pgcrypto`（`gen_random_uuid()`）。

---

## 一、表清单

| # | 表名 | Phase1 | 说明 |
|---|------|--------|------|
| 1 | `projects` | ✅ | 项目元数据、`workspace_root` |
| 2 | `analysis_tasks` | ✅ | 分析任务主表 |
| 3 | `analysis_task_files` | ✅ | 任务绑定的 file_records |
| 4 | `analysis_task_events` | ✅ | 任务事件流 |
| 5 | `model_artifacts` | ✅ | GraphRAG manifest 与路径 |
| 6 | `crr_snapshots` | 预留 | CRR JSON 快照 |
| 7 | `candidate_ir_items` | 预留 | 候选 IR |
| 8 | `ir_assets` | 预留 | 正式 IR 资产 |
| 9 | `wiki_pages` | 预留 | Wiki 页元数据（与磁盘 md 可双写） |

---

## 二、Phase1 核心表

### 2.1 `projects`

| 列 | 说明 |
|----|------|
| `project_code` | 业务编码，如 `PCG` |
| `project_slug` | 磁盘目录名，如 `pcg` |
| `workspace_root` | 绝对路径，`init` 后写入 |

### 2.2 `analysis_tasks`

| 列 | Phase1 典型值 |
|----|---------------|
| `status` | `pending` → `running` → `completed` / `failed` |
| `progress` | 0 → 20 → 40 → 100 |
| `current_step` | `files_staged` / `graphrag_polling` / `phase1_done` |
| `model_task_id` | 8090 返回的 hex id |
| `workspace_task_path` | `runtime/tasks/{uuid}/` |

### 2.3 `analysis_task_files`

| 列 | 说明 |
|----|------|
| `local_path` | staging 后 inputs 路径 |
| `graphrag_input_path` | 8090 normalized txt（完成后回填） |
| `parsed_text_path` | 常与 graphrag_input 相同 |
| `parse_status` | `pending` → `staged` → `normalized` |
| `minio_bucket` / `minio_object_key` | 来自 file_records |

### 2.4 `model_artifacts`

| 列 | 说明 |
|----|------|
| `manifest_json` | 8090 `artifact_manifest.json` 内容 |
| `manifest_path` | 平台侧副本路径 |
| `entities_path` / `relationships_path` / … | parquet 绝对路径 |
| `entity_count` / `relationship_count` / … | 行数统计 |
| `stdout_path` / `stderr_path` | 日志副本 |

### 2.5 `analysis_task_events`

| 列 | 说明 |
|----|------|
| `event_type` | `task_created`、`files_staged`、`phase1_completed` 等 |
| `payload_json` | 结构化上下文 |

---

## 三、预留表（Phase2+）

### `crr_snapshots`

存储 CRR 组装结果 JSON，关联 `task_id`。

### `candidate_ir_items`

候选需求/规则项，含 `content_json`、`confidence`、`status`。

### `ir_assets`

正式 IR 入库，版本与审核字段。

### `wiki_pages`

可选：Wiki 页索引（section、path、title），与 `workspace/projects/.../wiki/` 文件系统配合。

---

## 四、关系示意

```text
projects 1 ──* analysis_tasks 1 ──* analysis_task_files
                      │
                      ├──* analysis_task_events
                      ├──0..1 model_artifacts
                      ├──* crr_snapshots (预留)
                      ├──* candidate_ir_items (预留)
                      └──* wiki_pages (预留)

file_records * ──* analysis_task_files (via file_record_id)
users * ──* analysis_tasks (created_by)
```

---

## 五、迁移命令

```bash
export FILE_INDEX_DATABASE_URL=postgresql://craft:<password>@127.0.0.1:5434/ltt_craft
psql "$FILE_INDEX_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f /mnt/dockerContainerSave/memory/ltt/workspace/base_Platform/database/schema_graphrag_ir_workspace.sql
```

---

## 六、与代码对应

| 表 | Repository / Service |
|----|---------------------|
| `projects` | `workspace_repository.py` |
| `analysis_*` | `analysis_repository.py` |
| `model_artifacts` | `artifact_repository.py` |

---

*版本：2026-06-03；结构以 live DB 导出 SQL 为准。*
