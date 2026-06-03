# 数据库表结构说明（PostgreSQL）

> **数据来源**：仓库内 SQL 与后端初始化代码（`database/schema_all_tables.sql`、`database/schema_recording_index.sql`、`database/migrate_file_records_to_sessions.sql`、`backend/app.py` 中 `FileRecordStore`、`backend/auth_users.py` 中 `UserStore`）。  
> **说明**：本文描述的是**版本控制中的目标结构**；若线上库曾仅用应用自举建表而未执行完整迁移，请以实际 `psql \d+` 为准。本文**未**直接连接你环境中的数据库实例做实时探测。

---

## 1. 数据库与连接

| 项 | 说明 |
|----|------|
| 数据库产品 | **PostgreSQL**（`docker-compose.app.yml` 示例为 `postgres:16-alpine`，库名 `craft`） |
| 应用连接串 | 环境变量 **`FILE_INDEX_DATABASE_URL`**（例如 `postgresql://user:pass@host:5432/dbname`） |
| 扩展 | **`pgcrypto`**（用于 `gen_random_uuid()` 等） |

---

## 2. 自定义枚举类型（ENUM）

这些类型在 `schema_all_tables.sql` / `schema_recording_index.sql` 中定义，供会话相关表使用。

### 2.1 `recording_source`

| 枚举值 | 含义（工程语义） |
|--------|------------------|
| `live` | 实时流式录音场景（默认） |
| `offline_import` | 离线导入等非实时来源 |

### 2.2 `session_status`

| 枚举值 | 含义（工程语义） |
|--------|------------------|
| `recording` | 正在录音 |
| `stopped` | 已停止 |
| `uploaded` | 已上传对象存储 |
| `partial_failed` | 部分失败 |
| `completed` | 已完成 |

### 2.3 `artifact_type`

| 枚举值 | 含义（工程语义） |
|--------|------------------|
| `recording_wav` | 会话对应的 WAV 录音对象 |
| `raw_transcript` | 原始转写文本 |
| `formal_text` | 书面化/润色后文本 |
| `meeting_minutes` | 会议纪要文本 |

---

## 3. 表一览

| 表名 | 主要用途 |
|------|----------|
| `file_records` | **MinIO 对象索引**：记录上传到对象存储的文件元数据，兼容旧逻辑；可与 `session_id` 关联流式会话 |
| `recording_sessions` | **录音会话主表**：一次录音/一条业务会话一条记录，带状态与桶信息 |
| `session_artifacts` | **会话产物明细**：某会话下四类产物（录音、转写、书面稿、纪要）在 MinIO 中的具体对象 |
| `session_events` | **会话事件审计**：按事件类型追加 JSON 载荷，便于排查与迁移标记 |
| `users` | **平台用户**：登录名、密码哈希、角色、启用状态 |

---

## 4. 各表字段与说明

### 4.1 `file_records`

**用途**：为后端 `FileRecordStore`（`backend/app.py`）提供持久化索引。每次向 MinIO 写入并登记时，会 **UPSERT** 到本表；`GET /api/files/records` 从此表查询。设计上与「流式 ASR 的 session_id」可关联，也允许 `session_id` 为空（例如仅文本上传）。

| 字段名 | 类型 | 约束 / 默认值 | 说明 |
|--------|------|----------------|------|
| `id` | `BIGSERIAL` | `PRIMARY KEY` | 自增主键 |
| `session_id` | `TEXT` | 可空 | 流式会话标识（WebSocket 侧 session）；无会话时可为 `NULL` |
| `bucket_name` | `TEXT` | `NOT NULL` | MinIO（S3）桶名 |
| `object_key` | `TEXT` | `NOT NULL` | 对象键（路径） |
| `kind` | `TEXT` | `NOT NULL` | 业务类型字符串；代码中常见值：`recording_wav`、`raw_transcript`、`formal_text`、`meeting_minutes`（与 `artifact_type` 命名对齐，但本列为 **TEXT**） |
| `content_type` | `TEXT` | 可空 | HTTP/MIME 内容类型，如 `audio/wav`、`text/plain; charset=utf-8` |
| `byte_length` | `BIGINT` | 可空 | 对象字节大小 |
| `local_path` | `TEXT` | 可空 | 本机临时路径（例如录音落盘后再上传）；非必须 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 首次插入时间 |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 更新时间；由触发器在 `UPDATE` 时刷新 |

**索引**：`session_id`、`kind`、`created_at DESC`。

