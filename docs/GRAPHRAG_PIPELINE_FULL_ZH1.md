# GraphRAG 在本项目中的全流程说明（索引 + 查询）

本文档面向本仓库内 **`workspace/graphrag`**（Microsoft GraphRAG 实现）及演示配置 **`qwen_graphrag_demo`**，说明：**输入是什么、中间经过哪些处理、各步如何用模型/算法完成、最终产出什么**，以及 **查询阶段如何消费索引**。

> 说明：GraphRAG 不是「单一神经网络」，而是一套 **索引流水线（多工作流）+ 查询引擎（检索与 LLM 组装）**。其中大量步骤由 **大语言模型（LLM）** 完成抽取与摘要，图结构与社区发现由 **图算法** 完成，向量检索由 **嵌入模型 + 向量库** 完成。

---

## 1. 概念：GraphRAG 在解决什么问题

- **基线 RAG**：多数做法用向量相似度在文本块上检索，再拼进提示词。对「需要跨多段文字推理、或要对整库做宏观总结」类问题容易偏弱。
- **GraphRAG**：先把语料建成 **实体—关系知识图**，再做 **层次化社区划分** 与 **社区报告**，查询时既可走 **局部（实体-centric）** 路径，也可走 **全局（社区报告 map-reduce）** 路径，从而兼顾「细粒度事实」与「整体叙事/主题」。

---

## 2. 两大阶段总览

| 阶段 | 目的 | 主要输入 | 主要输出 |
|------|------|----------|----------|
| **索引（Index）** | 把原始文档变成可检索的知识模型 | 文本文件 / CSV / JSON 或自定义 DataFrame | Parquet 表、可选 GraphML、LanceDB 向量索引等 |
| **查询（Query）** | 针对用户问题检索上下文并生成答案 | 已完成索引 + 用户 `query` 字符串 | 自然语言回答 + 可追溯的上下文（实体、文本块、社区报告等） |

---

## 3. 索引阶段：输入（Input）

### 3.1 GraphRAG 原生产物：`documents` DataFrame

所有格式最终都会变成一张 **`documents` 表**（内存中为 pandas DataFrame），列语义如下（与官方 `docs/index/inputs.md` 一致）：

| 列名 | 含义 |
|------|------|
| `id` | 文档 ID；无显式 id 时常由正文哈希生成，保证跨次运行稳定 |
| `text` | 文档全文 |
| `title` | 标题；纯文本文件默认为文件名 |
| `creation_date` | ISO8601 创建时间（来自文件系统） |
| `metadata` | 可选字典；可在分块时前置到每个 TextUnit |

支持的常见文件类型：**`.txt`、`.csv`、`.json`** 等；也可通过 API **自带 DataFrame** 跳过文件加载。

### 3.2 本仓库演示：`qwen_graphrag_demo` 的额外前置

目录：`workspace/graphrag/qwen_graphrag_demo/ingest/convert_to_graphrag_input.py`

在正式进入 GraphRAG 之前，该脚本可把 **PDF / Office / 图片 / HTML / 表格** 等转为 **`input/.../normalized/*.txt`**，再由 `settings.yaml` 中的：

```yaml
input:
  type: text
  file_pattern: ".*/normalized/.*\\.txt"
```

限定只索引规范化后的文本。也就是说，**演示工程的「真实原始输入」比 GraphRAG 默认更丰富**，但 **进入管线时仍是纯文本文档流**。

---

## 4. 索引阶段：标准管线（Standard）工作流顺序

默认注册顺序在 `packages/graphrag/graphrag/index/workflows/factory.py` 中定义。标准方法为：

1. `load_input_documents` — 读入并解析为 `documents`
2. `create_base_text_units` — 分块得到 TextUnit
3. `create_final_documents` — 文档与 TextUnit 关联，写出 Documents 表
4. `extract_graph` — **LLM** 抽取实体与关系，再 **LLM** 汇总描述
5. `extract_covariates` — （可选）**LLM** 抽取声明/主张 → Covariates；**默认常关闭**
6. `finalize_graph` — 固化图相关表结构
7. `create_communities` — **Leiden** 层次社区发现
8. `create_final_text_units` — 将实体、关系等关联回 TextUnit
9. `create_community_reports` — **LLM** 为每个社区写报告并再摘要
10. `generate_text_embeddings` — **嵌入模型** 写向量（默认进 LanceDB）

### 4.1 本演示 `settings.yaml` 与默认标准的差异

`qwen_graphrag_demo/settings.yaml` 显式 **`workflows`** 列表为：

- 含：`load_input_documents` → `create_base_text_units` → `create_final_documents` → `extract_graph` → `finalize_graph` → `create_communities` → `create_community_reports` → `create_final_text_units` → `generate_text_embeddings`
- **未包含**：`extract_covariates`（与其中 `extract_claims.enabled: false` 一致，即 **不做声明抽取**）

因此本演示索引路径是 **「实体 + 关系 + 社区 + 社区报告 + 向量」**，**没有 Covariates/Claims 产物**。

---

## 5. 索引阶段：各步骤在做什么（处理逻辑）

