# workspace 一键启动说明

> **脚本路径**：`workspace/scripts/start_all.sh`、`workspace/scripts/stop_all.sh`

## 启动什么

按依赖顺序启动 / 检查：

| 顺序 | 组件 | 端口 / 地址 | 说明 |
|------|------|-------------|------|
| 1 | PostgreSQL（Docker `ltt-craft-pg`） | `127.0.0.1:5434` / `ltt_craft` | 本机 Docker 启动 |
| 2 | **MinIO（远程）** | **`http://111.228.12.207:9000`** | **不启动容器**；脚本做 `/minio/health/live` 自检 |
| 3 | vLLM Qwen3-VL | **8001** | GPU |
| 4 | vLLM Qwen3-Embedding | **8002** | GPU |
| 5 | vLLM Qwen3-Reranker（可选） | **8003** | GPU |
| 6 | GraphRAG 索引服务 | **8090** | |
| 7 | base_Platform 后端 | **18000** | 读 `base_Platform/.env` 含 `MINIO_*` |
| 8 | Vite 前端（HTTPS） | **5173** | |

日志与 PID：`workspace/.runtime/logs/`、`workspace/.runtime/pids/`。

## MinIO 配置

远程 MinIO 凭证写在 **`base_Platform/.env`**（与 `backend/app.py` 一致）：

```env
MINIO_ENDPOINT=http://111.228.12.207:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=Minio@123456
```

启动脚本会在拉起后端前 **curl 健康检查**；不可达时默认 **中止启动**（避免 upload/staging 静默失败）。

## 用法

```bash
cd /mnt/dockerContainerSave/memory/ltt/workspace
./scripts/start_all.sh
```

**常用环境变量**：

```bash
# vLLM 已在跑（避免 GPU 重复占用 / OOM）
START_SKIP_VLLM=1 ./scripts/start_all.sh

# 只要后端与服务，不要前端
START_SKIP_FRONTEND=1 ./scripts/start_all.sh

# 不启 Docker PG（已手动 up 时）
START_SKIP_DOCKER=1 ./scripts/start_all.sh

# 跳过 MinIO 连通检查（离线开发，不推荐）
START_SKIP_MINIO_CHECK=1 ./scripts/start_all.sh

# MinIO 不可达仍继续启动（仅告警）
MINIO_CHECK_STRICT=0 ./scripts/start_all.sh

# 覆盖远程 MinIO 地址
MINIO_ENDPOINT=http://111.228.12.207:9000 ./scripts/start_all.sh

# vLLM 目录非默认路径
VLLM_ROOT=/path/to/vllm-big-model ./scripts/start_all.sh
```

**停止**（默认保留 vLLM 与 PostgreSQL；MinIO 为远程，无需停止）：

```bash
./scripts/stop_all.sh
STOP_VLLM=1 ./scripts/stop_all.sh
STOP_DOCKER=1 ./scripts/stop_all.sh
```

## 说明

- **MinIO 不在 `docker-compose.ltt-pg.yml` 里**；`ltt-craft-pg` 只包含 PostgreSQL。
- 若 **8001/8002 已 HTTP 200**，脚本**不会**再执行 `vllm-big-model/start_all.sh`（避免显存冲突）。
- GraphRAG 8090 的环境与 `base_Platform/scripts/start_graphrag_8090.sh` 一致（`qwen_graphrag_demo/.env` + settings）。
- 前端使用 `frontend/vite.config.ts` 中的 **HTTPS** 与 `/api` 代理到 18000。
- 首次前端需已 `npm install`（`base_Platform/frontend/node_modules`）。
- 修改 `base_Platform/.env` 后若 18000 已在跑，需 `./scripts/stop_all.sh` 后再 `start_all.sh` 或单独重启后端。

## 相关文档

- [`base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md`](../base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md)
- [`base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md`](../base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md)