**约束**：`UNIQUE (bucket_name, object_key)` — 同一对象全局只保留一条索引记录，冲突时走更新逻辑。

**触发器**：`trg_file_records_updated` → 调用 `set_updated_at()`，在更新行前将 `updated_at` 设为当前时间。

**与代码的关系**：`FileRecordStore.upsert_record` / `list_records`；上传接口如 `/api/upload/text`、`/api/upload/recording` 等会写入此表。

---

### 4.2 `recording_sessions`

**用途**：表示「一次录音会话」的生命周期与归属桶。用于与 `session_artifacts`、`session_events` 外键关联，支撑更规范的会话维度查询与审计（相对仅依赖 `file_records.session_id` 文本）。

| 字段名 | 类型 | 约束 / 默认值 | 说明 |
|--------|------|----------------|------|
| `id` | `UUID` | `PRIMARY KEY`，默认 `gen_random_uuid()` | 会话内部主键 |
| `session_code` | `TEXT` | `NOT NULL`，`UNIQUE` | 对外/业务侧会话编码（可与流式 `session_id` 或迁移生成的 legacy 编码对应） |
| `bucket_name` | `TEXT` | `NOT NULL` | 该会话主要关联的 MinIO 桶 |
| `source` | `recording_source` | `NOT NULL`，默认 `live` | 会话来源枚举 |
| `status` | `session_status` | `NOT NULL`，默认 `recording` | 会话状态枚举 |
| `started_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 开始时间 |
| `ended_at` | `TIMESTAMPTZ` | 可空 | 结束时间 |
| `note` | `TEXT` | 可空 | 备注；迁移脚本会写入 `migrated from file_records` 等 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 行创建时间 |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 行更新时间（触发器维护） |

**索引**：`(bucket_name, created_at DESC)`、`(status, created_at DESC)`。

**触发器**：`trg_recording_sessions_updated` → `set_updated_at()`。

**说明**：当前主应用路径中，**文件索引仍以 `file_records` 为主**；`recording_sessions` 为扩展模型，供迁移与后续会话化能力使用。

---

### 4.3 `session_artifacts`

**用途**：将一次会话下的 **四类标准产物** 与 MinIO 对象绑定，并强制类型为 `artifact_type` 枚举，比 `file_records.kind` 更严格。

| 字段名 | 类型 | 约束 / 默认值 | 说明 |
|--------|------|----------------|------|
| `id` | `UUID` | `PRIMARY KEY`，默认 `gen_random_uuid()` | 主键 |
| `session_id` | `UUID` | `NOT NULL`，`REFERENCES recording_sessions(id) ON DELETE CASCADE` | 所属会话；父会话删除时级联删除本行 |
| `artifact_type` | `artifact_type` | `NOT NULL` | 产物类型枚举 |
| `bucket_name` | `TEXT` | `NOT NULL` | 桶名 |
| `object_key` | `TEXT` | `NOT NULL` | 对象键 |
| `content_type` | `TEXT` | 可空 | MIME 类型 |
| `byte_length` | `BIGINT` | 可空，`CHECK (byte_length IS NULL OR byte_length >= 0)` | 字节数 |
| `file_ext` | `TEXT` | 可空 | 小写扩展名，迁移时由 `object_key` 解析 |
| `sha256` | `TEXT` | 可空 | 可选的内容摘要，用于去重或校验 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 创建时间 |

**索引**：`(session_id, artifact_type, created_at DESC)`、`(bucket_name, created_at DESC)`、`(sha256)`。

**约束**：`UNIQUE (bucket_name, object_key)` — 全局同一对象键只对应一条附件记录。

---

### 4.4 `session_events`

**用途**：按时间顺序记录与会话相关的 **离散事件**（如迁移完成、上传步骤、自定义业务事件），载荷用 JSONB 灵活扩展。

| 字段名 | 类型 | 约束 / 默认值 | 说明 |
|--------|------|----------------|------|
| `id` | `BIGSERIAL` | `PRIMARY KEY` | 自增主键 |
| `session_id` | `UUID` | 可空，`REFERENCES recording_sessions(id) ON DELETE CASCADE` | 关联会话；允许为空以便记录尚未绑定会话的事件（若业务如此使用） |
| `event_type` | `TEXT` | `NOT NULL` | 事件类型字符串，如迁移脚本中的 `migration` |
| `event_payload` | `JSONB` | `NOT NULL`，默认 `'{}'` | 任意结构化详情 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 事件发生时间 |

**索引**：`(session_id, created_at DESC)`、`(event_type, created_at DESC)`。

**迁移脚本示例**：`migrate_file_records_to_sessions.sql` 会向相关会话插入 `event_type = 'migration'`，`event_payload` 含 `source`、`session_code` 等。

---

### 4.5 `users`

**用途**：Web 端 **注册 / 登录 / JWT** 与 **管理员用户管理** 的用户表，由 `UserStore`（`backend/auth_users.py`）在启动时 `CREATE TABLE IF NOT EXISTS` 与 `schema_all_tables.sql` 对齐；首次无管理员时会插入种子管理员（默认账号见前端登录页文案）。

| 字段名 | 类型 | 约束 / 默认值 | 说明 |
|--------|------|----------------|------|
| `id` | `BIGSERIAL` | `PRIMARY KEY` | 用户 ID |
| `username` | `TEXT` | `NOT NULL`，`UNIQUE` | 登录用户名 |
| `password_hash` | `TEXT` | `NOT NULL` | 密码哈希（非明文） |
| `role` | `TEXT` | `NOT NULL`，默认 `user`，`CHECK (role IN ('admin', 'user'))` | `admin` 可访问用户管理接口 |
| `is_active` | `BOOLEAN` | `NOT NULL`，默认 `true` | 是否允许登录 |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 注册时间 |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`，默认 `now()` | 更新时间（触发器维护） |