### 5.1 `create_base_text_units`（TextUnit 构造）

- **输入**：`documents` 每行的 `text`
- **处理**：按配置的 **token 窗口** 切分（演示：`chunking.size: 1200`, `overlap: 100`, `encoding_model: o200k_base`）
- **输出**：**TextUnit** 行表；每个单元是后续 **图抽取、引用溯源** 的最小分析单位
- **意义**：LLM 上下文有限，且细粒度引用需要「块 ID → 原文片段」映射

可选：`prepend_metadata` 可把文档级 metadata 复制到每个 chunk，避免「只有第一个 chunk 有标题/作者」之类信息缺失（见官方 `docs/index/inputs.md`）。

### 5.2 `create_final_documents`（文档层输出）

- **输入**：文档 + 其下属 TextUnit ID 列表
- **输出**：**`documents.parquet`**（知识模型中的 Document）
- **意义**：平台侧做溯源、展示「某答案来自哪些文件」时常用

### 5.3 `extract_graph`（图抽取 + 描述汇总）— **核心 LLM 步骤**

实现要点：`packages/graphrag/graphrag/index/workflows/extract_graph.py`、`.../graph_extractor.py`。

对每个 TextUnit：

1. **抽取（Extraction）**  
   - 将 TextUnit 全文与 **实体类型列表**（演示：`organization, person, geo, event`）填入提示词（`prompts/extract_graph.txt`）  
   - 调用 **补全模型**（演示：通过 LiteLLM 走智谱 OpenAI 兼容接口）  
   - 模型输出按约定分隔符解析为 **实体表**（名称、类型、描述…）与 **关系表**（源、目标、描述…）  
   - **Gleaning**：可配置多轮追问以「捞回」遗漏实体（演示：`max_gleanings: 1`）

2. **跨单元合并**  
   - 同一 **title + type** 的实体合并，描述先 **累积成列表**  
   - 同一 **source + target** 的关系同理

3. **汇总（Summarization）**  
   - 再调用 LLM，将同一实体/关系的多条描述 **压缩为一条**（`summarize_descriptions`，`max_length` 等限制长度）

**输出**：`entities`、`relationships`（及中间 raw 表，视配置落盘）；这是整张知识图的 **节点与边**。

若抽取结果为空，管线会 **直接报错退出**（防止后续空图）。

### 5.4 `extract_covariates` / Claims（本演示关闭）

- **意图**：从 TextUnit 中抽 **可检验的主张**（带主体/客体、时间、真伪评估等），服务特定分析场景  
- **本演示**：`extract_claims.enabled: false` 且工作流未包含该步 → **跳过**

### 5.5 `finalize_graph`（图定稿）

- 将实体、关系等整理为下游社区发现与查询所需的 **规范化表**（具体字段见 `docs/index/outputs.md`）

### 5.6 `create_communities`（层次社区发现）

- **输入**：实体—关系图  
- **处理**：**分层 Leiden** 聚类，直到社区规模等约束满足（`cluster_graph.max_cluster_size` 等可配）  
- **输出**：**`communities.parquet`** — 树状层级：`parent` / `children` / `level` / 成员实体与关系、关联 TextUnit 等

这一步 **不调用 LLM**，是图算法。

### 5.7 `create_community_reports`（社区报告）— **又一核心 LLM 步骤**

- **输入**：每个社区子图内的实体/关系描述（及可选文本线索）  
- **处理**：用 `community_report_graph.txt` 等提示词，让 LLM 生成 **标题、摘要、全文、findings、rank** 等（见 `outputs.md` 中 `community_reports`  schema）  
- **输出**：**`community_reports.parquet`** — 供 **Global Search** 做「整张数据集级别」推理的主要素材

### 5.8 `create_final_text_units`（TextUnit 回填）

- 把 **出现在该块中的实体、关系、（可选）covariate** 的 ID 关联到 TextUnit  
- **输出**：**`text_units.parquet`** — **Local Search** 与 **Basic RAG** 拉原文块时依赖

### 5.9 `generate_text_embeddings`（向量索引）

- **嵌入对象**（默认常见）：TextUnit 全文、实体描述、社区报告全文等（具体子集由配置 `embed_text`/`vector_store` 决定；演示中 `embed_text.names: [text_unit_text]` 表示至少嵌入文本块）  
- **存储**：演示使用 **`lancedb`**，`db_uri: output/lancedb`，维度与嵌入模型一致（`vector_size: 2048`）  
- **作用**：查询阶段 **向量检索**（局部搜索、基础 RAG、DRIFT 等）从这里取近邻

---

## 6. FastGraphRAG（快速模式）与本项目关系

工厂中还注册了 `IndexingMethod.Fast` 管线：`extract_graph_nlp` 用 **NLTK/spaCy 等名词短语与共现** 代替 LLM 抽取；社区报告可走 `create_community_reports_text`。**本演示 `settings.yaml` 未选用 Fast**，若启用可显著降成本，但图质量依赖 NLP 与语料语言。

---

## 7. 索引阶段：输出物（你「得到了什么」）

