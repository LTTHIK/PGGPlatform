# 项目现状与目标态对接信息清单（自动生成）

> 本文档基于当前仓库的**静态代码与配置**整理，用于从「需求分析页 + DeepSeek + Documents + Agent + SOP」演进至「上传 / Skill / 结构化分析 / RR→CRR / 候选 IR / 正式 IR / Wiki 目录树」。
> **未在仓库中出现的内容**已标注为「空」或「需补充」，不臆造业务定义。

---

## 一、当前项目整体结构

### 1.1 根目录结构（`tree -L 4`，已排除 `node_modules` 等）

```
.
├── backend/                 # FastAPI 后端
│   ├── app.py
│   ├── auth_users.py
│   ├── transcriber.py
│   └── requirements.txt
├── database/                # PostgreSQL 初始化 SQL
│   ├── schema_all_tables.sql
│   ├── schema_recording_index.sql
│   └── migrate_file_records_to_sessions.sql
├── frontend/                # Vite + React 前端
│   ├── src/
│   │   ├── main.tsx         # 单文件承载几乎全部 UI 与请求逻辑
│   │   ├── main.ts          # 另一入口（历史/备用，以 main.tsx 为准）
│   │   └── style.css
│   ├── vite.config.ts
│   └── package.json
├── offline-audio-client/    # 离线音频客户端（独立子项目）
├── paraformer_model/        # ASR 模型权重与配置
├── recordings/              # 本地录音 wav 落盘目录
├── docker-compose.app.yml
├── ecosystem.config.js      # PM2 示例（cwd 指向另一路径，见下文）
├── README.md
└── ...
```

### 1.2 实现决策对照

| 需要判断的内容 | 结论 |
|----------------|------|
| 前后端是否分离 | **是**。`frontend` 独立构建；开发时通过 Vite 代理访问 `/api`、`/ws`。 |
| 页面文件在哪里 | 主要在 `frontend/src/main.tsx`（单一大组件 `App`，无 `pages/` 拆分）。 |
| 后端入口 | `backend/app.py` 中 `app = FastAPI(...)`，由 uvicorn 加载 `backend.app:app`。 |
| 静态资源目录 | `frontend/public/`（favicon、icons）；业务文件主要走 **MinIO 对象存储**，非本地 `public/` Wiki 树。 |
| 环境配置 | 项目根 `.env`（由 `backend/app.py` 的 `load_env_file(PROJECT_DIR / ".env")` 加载）。**请勿将含真实密钥的 `.env` 提交到版本库。** |

---

## 二、前端技术栈与页面源码

### 2.1 技术栈

| 项 | 值 |
|----|-----|
| 框架 | **React 19**（`react` / `react-dom`） |
| 构建 | **Vite 8**（`vite.config.ts`） |
| UI | **Tailwind CSS 3** + 大量内联 `className`；图标 **lucide**（`icons` 动态解析） |
| 状态管理 | **无** Redux/Zustand；全部 `useState` / `useRef` / `useEffect` |
| 请求 | **原生 `fetch`**，封装为组件内 `api()` 函数 |

### 2.2 与截图页面相关的源码位置

**说明**：需求分析、Documents、中间文档区、Intelligence Agent、SOP Library、顶栏模型配置均在 **同一文件** `frontend/src/main.tsx` 内。