**索引**：`role`、`created_at DESC`。

**触发器**：`trg_users_updated` → `set_updated_at()`。

---

## 5. 函数与触发器（公共）

| 名称 | 类型 | 作用 |
|------|------|------|
| `set_updated_at()` | `FUNCTION`（`plpgsql`） | 在 `BEFORE UPDATE` 时将对应行的 `updated_at` 设为 `now()` |
| `trg_file_records_updated` | `TRIGGER` | 挂于 `file_records` |
| `trg_recording_sessions_updated` | `TRIGGER` | 挂于 `recording_sessions` |
| `trg_users_updated` | `TRIGGER` | 挂于 `users` |

**注意**：`schema_all_tables.sql` 中触发器语法使用 `EXECUTE PROCEDURE set_updated_at()`，为 PostgreSQL 历史写法；在较新版本中等价于 `EXECUTE FUNCTION`。若执行报错，可按环境版本调整为 `EXECUTE FUNCTION`。

---

## 6. 迁移脚本 `migrate_file_records_to_sessions.sql` 在做什么

该脚本**不是**日常 ORM 迁移，而是一次性（或可重复执行、带 `ON CONFLICT`）的 **数据迁移**：

1. 从 `file_records` 按归一化后的 `session_code` 聚合，**插入或更新** `recording_sessions`（`source = live`，`status = completed`，`note` 标记来自迁移）。
2. 将符合条件的 `file_records` 行映射为 `session_artifacts`（`kind` 与历史值 `recordings` 的映射见脚本内 `CASE`）。
3. 向 `session_events` 插入 `event_type = 'migration'` 的记录。

用于把旧版「仅 file_records」索引 **对齐到**「会话 + 附件」模型。

---

## 7. `schema_recording_index.sql` 与全量脚本的关系

`schema_recording_index.sql` 包含 **枚举、`recording_sessions`、`session_artifacts`、`session_events`** 及索引、触发器，但 **不包含** `file_records` 与 `users`。

`schema_all_tables.sql` 为 **完整基线**：在 `file_records` 与上述会话表、用户表一并创建，适合作为 Docker `initdb` 或空库初始化脚本。

---

## 8. 与业务扩展（RR / CRR / IR / Wiki）的关系

当前表结构 **未包含** 需求分析、GraphRAG、Wiki 落盘、候选 IR / 正式 IR 等域表。若后续扩展，典型做法是新增 `projects`、`analysis_jobs`、`candidate_ir`、`promoted_ir` 等表，并通过外键或 `session_id` / `user_id` 与现有表关联；**不要**强行把长 JSON 塞进 `session_events` 替代正式业务表，除非仅为调试日志。

---

## 9. 如何在你自己的环境里核对

在已配置 `FILE_INDEX_DATABASE_URL` 的机器上：

```bash
psql "$FILE_INDEX_DATABASE_URL" -c "\dt"
psql "$FILE_INDEX_DATABASE_URL" -c "\d+ file_records"
psql "$FILE_INDEX_DATABASE_URL" -c "\dT+"
```

可列出实际表、列与枚举是否与本文一致。

---

*文档随仓库 schema 维护；若修改 SQL，请同步更新本文。*
