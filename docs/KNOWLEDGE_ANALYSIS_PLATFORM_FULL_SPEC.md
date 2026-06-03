# 知识分析平台：文件管理 · RR/CRR/IR · 工作区 · GraphRAG 对接 — 项目详细说明

> **文档目的**：在 `base_Platform`（Web 与 FastAPI 基座）与 `graphrag`（索引与图谱能力）现状之上，汇总你方提出的产品与技术要求，形成可评审、可拆任务的**统一规格说明**。  
> **仓库依据**：`base_Platform/docs/PROJECT_TARGET_STATE_ANALYSIS.md`、`graphrag/docs/graphrag-engineering-integration.md`、`graphrag/qwen_graphrag_demo/README.md` 与 `ingest/convert_to_graphrag_input.py`。

---

## 一、现状摘要（与目标差距）

### 1.1 `base_Platform` 当前能力

| 维度 | 现状 | 与目标关系 |
|------|------|------------|
| 前端 | Vite + React，`frontend/src/main.tsx` 巨石组件；需求分析区为 **MinIO 树 + 文本预览 + 聊天** | 需扩展：**待分析文件列表**、解析状态、参与分析勾选、CRR/IR 工作流 UI、**知识工作区目录树** |
| 后端 | FastAPI 单文件 `backend/app.py`；上传走 **MinIO**；PostgreSQL 有 `file_records` 等，**无** RR/CRR/IR 表 | 需：**本地/混合落盘路径**、解析流水线、领域表、**服务化拆分** |
| 异步 | 无任务队列；长操作为同步 HTTP | 解析与建索引建议 **后台任务 + 状态轮询** 或至少线程池 + DB 状态 |
| RR→CRR | 仓库内 **无** 专用模型或契约 | 由本规格定义 **平台契约**；可与 LLM 管线或 GraphRAG 后处理组合 |

### 1.2 `graphrag` 当前能力（对接边界）

| 维度 | 结论 |
|------|------|
| 对外形态 | **CLI**（`graphrag index` / `graphrag query`）+ **Python API**（`graphrag.api`）；**无** 官方「RR→CRR」REST |
| 输入 | 由 `settings.yaml` 的 `input_storage` 与 `file_pattern` 决定；演示为 `input/normalized/**/*.txt` |
| 预处理 | `ingest/convert_to_graphrag_input.py`：支持 **txt/md/csv/xls/xlsx/html、pdf/pptx/docx（markitdown）、图片 OCR/视觉描述** 等 |
| 输出 | `output/` 下 **parquet**、**LanceDB**（嵌入式）、可选 **graphml**；查询返回自然语言 + `context_data` |
| 多项目 | **每项目独立根目录**（各自 `settings.yaml`、`output/lancedb`）为工程惯例 |

**重要**：GraphRAG 产物是 **图谱与向量索引**，不是业务上的 CRR/IR JSON；平台需 **自建映射层**，把「解析文本 / RR / CRR / IR」与 `parquet` 行、社区报告、向量 id 关联起来。

---

## 二、术语约定（可再与产品对齐命名）

| 缩写 | 建议含义 | 说明 |
|------|-----------|------|
| **RR** | Raw Requirement / 原始抽取条目 | 从文件直接抽取的片段或结构化项；允许重复、噪声、缺字段 |
| **CRR** | Cleaned / Confirmed / Candidate Requirement Record | 清洗与结构化后的需求记录；含置信度、来源、缺失字段、冲突标记 |
| **IR** | Insight Record（信息资产） | 经确认的沉淀资产；与候选 IR 严格区分 |

---

## 三、总体架构（推荐）

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Web（base_Platform 演进）                  │
│  待分析文件 │ CRR 候选 │ 候选 IR │ 正式 IR │ 知识工作区树 │ Agent   │
└─────────────┬───────────────────────────────────┬─────────────────┘
              │ REST/WebSocket                     │