| 模块 | 代码位置（概念） | 说明 |
|------|------------------|------|
| 左侧主导航 `STAGES` | 约 L10–L22、L1414–L1427 | 含「需求采集」「需求分析」…「用户管理」；与需求清单中的「需求获取」等命名略有差异（以代码为准）。 |
| 需求分析三栏布局 | `AnalysisModule`，约 **L1266–L1317** | 左：MinIO 树；中：固定标题 + `selectedFileContent`；右：聊天 + SOP 侧栏。 |
| Documents 区 | `AnalysisModule` 左侧，约 L1268–L1277 | 调用 `refreshTree` → `GET /api/minio/tree`。 |
| 中间文档展示 | 约 L1279–L1289 | 固定文案「PCG 策划方案深度细化分析」+ `selectedFileContent`（来自 `GET /api/minio/object`）。 |
| Intelligence Agent | 约 L1291–L1307 | `chatMessages`、`sendChat` → `POST /api/chat`。 |
| SOP Library | `PROMPT_LIBRARY` 常量约 **L32–L36** + 约 L1308–L1314 | 静态数组，点击将 `content` 写入 `chatInput`。 |
| API 配置栏 | 主布局 `header` 内，约 **L1451–L1477** | `llmConfig` + `saveLlmConfig` / `loadLlmConfig`。 |
| 样式 | `frontend/src/style.css` + Tailwind 类名 | |

### 2.3 数据流摘要

| 问题 | 结论 |
|------|------|
| 组件化程度 | **单文件巨石**；重构目标态时建议拆分为 `pages/`、`components/`、`api/`。 |
| Documents 数据 | **真实接口**：MinIO 桶与对象键列表，非纯假数据。 |
| 文件选择 | 有：`handleSelectObject` 拉取对象预览文本。 |
| Agent 聊天 | 有：`POST /api/chat`，附带当前选中文件内容截断（约 12000 字符）。 |
| SOP Library | **静态前端常量**，非数据库。 |

### 2.4 开发代理

`frontend/vite.config.ts`：

- 前端 dev：`https`，端口 **5173**，host `0.0.0.0`
- 代理：`/api` → `http://127.0.0.1:18000`；`/ws` → `ws://127.0.0.1:18000`

---

## 三、当前后端技术栈

| 项 | 值 |
|----|-----|
| 语言 | Python 3 |
| 框架 | **FastAPI**（`fastapi`），ASGI 服务为 **uvicorn** |
| 入口 | `backend/app.py` 中 `app` 实例 |
| 典型启动命令 | `python -m uvicorn backend.app:app --host 0.0.0.0 --port 18000`（与 `ecosystem.config.js` 中 args 一致，但该文件 `cwd` 指向其他目录，部署时需按实际路径修改） |
| 端口 | **18000**（与 Vite 代理一致）；Docker 映射示例 `18001:18000`（`docker-compose.app.yml`） |
| 路由分层 | **无**独立 `routes/` 包；路由均写在 `app.py` |
| 文件上传 | 有：`/api/upload/text`、`/api/upload/recording`、`/api/upload/all`、`/api/client/upload/audio`；转写 `POST /api/transcribe` |
| 数据库 | **PostgreSQL**（`psycopg`），连接串环境变量 `FILE_INDEX_DATABASE_URL` |
| 异步任务 | **无** Celery/RQ 等；长操作为同步 HTTP（LLM、转写等在同请求内完成） |

### 3.1 后端目录结构（实际）

```
backend/
├── app.py           # 路由、LLM、MinIO、上传、认证
├── auth_users.py    # 用户与 JWT
├── transcriber.py   # Paraformer ASR
├── requirements.txt
└── __init__.py
```

---

## 四、DeepSeek / 大模型调用逻辑

### 4.1 配置存储位置

| 层级 | 说明 |
|------|------|
| 进程启动 | 自项目根 `.env` 读取 `DEEPSEEK_BASE_URL`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`DEEPSEEK_VERIFY_SSL`、`DEEPSEEK_TIMEOUT_S` |
| 运行时可变配置 | 内存字典 `llm_runtime_config`（线程锁 `llm_config_lock`），可通过 API 更新；**不落库**（重启后仍以 `.env` 与上次 `POST` 合并行为为准：以代码逻辑为准——`set_llm_runtime_config` 仅改内存） |

### 4.2 前端调用

| 操作 | 方法 | 路径 |
|------|------|------|
| 加载配置 | `GET` | `/api/llm/config` |
| 保存配置 | `POST` | `/api/llm/config`，JSON body：`base_url`、`model`、`api_key` |

均需登录：`Authorization: Bearer <token>`（公开路由除外）。

