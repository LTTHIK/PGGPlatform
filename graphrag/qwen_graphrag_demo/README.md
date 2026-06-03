# GraphRAG 演示工程 · `qwen_graphrag_demo`

本目录是一套**可独立运行**的演示：企业多格式资料 → 标准化文本 → **GraphRAG 索引（知识图谱 + 向量）** → 检索问答。当前默认配置（见 `settings.yaml`）为：**智谱 GLM（OpenAI 兼容）** 负责补全/抽取/社区报告等；**阿里云 DashScope** 负责 **`text-embedding-v3`** 嵌入及预处理 **`--enable-vision`** 的视觉描述（密钥分别为 **`ZHIPU_*`** 与 **`DASHSCOPE_*` / `VISION_*`**，可按需改为同一厂商）。

**图谱浏览推荐**：静态图与 Pyvis 适合出图；若要 **Neo4j Browser 式**拖拽、属性面板与 **Cypher**，用本仓库的 `export_to_neo4j.py` 将 `entities.parquet` / `relationships.parquet` 导入 Neo4j（见 [§8](#8-知识图谱推荐-neo4j-browser)）。

---

## 文档导航

| 章节 | 内容 |
|------|------|
| [1. 项目目录](#1-项目目录) | 目录树与路径含义 |
| [2. 环境与依赖](#2-环境与依赖) | Conda、`.env`、`pip` |
| [3. 模型与环境变量](#3-模型与环境变量) | `settings.yaml`、智谱 + DashScope、嵌入 batch |
| [4. 支持的数据格式](#4-支持的数据格式) | 预处理格式与目录约定 |
| [5. 全量流程（主库）](#5-全量流程主库) | 预处理 → `graphrag index` → 查询 |
| [6. 增量流程](#6-增量流程) | `incremental_update.py`、`delta`、`creation_date` |
| [7. 查询](#7-查询) | 主库与 `-d` 增量库 |
| [8. 知识图谱（推荐 Neo4j Browser）](#8-知识图谱推荐-neo4j-browser) | Docker、导入脚本、常见踩坑 |
| [9. 其他可视化（PNG / Pyvis）](#9-其他可视化png--pyvis) | `visualize_graph.py` |
| [10. 常见问题](#10-常见问题) | LiteLLM、字体、限流、检索模式 |
| [11. 按时间清理 LanceDB 向量](#11-按时间清理-lancedb-向量) | `purge_stale_vectors.py` |
| [12. 运行清单 JSON（`record_run_manifest`）](#12-运行清单-jsonrecord_run_manifest) | 建库/增量后追溯路径与统计 |
| [附录 · 命令速查](#附录--命令速查) | 一键复制 |

---

## 1. 项目目录

```text
qwen_graphrag_demo/
├── .env                    # API 密钥（勿提交仓库）
├── settings.yaml           # 模型、分块、向量、工作流
├── README.md
│
├── data/                   # 全量原始数据（docx / excel / images / pdf / pptx 等）
├── data_increment/       # 增量原始数据（结构不必与 data 完全一致）
│
├── ingest/
│   ├── convert_to_graphrag_input.py
│   ├── requirements.txt
│   └── README.md
│
├── input/                  # GraphRAG input_storage（见 settings.yaml）
│   ├── normalized/         # 预处理输出的 txt
│   └── increment_*/        # 增量预处理子目录
│
├── output/                 # 主库（默认 query 不加 -d）
│   ├── entities.parquet
│   ├── relationships.parquet
│   ├── documents.parquet
│   ├── text_units.parquet
│   ├── communities.parquet
│   ├── community_reports.parquet   # local/global 查询依赖
│   ├── graph.graphml
│   ├── lancedb/
│   └── context.json / stats.json / …
│
├── output_increment_*/     # 增量归档；其下 运行批次/delta 为融合后可查询库
├── output_clean/           # 可选：clean_graph_inputs
├── update_output/          # update 临时目录
├── prompts/  cache/  logs/
│
├── incremental_update.py
├── record_run_manifest.py   # 建库/增量后生成 run_manifest_*.json
├── visualize_graph.py
├── export_to_neo4j.py      # parquet → Neo4j
├── purge_stale_vectors.py
├── quality_check.py
├── clean_graph_inputs.py
└── graph_preview*.png      # 可视化产物（可删）
```

| 路径 | 用途 |
|------|------|
| `data/` | 全量原件 → `convert_to_graphrag_input.py --source-dir ./data` → `graphrag index` |
| `data_increment/` | 增量原件 → `incremental_update.py --source-dir ./data_increment` |
| `input/normalized/` | 实际参与索引的 txt（由 `input.file_pattern` 决定） |
| `output/` | 主库 |
| `…/delta/` | 某次增量后的**整库快照**；`graphrag query -d …/delta` |

---

## 2. 环境与依赖

```bash
conda activate graphrag311
cd qwen_graphrag_demo
pip install -r ingest/requirements.txt
```

`.env` 与当前 `settings.yaml` 对齐的典型写法（**勿将真实密钥提交仓库**）：

```dotenv
# 智谱：GraphRAG 补全 / 抽取 / 社区报告等（OpenAI 兼容）
ZHIPU_API_KEY=你的_智谱_API_Key
ZHIPU_API_BASE=https://open.bigmodel.cn/api/paas/v4

# DashScope：嵌入 + 可选与视觉共用
DASHSCOPE_API_KEY=你的_DashScope_sk_密钥
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# 预处理 --enable-vision 时优先使用（不设则用 DASHSCOPE_API_KEY）
VISION_API_KEY=你的_DashScope_sk_密钥
```

国际域可将 `DASHSCOPE_API_BASE` 改为 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`。

**`ingest/requirements.txt`**：预处理脚本依赖（含 `httpx`、`pyarrow`、`PyYAML` 等）。**`graphrag index` / `query`** 仍需在已安装 **GraphRAG** 的 Conda 环境（如 `graphrag311`）中执行。

---

## 3. 模型与环境变量

逻辑在 `settings.yaml`（密钥等用 `${VAR}` 从 `.env` 注入）。

| 用途 | 配置位置 | 说明 |
|------|----------|------|
| 补全 / 抽取 / 社区报告等 | `completion_models.default_completion_model` | 当前示例：`glm-4.5-air`，`api_base` 指向智谱 OpenAI 兼容网关；`call_args` 中含 `max_tokens`、`timeout`、关闭深度思考的 `extra_body.thinking` 等 |
| 向量嵌入 | `embedding_models.default_embedding_model` | `text-embedding-v3`；**不要**在 `call_args` 里写 `dimensions`；需 `encoding_format: "float"`；`embed_text.batch_size` 对 DashScope **≤10**（否则 400） |
| 向量化列 | `embed_text.names` | 当前含 `entity_description`、`community_full_content`、`text_unit_text`；与 `vector_store.index_schema` 一致 |
| 流水线 | `workflows` | 含 `create_community_reports` 方可使用 **`--method local` / `global`** |

建议 `concurrent_requests: 1` 降低限流概率。

- **换智谱对话模型**：改 `model` / `api_base` 及智谱文档中的参数。参考 [智谱开放文档](https://docs.bigmodel.cn/)。  
- **换千问嵌入 / 地域**：改嵌入 `model`、`api_base` 与 `.env` 中 `DASHSCOPE_API_BASE`。参考 [Qwen OpenAI 兼容](https://docs.qwencloud.com/api-reference/toolkitframework/openai-compatible/overview)。  
- **换嵌入模型或维度**：同步改 `vector_store` 的 `vector_size`，并**删 `output/` 与 `cache/` 后全量重建**。

---

## 4. 支持的数据格式

预处理支持：`docx`、`pdf`、`pptx`、`xlsx`/`xls`/`csv`、`png`/`jpg`/`jpeg`/`webp`（可选 **OCR** 与/或 **视觉描述**）、`txt`/`md`/`html`/`htm`。

`data` 与 `data_increment` **目录结构不必一致**：脚本**递归扫描** `--source-dir` 下支持的扩展名；索引只认 `input/normalized` 里符合 `file_pattern` 的 txt。

---

## 5. 全量流程（主库）

在**本目录**下执行（路径以你本机克隆位置为准）。

**预处理**（续行时反斜杠须为行末最后一个字符，其后不能有空格）：

```bash
python ingest/convert_to_graphrag_input.py \
  --source-dir ./data \
  --target-dir ./input/normalized \
  --enable-ocr \
  --enable-vision
```

单行示例：

```bash
python ingest/convert_to_graphrag_input.py --source-dir ./data --target-dir ./input/normalized --enable-ocr --enable-vision
```

- `--enable-ocr`：本机需 tesseract。  
- `--enable-vision`：需 `openai` 等依赖；Bearer 优先 `VISION_API_KEY`，否则 `DASHSCOPE_API_KEY`。默认视觉 API 与模型与上文 DashScope 一致；慢请求可调 `--vision-timeout`，大图见脚本内缩放参数。脚本会加载项目根 `.env`。

**建库与查询**：

```bash
graphrag index --skip-validation
graphrag query "你的问题" --method basic
# 同一套 output 下也可（需已按当前 settings 跑过含 create_community_reports 的全量 index）：
# graphrag query "你的问题" --method local
# graphrag query "你的问题" --method global
```

**启用 `local` / `global` 后**：流水线会生成 **`community_reports.parquet`**，并向量化 **`entity_description`、`community_full_content`、`text_unit_text`**，智谱与 DashScope 调用量、耗时均会上升。若曾用旧配置建库，改动后请 **`rm -rf output cache` 再 `graphrag index`**。

**全量重来主库（换原始数据或改 workflows / 嵌入列时）**：建议 `rm -rf output cache`，按需清空 `input/normalized/` 后重新预处理，再 **`graphrag index`**。建库成功后可用 **`python record_run_manifest.py --pretty`**（§12）生成清单 JSON。

**`graphrag index --skip-validation` 含义**：`--skip-validation` 表示**跳过建索引前的配置自检**。默认（不加该参数）时，GraphRAG 会对每个补全模型发一条极短连通性测试、对每个嵌入模型发一条测试 embedding；若当前用于 `embed_text` 的嵌入产出维度与 `settings.yaml` 里 `vector_store` 的 `vector_size` 不一致，自检阶段还可能把运行中的 `vector_size` 改成与模型实际输出一致。加上本参数后**不再**做上述请求，可少打几轮 API、启动更快，适合环境已确认无误或需规避校验阶段限流的场景；**首次**换新密钥、新 base、新嵌入模型或不确定向量维度时，更建议先执行 **`graphrag index`**（不加 `--skip-validation`），让自检尽早暴露配置问题。

---

## 6. 增量流程

**一键**（保留现有 `output/`，归档到 `output_increment_*`）：

```bash
python incremental_update.py \
  --source-dir ./data_increment \
  --run-update \
  --skip-validation \
  --enable-vision
```

（可选同样传入 `--enable-ocr` / `--vision-model` 等，与全量一致。）

**查询增量融合库时，`-d` 必须指向 `delta`**：

```text
output_increment_时间戳/运行批次时间戳/delta/   ← 这里
```

否则可能报错：`Could not find text_units.parquet in storage!`

```bash
graphrag query "你的问题" --method basic \
  -d ./output_increment_20260409_212025/20260409-212051/delta
```

**说明**：

- `delta/` 是 update 完成后的**整库快照**（主库状态 + 增量合并），不是「仅增量片段」。  
- 看「主库+增量」图用 `delta/graph.graphml`；仅看上次全量 index 的图用 `output/graph.graphml`。  
- **creation_date**：本轮**新**进入索引的 txt 多用文件 `st_ctime`；已存在同 `title` 的文档从 `previous` 合并时**不会**把 `creation_date` 改成当前时间。业务日期请写入正文或元数据；GraphRAG 不会从 PDF 推断公告日。  
- 多轮增量：继续在 `data_increment/` **追加**文件即可；每轮会新建 `increment_*` 与 `output_increment_*` 时间戳目录。

---

## 7. 查询

| 场景 | 命令 |
|------|------|
| 主库（向量块检索，依赖最少） | `graphrag query "…" --method basic` |
| 主库（实体+关系+文本+社区混合） | `graphrag query "…" --method local` |
| 主库（社区报告 map-reduce） | `graphrag query "…" --method global` |
| 某次增量融合库 | 上述命令加 `-d …/output_increment_*/…/delta` |

`local` / `global` 需要 **`output/community_reports.parquet`** 及对应向量（见 `settings.yaml` 中 `workflows` 与 `embed_text.names`）。缺表时报错见 [§10](#10-常见问题)。**仅 basic、且想省 API**：可自行从 `workflows` 去掉 `create_community_reports`，并把 `embed_text.names` 缩回 `[text_unit_text]` 后重建索引。

---

## 8. 知识图谱（推荐 Neo4j Browser）

目标：**拖拽节点、查看属性、写 Cypher**，与 Neo4j Desktop / Browser 一致的体验。数据来自 `entities.parquet` 与 `relationships.parquet`（不是 `graph.graphml`），以保留 `title`、`type`、`description`、`weight` 等字段。

**数据模型（导入后）**：

- 节点标签：`Entity`，稳定主键属性：`graphrag_id`（对应 GraphRAG 实体 `id`）。  
- 关系类型：`RELATED`（parquet 无独立关系名）；`description`、`weight` 等在关系属性上。  
- 社区报告、向量仍在原 parquet / LanceDB，**未**导入 Neo4j。

### 8.1 用 Docker 启动 Neo4j

拉镜像若遇 Docker Hub 超时，可在 `/etc/docker/daemon.json` 配置 `registry-mirrors`（如 DaoCloud、阿里云**个人**镜像加速地址），`systemctl restart docker` 后再 `docker pull neo4j:5-community`。

**Neo4j 5 要求初始密码至少 8 个字符**（例如不要用 `0000`）。首次启动示例：

```bash
docker run -d --name graphrag-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/至少八位密码 \
  neo4j:5-community
```

浏览器打开 `http://127.0.0.1:7474`，用户 `neo4j`，密码与 `NEO4J_AUTH` 中一致。

若容器名已占用：优先 **`docker start graphrag-neo4j`** 复用旧容器；确需重建再 **`docker rm graphrag-neo4j`** 后重新 `docker run`。

### 8.2 再次启动与进入容器

关机、重启 Docker 或容器退出后，**不会**自动运行，需要先启动再连 Browser / Bolt：

```bash
docker start graphrag-neo4j
```

查看是否在跑：`docker ps --filter name=graphrag-neo4j`。若 `docker exec` 报 `container … is not running`，多半是未执行上面的 `start`。

需要进容器里看文件、调配置时（**导入 GraphRAG 的 Python 脚本仍在宿主机执行**）：

```bash
docker exec -it graphrag-neo4j bash
```

若镜像内无 `bash`，可改用 `docker exec -it graphrag-neo4j sh`。退出容器内 shell 用 `exit`，不会停止 Neo4j 进程。

### 8.3 导入 GraphRAG 产物（在宿主机执行）

**必须在安装 Python、且含有 `output/`（或增量 `delta/`）的机器上执行**，与 Neo4j 通过 `bolt://127.0.0.1:7687` 通信。  
**不要**在 `docker exec` 进入的 Neo4j 容器里跑脚本（镜像内通常无 Python、也无你的工程目录）。

```bash
pip install neo4j pyarrow
export NEO4J_PASSWORD='与上面 NEO4J_AUTH 中相同的密码'
cd /你的路径/qwen_graphrag_demo
python export_to_neo4j.py --output-dir ./output --clear
```

- 增量库：把 `--output-dir` 改为 `…/output_increment_*/运行批次/delta`。  
- `--clear`：删除图中**所有** `:Entity` 节点及其关系后再写入；若同一 Neo4j 实例上还有别的业务图，请使用独立 database（`--database`，Neo4j 5）或去掉 `--clear` 仅 MERGE 更新。

成功时终端会打印实体数、关系数；随后在 Browser 中执行：

```cypher
MATCH (n:Entity) RETURN n LIMIT 50;
MATCH (a:Entity)-[r:RELATED]->(b:Entity) RETURN a, r, b LIMIT 100;
```

**远程 Neo4j**：在能访问 Bolt 的机器上设置 `export NEO4J_URI='bolt://主机:7687'`，并保证网络或 SSH 隧道可达。

---

## 9. 其他可视化（PNG / Pyvis）

**主库**：

```bash
python visualize_graph.py \
  --graph ./output/graph.graphml \
  --topk 50 --show-edge-weight \
  --out ./graph_preview_main.png
```

**增量 `delta` 图**（路径按本机修改）：

```bash
python visualize_graph.py \
  --graph ./output_increment_时间戳/运行批次/delta/graph.graphml \
  --topk 80 --show-edge-weight \
  --out ./graph_merged.png
```

**交互 HTML**（`pip install pyvis`）：

```bash
python visualize_graph.py \
  --graph ./output/graph.graphml \
  --html-out ./graph.html --out ./graph.png
```

**中文字体与「图上只有 P001 这类数字」**：

- matplotlib 默认 **DejaVu Sans** 不含汉字，标题与中文 **node id** 会变成**方框**；若 id 形如 `P003 矿区…`，往往只剩 **ASCII 前缀**像数字，看起来像「只有编号」。  
- `visualize_graph.py` 会在已注册字体中**自动匹配**文泉驿 / Noto CJK / 思源黑体 / 微软雅黑等（无需与旧版那样写死完整注册名）。  
- 仍告警时：安装字体（Debian/Ubuntu 示例）`sudo apt install fonts-noto-cjk` 或 `fonts-wqy-zenhei`，再重新运行脚本；或手动指定 **`--font 'Noto Sans CJK SC'`**（以本机 `fc-list` 已安装名为准）。  
- 脚本若调用 `plt.show()`，看到「已保存」后可关窗或 `Ctrl+C`。`Glyph missing` 时 PNG 有时仍写出，但文字会缺笔；修好字体后应重新导出。

---

## 10. 常见问题

| 现象 | 处理 |
|------|------|
| `No entities detected` 且日志里 `cache_hit_rate` 很高 | 多为**旧 LLM 缓存**（例如曾把 `max_tokens` 设得很小）；删 `cache/` 后重跑 `graphrag index`；新版本 graphrag-llm 已让缓存键包含 `max_tokens` 等参数 |
| `LiteLLM … Network is unreachable` | 多为拉远程价格表失败，一般**可忽略**，不影响推理与检索 |
| `RateLimitError` | `index` / `update` 使用 `--skip-validation`，降低并发，稍后重试 |
| `batch size is invalid … larger than 10`（嵌入 400） | DashScope 单次嵌入条数上限为 **10**。在 `settings.yaml` 的 `embed_text.batch_size` 设为 `10`（默认 GraphRAG 为 16 会触发此错误） |
| `extract_graph` 长时间停在 `n/22` | 进度按**整块文本**更新，块内可能多次调 LLM；智谱 GLM-4.5 若开「深度思考」会极慢。当前 `settings.yaml` 已通过 `extra_body.thinking` 关闭思考、并将 `extract_graph.max_gleanings` 设为 0；仍慢可调大 `completion_models.*.call_args.timeout` |
| `Could not find community_reports.parquet` | 用当前 `settings.yaml` 全量 `graphrag index`；或改回含 `create_community_reports` 的流水线并删 `output`/`cache` 重建 |
| `local` / `global` 效果差 | 调 `community_reports` 长度、查询 `--community-level`；仍不稳可先用 `--method basic` |
| 中文字体 `Glyph missing … DejaVu Sans`、图上中文变方块只剩 `P00x` | 见 **§9**：装 `fonts-noto-cjk` / `fonts-wqy-zenhei`，或用 `visualize_graph.py --font '字体名'`；脚本已自动探测常见 CJK 字体 |

---

## 11. 按时间清理 LanceDB 向量

**目的**：按 `documents.parquet` 的 `creation_date`（见 §6）弱化或删除过旧文档的**向量行**，减轻旧文在 `basic` 检索中被命中。默认 **dry-run**；确认后加 `--apply`。

**注意**：只删 LanceDB 中的向量，**不删** parquet / `graph.graphml`；图谱与结构化表不会自动同步裁剪。`creation_date` 为空时默认不删。增量库时 `--output-dir` 指向 `…/delta` 且该目录下需存在 `lancedb/`。

```bash
python purge_stale_vectors.py --output-dir ./output --cutoff-date 2024-06-01
python purge_stale_vectors.py --output-dir ./output --cutoff-date 2024-06-01 --apply
python purge_stale_vectors.py --output-dir ./output --max-age-days 365 --apply
```

也可用 `--cutoff`（ISO8601 UTC）、`GRAPHRAG_PURGE_CUTOFF` 等，详见脚本 `--help`。查看表名：

```bash
python -c "import lancedb; print(lancedb.connect('./output/lancedb').table_names())"
```

若需 parquet、向量、图谱**严格一致**，应整理输入后全量 `graphrag index` 或规范使用 `graphrag update`。

---

## 12. 运行清单 JSON（`record_run_manifest`）

脚本：**`record_run_manifest.py`**。在 **`graphrag index` / `graphrag update`** 或预处理完成后执行，生成 **`run_manifest_<task_id>.json`**，便于 Agent 或流水线追溯：项目根、`input/normalized`、`output`、LanceDB、`settings.yaml` 指纹、`settings.yaml` 中的模型与 **workflows**、主要 **parquet** 绝对路径、**stats 行数**、`output/` 下文件清单（可截断）、`logs/indexing-engine.log` 等。

**依赖**：与 GraphRAG 相同环境；`ingest/requirements.txt` 已含 **pyarrow**，安装后 **`stats` 行数**可正常写入。若仅用无 pyarrow 的解释器，`stats` 可能为 `null`。

```bash
# 主库（默认 project-root 为当前目录，output 为 ./output）
conda activate graphrag311
cd qwen_graphrag_demo
python record_run_manifest.py --pretty

# 指定任务 ID 与业务项目名
export GRAPHRAG_PROJECT_ID=PCG
export GRAPHRAG_MODEL_VERSION=graphrag-3.x-qwen-demo
python record_run_manifest.py --task-id task_20260506_1 --pretty

# 增量融合库（output 指向 delta）
python record_run_manifest.py \
  --output-dir ./output_increment_时间戳/运行批次/delta \
  --task-id inc_20260506_1 \
  --pretty

# 附加自定义字段（JSON 对象）
python record_run_manifest.py --extra-json '{"preprocess":"python ingest/convert_to_graphrag_input.py ..."}'
```

常用参数：`--no-success`（标记失败）、`--stdout-log` / `--stderr-log`（若你对 `graphrag index` 做了重定向）、`--out-json ./manifests/foo.json`、`--max-output-files`（控制 `output_scan.files` 条数）。

---

## 附录 · 命令速查

```bash
conda activate graphrag311
cd qwen_graphrag_demo
pip install -r ingest/requirements.txt

# 全量
python ingest/convert_to_graphrag_input.py --source-dir ./data --target-dir ./input/normalized --enable-ocr --enable-vision
graphrag index --skip-validation   # 含义见 §5；首次建库可改为 graphrag index 做自检
graphrag query "你的问题" --method basic
python record_run_manifest.py --pretty   # 生成 run_manifest_*.json，见 §12

# 增量
python incremental_update.py --source-dir ./data_increment --run-update --skip-validation
graphrag query "你的问题" --method basic -d ./output_increment_时间戳/运行批次时间戳/delta

# 图谱：Neo4j（容器已创建；重启机器或容器退出后要先 start）
docker start graphrag-neo4j
docker exec -it graphrag-neo4j bash   # 可选：进容器调试；导入脚本仍在宿主机跑
pip install neo4j pyarrow
export NEO4J_PASSWORD='你的Neo4j密码'
python export_to_neo4j.py --output-dir ./output --clear

# 图谱：静态 / Pyvis（中文异常时加 --font，见 §9）
python visualize_graph.py --graph ./output/graph.graphml --topk 50 --show-edge-weight --out ./graph_preview.png
```

---

细节以 `settings.yaml` 为准；完整配置项见 [GraphRAG 配置文档](https://microsoft.github.io/graphrag/config/yaml/)。
