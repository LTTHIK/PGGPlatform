# PGG Platform（LTT Workspace）

知识分析平台：文件上传 → MinIO → GraphRAG 索引（Phase1）→ 后续 CRR / IR / Wiki。

## 目录

| 路径 | 说明 |
|------|------|
| `base_Platform/` | FastAPI 后端、前端、8090 子服务、数据库脚本 |
| `graphrag/` | GraphRAG 引擎（含 `profiling.py` 本地补丁）与 `qwen_graphrag_demo` 配置 |
| `scripts/` | 全栈一键启动 `start_all.sh` |
| `docs/` | 跨工程文档（总册等） |

## 快速启动

```bash
cd workspace
START_SKIP_VLLM=1 ./scripts/start_all.sh   # vLLM 已运行时
```

详见 [`base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md`](base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md)。

## 环境准备（首次）

1. 复制 `base_Platform/.env.example` → `base_Platform/.env`
2. 创建 Python 虚拟环境并安装依赖（见各子目录 `requirements.txt`）
3. `docker compose -f base_Platform/docker-compose.ltt-pg.yml up -d`
4. 本机需 vLLM :8001/:8002（GraphRAG 抽图与向量）

## 文档索引

- 总册：[`docs/PROJECT_FULL_GUIDE_ZH.md`](docs/PROJECT_FULL_GUIDE_ZH.md)
- 验收：[`base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md`](base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md)

## 上游说明

- `graphrag/` 基于 [microsoft/graphrag](https://github.com/microsoft/graphrag)，含本地修改（`profiling.py` 等）
- `hermes-agent/`（若存在）来自 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)，与本平台 Phase1 无硬依赖

## 未纳入 Git 的大文件

见 [`.gitignore`](.gitignore)：`paraformer_model/`、虚拟环境、`graphrag_runs/`、`.env` 等需在部署机器上单独准备。
