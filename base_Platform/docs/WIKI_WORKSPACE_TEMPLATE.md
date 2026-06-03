# Wiki 工作区模板设计

> **模板路径**：`backend/resources/wiki_template/base_wiki/`  
> **运行时**：`workspace/projects/{project_slug}/`  
> **详细分析**：[`backend/resources/WIKI_RESOURCES_ANALYSIS_ZH.md`](../backend/resources/WIKI_RESOURCES_ANALYSIS_ZH.md)

---

## 一、设计目标

1. **模板与数据分离**：`base_wiki` 随代码发布；项目内容在 `workspace/projects/`（不进 Git）。
2. **中文优先**：README、AGENTS、wiki/index 等为中文脚手架。
3. **与 MinIO / GraphRAG 分工**：raw 存原件引用；parquet/LanceDB 在 8090；**wiki/** 存人类可读 Markdown。

---

## 二、目录结构

### 2.1 模板（只读）

```text
backend/resources/wiki_template/base_wiki/
├── README.md
├── AGENTS.md              # LLM 维护规则
├── llm-wiki.md            # 方法论（英文 idea file）
├── raw/.gitkeep
├── templates/             # 5 类页面模板
│   ├── source-page.md
│   ├── topic-page.md
│   ├── entity-page.md
│   ├── analysis-page.md
│   └── lint-report.md
└── wiki/
    ├── index.md
    ├── overview.md
    ├── log.md
    └── sources|topics|entities|analyses/.gitkeep
```

### 2.2 运行时（按项目）

```text
workspace/projects/{project_slug}/
├── README.md, AGENTS.md, llm-wiki.md
├── raw/
├── templates/
├── wiki/
└── runtime/tasks/{task_id}/
    ├── inputs/
    ├── graphrag_out/
    └── logs/
```

---

## 三、初始化流程

1. `POST /api/workspace/init` 传入 `project_code`、`project_slug`
2. `WorkspaceInitializer` 从 `base_wiki` copytree（若目标不存在）
3. 创建 `runtime/tasks/`
4. 更新 `projects.workspace_root`

代码：`backend/services/workspace_initializer.py`

---

## 四、API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/workspace/init` | 初始化磁盘 + DB |
| GET | `/api/workspace/tree?project_code=` | 扫描 `wiki/` 树 |
| GET | `/api/workspace/file?project_code=&path=wiki/...` | 读 md（限 wiki 前缀） |

---

## 五、与 GraphRAG / 分析任务

| 阶段 | Wiki 角色 |
|------|-----------|
| Phase1 | 不自动写 wiki；GraphRAG 产物在 8090 + `model_artifacts` |
| Phase2+ | 计划用 `WikiWriter` 写 `wiki/analyses/`、`wiki/sources/` 等 |
| 任务目录 | `runtime/tasks/{id}/` 存中间产物，**不是**再拷一份 wiki 树 |

### 5.1 数据流（目标态）

```text
GraphRAG manifest → 平台 Worker → WikiWriter → wiki/*.md
                              └→ wiki_pages 表（可选索引）
```

当前 **WikiWriter 已实现、未接入 Phase1 流水线**。

---

## 六、WikiWriter 能力

文件：`backend/services/wiki_writer.py`

| 方法 | 作用 |
|------|------|
| `write_page(section, filename, content)` | 写 sources/topics/entities/analyses |
| `write_index` / `write_overview` | 更新导航页 |
| `append_log` | 维护 `wiki/log.md` |
| `write_task_readme` | 任务目录 README |

---

## 七、环境变量

| 变量 | 默认 |
|------|------|
| `WORKSPACE_PROJECTS_ROOT` | `{base_Platform}/workspace/projects` |

---

## 八、运维建议

- 升级模板：只影响**新 init** 的项目；已运行项目需手动 merge 或文档说明 diff
- 大文件：GraphRAG parquet 不要放进 `wiki/`
- 权限：前端 tree API 只暴露 `wiki/`，不暴露 `runtime/` 敏感路径

---

*版本：2026-06-03*