### 4.3 后端读取 Secret Key

- 启动时：`DEEPSEEK_API_KEY` 环境变量填入 `llm_runtime_config["api_key"]`
- 前端保存后：`update_llm_config` 将请求体写入 `llm_runtime_config`
- 实际调用：`build_llm_client()` → `DeepSeekClient`，使用当前 `llm_runtime_config` 的 `api_key`

### 4.4 `chat/completions` 封装

- 类：`DeepSeekClient`（`backend/app.py`）
- 方法：`chat(messages)` → `POST {base_url}/chat/completions`，OpenAI 兼容形态
- 使用处：`/api/polish`、`/api/minutes`、`/api/chat`

### 4.5 是否只支持 DeepSeek

- 代码层为 **任意 OpenAI 兼容** `base_url` + `model` + Bearer Key；默认文案与常量偏向 **DeepSeek**。
- **仓库内无** RR/CRR 专用模型调用。

### 4.6 「加载模型配置失败：HTTP 502」分析（基于架构推断 + 日志线索）

| 项目 | 内容 |
|------|------|
| 失败请求（推断） | 浏览器访问 `GET /api/llm/config`（经 Vite 代理到 `127.0.0.1:18000`） |
| 502 常见原因 | **Vite 代理无法连接后端**（uvicorn 未启动、端口非 18000、防火墙）时，开发服务器常返回 **502 Bad Gateway**。 |
| 非 DeepSeek 远端直接导致 | `GET /api/llm/config` **不调用** DeepSeek；仅读内存配置。若后端正常应返回 200 或 401（未登录）。 |
| 历史日志 | `logs/backend-out-0.log` 中有 `GET /api/llm/config` **200** 记录，说明在部分环境中接口可用。`logs/backend-error-*.log` 存在 **18000 端口已被占用** 导致启动失败记录。 |

**建议排查顺序**：1）本机 `127.0.0.1:18000` 是否有进程监听；2）前端是否走 Vite 代理（相对路径 `/api/...`）；3）是否已登录（未登录应为 401 而非 502，除非连接未建立）。

---

## 五、RR → CRR 知识图谱模型信息

**仓库内状态**：**未发现** RR→CRR 模型代码、服务地址、Dockerfile、专用 `requirements`、或相关 HTTP/CLI 入口。

| 小节 | 内容 |
|------|------|
| 5.1 运行方式 | **空**（需你方提供模型形态：本地函数 / 子进程 / HTTP 服务 / Docker / GPU 等） |
| 5.2 模型入口 | **空** |
| 5.3 依赖与权重 | **空**（本仓库仅有 ASR 相关 `paraformer_model/` 与 `_wenet_pkg/`） |
| 5.4 RR 输入样例 | **空**（需业务或模型侧提供） |
| 5.5 CRR 输出样例 | **空** |

---

## 六、RR / CRR / IR 业务定义

**仓库内状态**：代码与 SQL **未定义** RR、CRR、IR 领域模型。

| 对象 | 仓库内依据 | 需产品/算法补充 |
|------|------------|-----------------|
| RR | 无 | 缩写含义、字段、是否入库、与文件关系 |
| CRR | 无 | 与 RR 映射关系、是否入图数据库、与 Wiki 映射 |
| IR | 无 | 候选 vs 正式、是否可编辑、版本、与 `wiki/analyses` 关系 |

---

## 七、现有数据库信息

- **类型**：PostgreSQL（从 `psycopg`、`docker-compose.app.yml` 与 `database/schema_all_tables.sql` 可知）。
- **ORM**：**无** SQLAlchemy 等；`FileRecordStore`、`UserStore` 等使用原始 SQL（见 `backend/app.py`、`auth_users.py`）。
- **迁移工具**：仓库提供 **SQL 脚本**（`database/`），未见 Alembic。

### 7.1 主要表（摘自 `schema_all_tables.sql`）