┌─────────────▼───────────────────────────────────▼─────────────────┐
│                    API Gateway / FastAPI 路由层                    │
│  认证 JWT │ 项目 project_id │ 请求校验 │ 错误码统一                  │
└─────────────┬───────────────────────────────────┬─────────────────┘
              │                                   │
    ┌─────────▼─────────┐               ┌────────▼────────┐
    │  领域服务（拆分）   │               │  异步任务执行器  │
    │  见第四节          │               │  Celery/RQ/线程  │
    └─────────┬─────────┘               └────────┬────────┘
              │                                   │
    ┌─────────▼───────────────────────────────────▼─────────────────┐
    │ PostgreSQL（RR/CRR/IR/文件元数据/版本） + 对象存储或本地卷        │
    └─────────────────────────────────────────────────────────────────┘
              │ 可选：规范化文本同步到 GraphRAG 项目根
    ┌─────────▼─────────┐
    │ GraphRAG 子进程/API │  index / query；每项目独立 root
    └─────────────────────┘
```

---

## 四、后端服务拆分（禁止单接口堆叠）

以下与需求中的建议一一对应，便于独立演进与测试。

| 服务名 | 职责 | 主要依赖 |
|--------|------|----------|
| **FileParserService** | 接收原始文件路径或流；按类型解析；写 `parsed/`；更新 DB 解析状态 | python-docx、pypdf、markitdown、可选 OCR、xlsx 库等 |
| **KnowledgeExtractService** | 从已解析文本生成 **RR** 条目（及可选实体草稿）；写 `rr/rr_result.json` 快照 + DB | LLM 或规则；与 GraphRAG 抽取解耦 |
| **RRToCRRService** | 去重、合并、字段规范化、冲突检测、缺失字段推断；产出 **CRR 候选** | LLM + 确定性校验；写 `crr/crr_candidates.json` + DB |
| **IRGenerateService** | 基于 CRR + 上下文生成 **IR 候选** | LLM |
| **IRAssetService** | 校验、去重、编号、写入 **正式 IR**；更新候选状态；写 `ir/ir_assets.json` | DB 事务 |
| **WorkspaceService** | 目录树、文件预览、刷新；路径校验（防目录穿越） | 本地 `workspace/` 或挂载卷 |

**编排层**（薄）：如 `AnalysisOrchestrator` 只负责参数组装、调用顺序、任务 id 与日志，不把解析细节写在一起。

---

## 五、存储与目录约定

### 5.1 原始上传与解析结果分离（强约束）

| 类型 | 路径（建议） | 说明 |
|------|----------------|------|
| 原始文件 | `/uploads/{project_id}/raw/` 或 MinIO 键 `uploads/{project_id}/raw/...` | 与「解析后」不同前缀，避免追踪混乱 |
| 解析产物 | `/workspace/{project_id}/parsed/` 或与分析会话绑定：`/workspace/{project_id}/{analysis_run_id}/parsed/` | 文本、json 摘要、OCR 侧车文件等 |

**分析会话目录**（与需求中的 RR 批次一致，示例）：

```text
workspace/
└── {project_id}/
    └── RR-{date}-{run_id}/          # 或 session_id
        ├── raw/                     # 可符号链接到 uploads/.../raw/ 同名文件
        ├── parsed/
        ├── rr/
        │   └── rr_result.json
        ├── crr/
        │   └── crr_candidates.json
        ├── ir/
        │   ├── ir_candidates.json
        │   └── ir_assets.json
        ├── graph/                   # 可选：导出 nodes/edges 或 graph_meta
        ├── logs/
        └── reports/