默认以 **Parquet** 为主（见 `docs/index/outputs.md`），常见包括：

| 产物 | 内容概要 |
|------|----------|
| `documents.parquet` | 原始文档 + 下属 `text_unit_ids` |
| `text_units.parquet` | 分块文本 + 关联实体/关系 ID |
| `entities.parquet` | 汇总后的实体与描述、频次、度数等 |
| `relationships.parquet` | 加权边、描述、共现文本块等 |
| `communities.parquet` | 层次社区结构 |
| `community_reports.parquet` | 每层社区的 LLM 报告 |
| `covariates.parquet` | 仅当声明抽取开启时 |
| `output/lancedb/` | 向量表，供检索 |
| GraphML（可选） | `snapshots.graphml: true` 时导出图结构便于可视化 |

这些文件即 **知识模型（Knowledge Model）** 的物化形式。

---

## 8. 查询阶段：输入与输出

实现入口：`packages/graphrag/graphrag/api/query.py`。

### 8.1 共同输入

- **`GraphRagConfig`**（由 `settings.yaml` 与环境变量解析）  
- 从索引目录加载的 DataFrame：**`entities`、`relationships`、`communities`、`community_reports`、`text_units`**（及可选 **`covariates`**）  
- 用户 **`query`** 字符串

### 8.2 Global Search（全局搜索）

- **适合**：跨文档、宏观总结类问题（例如「这批资料里反复出现的主题与矛盾是什么？」）  
- **机制（概念）**：对 **社区报告** 做 **Map-Reduce**：多段报告分别与问题对齐（map），再合并为最终答复（reduce）；可配置动态社区选择、社区层级上限等  
- **主要消耗**：LLM 调用次数与上下文体量通常 **高于** 局部分支  
- **输出**：`str` 回答 + `context_data`（回调收集的表格化上下文，便于 UI 或审计）

### 8.3 Local Search（局部搜索）

- **适合**：指向具体实体/细节的问题（例如「某合同中甲方义务第三条是什么？」）  
- **机制（概念）**：  
  1. 用 **查询与实体描述的向量相似度** 找 **相关实体**  
  2. 沿图扩展：**相关关系、相邻实体、关联 TextUnit、相关社区报告、（若有）covariates**  
  3. 在 **上下文预算** 内排序截断，拼成提示词，由 LLM 生成答案  
- **输出**：同样是回答 + 可追溯上下文

官方数据流示意见 `docs/query/local_search.md`（Mermaid 图）。

### 8.4 其他查询模式（库内可选）

- **Basic Search**：主要在 **TextUnit 向量** 上 Top-K，再摘要 — 便于与基线 RAG 对比  
- **DRIFT Search**：在局部路径中加强社区信息的利用，扩展检索广度  
- **Question Generation**：基于全局/局部信号生成后续问题列表  

演示工程在 `settings.yaml` 中为各模式配置了 **独立 system prompt 文件**（`prompts/local_search_system_prompt.txt` 等）。

---

## 9. 「模型」在各处的分工（总结表）

| 环节 | 是否用 LLM | 是否用嵌入模型 | 是否用图算法 |
|------|------------|----------------|--------------|
| 分块 | 否 | 否 | 否 |
| 实体/关系抽取与描述汇总 | **是** | 否 | 否 |
| 声明抽取（可选） | **是** | 否 | 否 |
| 社区发现 | 否 | 否 | **是（Leiden）** |
| 社区报告 | **是** | 否 | 否 |
| 写入向量库 | 否 | **是** | 否 |
| Global Query | **是** | 间接（报告/实体等已嵌入） | 否 |
| Local Query | **是** | **是** | 否（用已构图扩展） |

---

## 10. 与平台侧（`base_Platform`）的衔接说明

本仓库另含 **`workspace/base_Platform`** 的数据库扩展（如 `model_artifacts`、`graphrag_input_path` 等），用于把 **任务运行目录、manifest、LanceDB 路径** 登记到业务库。那是 **编排与元数据层**；**图与向量的计算过程仍由本节所述 GraphRAG 包完成**。

---

## 11. 推荐阅读顺序（源码与官方文档）

1. 数据流总览：`workspace/graphrag/docs/index/default_dataflow.md`  
2. 输入/输出 schema：`workspace/graphrag/docs/index/inputs.md`、`outputs.md`  
3. 管线注册：`workspace/graphrag/packages/graphrag/graphrag/index/workflows/factory.py`  
4. 图抽取：`.../index/workflows/extract_graph.py`、`.../operations/extract_graph/graph_extractor.py`  
5. 查询 API：`.../graphrag/api/query.py`  
6. 本演示配置：`workspace/graphrag/qwen_graphrag_demo/settings.yaml`  
7. 多格式入库：`workspace/graphrag/qwen_graphrag_demo/ingest/convert_to_graphrag_input.py`  

---

*文档生成依据本仓库内 GraphRAG 包与 `qwen_graphrag_demo` 当前结构整理；若你升级 GraphRAG 版本或改写 `workflows`，请以 `factory.py` 与项目内 `settings.yaml` 为准。*