| 表名 | 用途 |
|------|------|
| `file_records` | 文件索引（bucket、object_key、kind、session_id 等） |
| `recording_sessions` | 录音会话主表 |
| `session_artifacts` | 会话产物（枚举含 `recording_wav`、`raw_transcript`、`formal_text`、`meeting_minutes`） |
| `session_events` | 会话事件审计 JSONB |
| `users` | 用户、`role`：`admin` / `user` |

**无** 与 RR、CRR、IR、Wiki 页面对应的表。

---

## 八、Wiki 工作区模板（Chinese-LLM-Wiki-main）

**仓库内状态**：**未包含** `Chinese-LLM-Wiki-main` 或 `templates/`、`wiki/` 等目录。  
实现「必须按模板落盘」需将模板**作为子模块或拷贝**纳入仓库后再对接 Writer。

---

## 九、目标页面结构与交互（需业务确认）

以下为用户目标态描述与**当前代码差异**，供评审填空：

| 子项 | 当前实现 | 目标态（来自需求描述） | 确认方 |
|------|----------|------------------------|--------|
| 左侧导航 | 11 个阶段 + 用户管理；仅 `capture`、`analysis`、`users` 有实质内容 | 是否保留全部、是否只改「需求分析」 | 产品 |
| Documents | MinIO 对象树 + 文本预览 | 是否改为本地上传 + Wiki/raw 树 | 产品 |
| 中间区 | 固定标题 + 预览文本 | 结构化分析 / CRR / 候选 IR / Markdown | 产品 |
| Agent | DeepSeek 聊天 + 文件上下文 | 是否保留、是否读 Wiki、是否触发 Skill | 产品 |
| SOP | 静态 `PROMPT_LIBRARY` | 是否映射 Skill、配置来源 | 产品 |
| 新增区 | 无 Skill 下拉、无进度条、无 IR 表、无 Wiki 目录树 | 全部待设计 | 产品 |

---

## 十、文件存储规则（建议 vs 当前）

| 规则项 | 当前仓库行为 | 与目标模板对齐建议（待拍板） |
|--------|--------------|------------------------------|
| 原始上传 | 音频/文本等多上传至 **MinIO**；本地 `recordings/` 存实时录音 wav | 若坚持 Wiki：`raw/` 需在服务端映射（拷贝或挂载），**当前无** |
| Wiki 根目录 | 无 | 每项目一目录或全局 workspace：**空**（需决策） |
| 候选 IR | 无 | 建议 DB 或 runtime（与需求一致） |
| 正式 IR | 无 | `wiki/analyses/` 需模板与 Writer |

---

## 十一、后端任务流程

| 项 | 结论 |
|----|------|
| 任务队列 | **无** |
| 前端轮询 | **无**现成任务 ID 流程 |
| 取消 / 重试 / 并发控制 | **无** |
| 长流程（解析→RR→CRR→IR→Wiki） | 当前架构为**同步** HTTP，扩展需新增任务子系统或至少后台线程 + 状态存储 |

---