```

若需与 **GraphRAG** 演示对齐：可将 `parsed/*.txt` 同步或复制到 `graphrag/qwen_graphrag_demo/input/normalized/`，再在该项目根执行 `graphrag index`（见 `graphrag` 文档 7.2 / 附录）。

### 5.2 与 `base_Platform` 现状的关系

- 当前平台文件多走 **MinIO**；目标可 **MinIO 存 raw + 本地 workspace 存 parsed/artifacts**，或全本地；需在实现前做一次 **存储策略** 决策（备份、权限、多机挂载）。

---

## 六、模块 1：文件上传与文件管理

### 6.1 前端

**上传组件**

- 支持扩展名：**docx / pdf / md / txt / json / xlsx**（与 `convert_to_graphrag_input.py` 能力对齐时可注明「预处理脚本已支持 csv/html/pptx 等，平台可逐步放开」）。
- 限制：单文件大小、总容量、MIME 校验、病毒扫描（可选）。

**文件列表（「待分析文件」）列**

| 列 | 说明 |
|----|------|
| 文件名 | 原始名 |
| 文件类型 | 扩展名 / MIME |
| 上传时间 | `created_at` |
| 文件大小 | bytes |
| 解析状态 | `pending` / `parsing` / `parsed` / `failed`；失败附 `error_message` |
| 是否已参与分析 | 布尔或关联 `analysis_run_id` |

**操作**

- 上传、删除、预览、**重新解析**、**勾选参与本次分析**（多选 → 传给编排接口的 `files` 列表）。

### 6.2 后端

**保存**：`/uploads/{project_id}/raw/{filename}`（或等价对象键）。

**解析策略**（FileParserService）

| 格式 | 行为 |
|------|------|
| docx | 抽取纯文本（markitdown / python-docx） |
| pdf | 文本层优先；无文本层则 OCR；可选提取内嵌图并走视觉描述 |
| md / txt | 原文本 |
| json | 解析为结构化对象；同时生成人类可读摘要文本供 LLM |
| xlsx | 表结构转文本或 CSV 风格描述 |

**解析结果**：`/workspace/{project_id}/.../parsed/{basename}.txt`（或 `.json` 元数据 + `.txt` 正文）。

**建议 API（示例）**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{project_id}/files/upload` | multipart |
| GET | `/api/projects/{project_id}/files` | 列表 + 状态 |
| DELETE | `/api/projects/{project_id}/files/{file_id}` | 软删或硬删 |
| GET | `/api/projects/{project_id}/files/{file_id}/preview` | 文本或安全 HTML |
| POST | `/api/projects/{project_id}/files/{file_id}/reparse` | 异步任务 |
| PATCH | `/api/projects/{project_id}/files/selection` | 本次分析勾选集 |

---

## 七、模块 2：知识模型处理「服务化」与契约

### 7.1 模型输入（平台统一 JSON）

与需求对齐，作为 **KnowledgePipeline** 或 **POST /api/analysis/run** 的 body 核心：

```json
{
  "project_id": "PCG",
  "skill": "IMC策略分析",
  "mode": "需求分解-自动模式",
  "files": [
    "PCG策划方案.docx",
    "会议纪要_20260402.md"
  ],
  "existing_rr": [],
  "existing_crr": [],
  "existing_ir": [],
  "knowledge_context": []
}
```

**字段说明**

- `files`：建议实际传 `file_id[]` 或 `{ file_id, name }[]`，避免同名歧义。
- `existing_*`：用于增量分析、冲突检测与去重。
- `knowledge_context`：可选检索片段（后续可接向量库 / GraphRAG query 结果）。

### 7.2 模型输出（最小集合）

```json
{
  "crr_candidates": [],
  "ir_candidates": [],
  "knowledge_updates": [],
  "conflicts": [],
  "missing_info": [],
  "logs": []
}
```

**实现说明**：一次 HTTP 若同步跑满流水线易超时；建议返回 `task_id`，上述结构写入 **DB + `workspace/.../json` 快照**，前端轮询 `GET /api/analysis/tasks/{task_id}`。

### 7.3 与 GraphRAG 的衔接（可选路径）

1. **FileParserService** 产出 `parsed/*.txt`。  
2. 复制或生成到 GraphRAG 项目 `input/normalized/`。  
3. 子进程或 worker 调用 `graphrag index` 或 `build_index`。  
4. 将 `entities.parquet` / `community_reports` 等 **摘要映射** 为 `knowledge_updates` 或 `knowledge_context` 的来源；**不**把 GraphRAG 输出直接当作业务 CRR，除非产品明确等价。

---

## 八、模块 3：RR → CRR

### 8.1 RR → CRR 处理逻辑（业务）

- 输入：RR 列表 + 已有 CRR/IR + 文件元数据。  
- 处理：去重、字段补全建议、角色/目标澄清、预算周期交付抽取、与已有信息 **冲突检测**。  
- 输出：CRR 候选（`status: candidate` 等）+ `missing_fields` + `confidence` + `source_files`。

**CRR 单条示例**（与需求一致，可作 API schema）：

```json
{
  "crr_id": "CRR-20260415-001",
  "title": "品牌认知提升策略",
  "goal": "提升品牌认知与转化",
  "target_audience": "待补充",
  "budget": "500万",
  "delivery": "IMC方案",
  "source_files": [
    "PCG策划方案.docx",
    "会议纪要_20260402.md"
  ],
  "confidence": 0.82,
  "status": "candidate",
  "missing_fields": ["目标人群"],
  "created_at": "2026-04-15"
}
```

### 8.2 前端

- CRR 候选列表、详情抽屉/页。  
- 缺失字段、冲突、置信度、来源文件高亮。  
- 字段可编辑；**确认 / 驳回 / 修改** 驱动状态机。

### 8.3 后端与数据库表（建议）

| 表名 | 用途 |
|------|------|
| `requirement_raw` | RR 持久化 |
| `requirement_cleaned` | CRR 当前有效行（候选与已确认可用 `status` 区分或分表） |
| `requirement_source_relation` | CRR/RR 与 `file_id`、文档 span 关联 |
| `requirement_version` | 每次用户编辑或模型重跑产生版本 |

**状态建议**：`candidate` → `confirmed` / `rejected`；已确认可生成不可变版本号。

---

## 九、模块 4：候选 IR（临时）

### 9.1 状态机

| 状态 | 含义 |
|------|------|
| `draft` | 模型刚生成 |
| `reviewing` | 用户查看/编辑中 |
| `accepted` | 已写入正式 IR |
| `rejected` | 驳回 |
| `archived` | 不再默认展示 |

### 9.2 表 `ir_candidate`（建议字段）

`id`, `project_id`, `title`, `content`, `ir_type`, `source_crr_ids`, `source_file_ids`, `confidence`, `status`, `created_by_model`, `model_version`, `created_at`, `updated_at`, `reviewed_by`, `reviewed_at`，以及可选 `rationale`（模型生成原因）、`raw_model_payload`（JSONB）。

### 9.3 前端（第一阶段）

列表、详情、编辑、确认写入、驳回、查看来源与模型原因。

---

## 十、模块 5：正式 IR 资产库

### 10.1 表 `ir_asset`（核心字段）

与需求对齐：`ir_id`, `project_id`, `title`, `content`, `category`, `goal`, `role`, `target_audience`, `budget`, `delivery`, `constraints`, `source_files`, `source_crr_ids`, `source_candidate_id`, `tags`, `status`, `version`, `created_at`, `updated_at`, `created_by`。

**图谱扩展（可选）**：`entity_ids`, `relation_ids`, `graph_node_id`, `embedding_id`。

### 10.2 前端

列表展示：IR 编号、标题、内容摘要、来源、标签、状态、更新时间；操作：查看 / 编辑 / 归档 / 导出 / 关联图谱。

### 10.3 「写入 IR」后端步骤（与需求一致）

1. 校验候选完整性（必填字段、长度等）。  
2. 与已有 `ir_asset` 相似度去重（规则 + 可选向量）。  
3. 生成正式 `ir_id`（全局或项目内唯一）。  
4. DB 事务写入 `ir_asset`。  
5. 候选状态 → `accepted`。  
6. 写入 `workspace/.../ir/ir_assets.json`（或按 IR 分文件）。  
7. 可选：触发 GraphRAG 增量索引或 Neo4j 导出（`export_to_neo4j.py` 同类逻辑）。  
8. 返回最新 IR 列表。

---

## 十一、模块 6：知识工作区

### 11.1 展示内容

右下角 **目录树**：与本地 `workspace/{project_id}/...` 一致；文件夹图标、展开收起、文件大小与 `mtime`。

### 11.2 API（与需求一致）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspace/tree?project_id=PCG` | 返回嵌套 `name` / `type` / `children` / `path` / `size` / `updated_at` |
| GET | `/api/workspace/file?path=...` | 预览；**必须**校验 path 落在允许根目录下 |
| POST | `/api/workspace/refresh` | 刷新缓存或重新扫描 |

**安全**：禁止 `..` 与根外绝对路径；按 `project_id` 与用户权限过滤。

### 11.3 第二阶段能力

上传到指定目录、新建文件夹、删除、重命名、下载、搜索、按类型筛选。

---

## 十二、前端工程化建议（基于 `base_Platform` 现状）

| 项 | 建议 |
|----|------|
| 拆分 | 从 `main.tsx` 拆出 `pages/Analysis/`、`components/FileQueue/`、`components/WorkspaceTree/`、`api/client.ts` |
| 状态 | 文件任务与解析状态适合 **React Query** 或轻量 store |
| 与现有一致 | 保留 JWT、`/api` 代理、LLM 配置栏；新增模块与之共存 |

---

## 十三、数据库迁移策略

- 在 `database/` 下新增 SQL 脚本（与现有 `schema_all_tables.sql` 风格一致）或引入 Alembic（二选一，团队定）。  
- 新表与现有 `file_records` 可 **外键关联** 或并存：若继续用 MinIO，`file_records` 存对象键；若本地 raw，则扩展 `storage_backend` 字段。

---

## 十四、非功能需求（摘要）

| 类别 | 要求 |
|------|------|
| 性能 | 大 PDF 解析与 GraphRAG index 必须异步；超时与重试可配置 |
| 审计 | 关键操作写 `logs/` + DB 审计表（可选） |
| 多租户 | `project_id` 隔离；GraphRAG **每项目独立 root** |
| 错误码 | 平台自建枚举（GraphRAG 无统一业务错误 JSON，见 `graphrag-engineering-integration.md` 7.5） |

---

## 十五、交付分期（建议）

| 阶段 | 内容 |
|------|------|
| **P0** | 上传 + raw/parsed 分离 + 文件列表与解析状态 + WorkspaceService 树与预览 |
| **P1** | RR 抽取 + CRR 候选 + DB 表 + 前端 CRR 确认流 |
| **P2** | 候选 IR + 写入正式 IR + 资产文件落盘 |
| **P3** | GraphRAG 索引联动、图谱可视化、增量更新 |

---

## 十六、附录：关键仓库路径索引

| 路径 | 内容 |
|------|------|
| `base_Platform/backend/app.py` | 现有路由与 MinIO/LLM |
| `base_Platform/frontend/src/main.tsx` | 需求分析 UI 现状 |
| `base_Platform/database/schema_all_tables.sql` | 现有表 |
| `graphrag/docs/graphrag-engineering-integration.md` | GraphRAG 对接说明 |
| `graphrag/qwen_graphrag_demo/ingest/convert_to_graphrag_input.py` | 多格式转文本 |
| `graphrag/qwen_graphrag_demo/settings.yaml` | 输入输出与向量库路径 |

---

*本文档由需求描述与仓库静态分析合并生成；具体字段名、枚举值与 URL 可在详细设计评审中微调。*