## 十二、当前 API 清单（`backend/app.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 + ASR/DeepSeek 是否配置 key |
| POST | `/api/auth/register` | 注册（普通用户） |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/admin/users` | 管理员：用户列表 |
| POST | `/api/admin/users` | 管理员：创建用户 |
| PATCH | `/api/admin/users/{user_id}` | 管理员：更新用户 |
| GET | `/api/llm/config` | 读取 LLM 配置 |
| POST | `/api/llm/config` | 更新 LLM 配置 |
| POST | `/api/transcribe` | 上传音频转写 |
| WS | `/ws/asr` | 实时流式 ASR（query `token`） |
| POST | `/api/polish` | 口语书面化 |
| POST | `/api/minutes` | 会议纪要 |
| POST | `/api/chat` | 通用聊天 |
| GET | `/api/minio/tree` | 桶与对象键树 |
| GET | `/api/minio/object` | 对象预览文本 |
| GET | `/api/files/records` | PostgreSQL 文件索引记录 |
| POST | `/api/upload/recording` | 上传会话录音到 MinIO |
| POST | `/api/upload/recording/latest` | 上传最新本地 wav |
| POST | `/api/client/upload/audio` | 客户端上传音频 |
| POST | `/api/upload/text` | 文本上传 MinIO（kind: raw/formal/minutes） |
| POST | `/api/upload/all` | 组合上传 |

**统一前缀**：`/api`。  
**认证**：除注册、登录、健康检查外，多数路由依赖 JWT（见 `require_user` / `require_admin`）。

---

## 十三、权限与用户信息

| 项 | 结论 |
|----|------|
| 登录 | **有**（JWT，`localStorage` 键 `pgg_auth_token`） |
| 角色 | `admin`、`user`；用户管理仅 admin |
| 审核人 / IR promote | **未实现** |
| 操作日志 | `session_events` 与会话相关；**无**通用审计表 |

---

## 十四、最小信息集（P0 / P1 / P2）对照

### P0（启动目标态设计前建议齐备）

| # | 项 | 本仓库 |
|---|-----|--------|
| 1 | 项目目录结构 | **已提供**（本文第一节） |
| 2 | 当前页面源码 | **已定位** `frontend/src/main.tsx` |
| 3 | 后端框架与入口 | **已提供** FastAPI `backend/app.py` |
| 4 | API 配置与 DeepSeek 调用 | **已提供** |
| 5–7 | RR→CRR 与样例 | **空** |
| 8 | Wiki 模板原文件 | **空**（不在仓库） |

### P1

| 项 | 本仓库 |
|----|--------|
| 数据库与表 | **已提供** PostgreSQL + 脚本；无 IR 相关表 |
| 文件上传 | **有**（MinIO + 多种 upload API） |
| Documents 数据来源 | **MinIO tree API** |
| SOP 数据来源 | **前端静态** |
| 502 详细 Network 抓包 | **空**（需浏览器现场导出；推断见第四节） |
| IR 样例 | **空** |

### P2

权限细化、多项目、并发、图数据库、全文/向量检索等：**未在仓库体现**，标为 **空**。

---

## 十五、建议交付顺序（与你方清单对齐）

1. 项目目录结构 → 见第一节  
2. 前端页面源码 → `frontend/src/main.tsx`（重点 `AnalysisModule`、header LLM、`STAGES`）  
3. 后端入口与路由 → `backend/app.py`  
4. RR→CRR 模型说明 → **需外部补充**  
5. RR/CRR JSON 样例 → **需外部补充**  
6. Wiki 模板目录 → **需拷贝进仓库**  
7. 数据库信息 → `database/schema_all_tables.sql` + `FILE_INDEX_DATABASE_URL`  
8. 502 日志 → 结合 **后端是否监听 18000** + Vite 代理行为排查；历史日志见 `logs/`  

---

## 十六、安全与运维提示（仓库扫描）

- 根目录存在 `.env` 时，**务必将真实 API Key 移出版本控制**，使用 `.env.example` 占位 + `.gitignore` 忽略 `.env`。
- `ecosystem.config.js` 内 `cwd` 指向 `minimal_craft_deploy`，与本仓库路径不一致，PM2 一键启动前需修改。
- MinIO 默认 endpoint/密钥在 `backend/app.py` 源码中硬编码为默认值，生产环境应改为环境变量并轮转密钥。

---

## 附录 A：关键文件引用（行号供仓库内跳转）

- 前端代理与端口：`frontend/vite.config.ts`（`/api` → `127.0.0.1:18000`）  
- 前端 LLM 加载/保存：`frontend/src/main.tsx` 约 L302–L326、L1451–L1477  
- 需求分析布局：`frontend/src/main.tsx` 约 L1266–L1317  
- 后端 LLM 与路由：`backend/app.py`（`DeepSeekClient` 约 L146–183；`/api/llm/config` 约 L667–688）  

---

*文档生成方式：对仓库执行目录列举、全文检索与分段阅读；未运行应用态抓包。*
