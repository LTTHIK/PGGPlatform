# PGGPlatform

面向企业文档与知识资产的智能分析平台。项目将文件存储、任务编排、GraphRAG 索引、模型服务与可视化管理串成一条可追踪的处理链路，当前重点是“文档上传 → 对象存储 → 异步索引 → 任务状态与产物管理”。

## 项目能力

- 统一上传与对象存储：通过 FastAPI 接收文件并写入 MinIO。
- 异步任务编排：记录索引任务、阶段状态、日志与错误信息，便于定位长任务问题。
- GraphRAG 知识建模：抽取实体、关系、社区与摘要，生成后续检索和知识展示所需产物。
- 模型服务解耦：通过兼容接口连接本地大模型与向量模型，便于替换推理后端。
- 前后端协作：前端负责文件和任务管理，后端提供 REST/WebSocket 接口与数据库持久化。

## 技术架构

```text
Web 前端（React + Vite）
        │ REST / WebSocket
        ▼
平台后端（FastAPI）── PostgreSQL
        │
        ├── MinIO（原始文件与索引产物）
        ├── GraphRAG（实体、关系、社区与报告）
        └── 模型服务（LLM / Embedding）
```

## 目录说明

| 路径 | 说明 |
| --- | --- |
| `base_Platform/` | 平台后端、前端、数据库脚本、部署与验收文档 |
| `graphrag/` | GraphRAG 引擎、本地适配与示例配置 |
| `scripts/` | 全栈启动和运维脚本 |
| `docs/` | 跨模块设计与项目说明 |
| `hermes-agent/` | 独立上游实验代码，当前不是平台主链路的必需组件 |

## 快速开始

1. 复制配置模板并填写本机参数：

   ```bash
   cp base_Platform/.env.example base_Platform/.env
   ```

2. 按各模块的 `requirements.txt` 安装 Python 依赖，并安装前端依赖。
3. 启动 PostgreSQL 与 MinIO：

   ```bash
   docker compose -f base_Platform/docker-compose.ltt-pg.yml up -d
   ```

4. 启动全栈服务；已有模型服务时可跳过本地 vLLM 启动：

   ```bash
   START_SKIP_VLLM=1 ./scripts/start_all.sh
   ```

完整步骤见 [`base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md`](base_Platform/docs/PHASE1_STARTUP_GUIDE_ZH.md)，验收方法见 [`base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md`](base_Platform/docs/PHASE1_ACCEPTANCE_TEST_ZH.md)。

## 配置与安全

- `.env`、数据库口令、MinIO 密钥和 JWT 密钥只保存在部署环境，不提交到 Git。
- 前端 HTTPS 为可选能力。需要 HTTPS 时，请在 `base_Platform/frontend/ssl/` 本地生成 `vite-localhost.key` 与 `vite-localhost.crt`；文件缺失时开发服务器自动使用 HTTP。
- 日志、PID、索引结果、上传文件、模型权重和本地证书均由 `.gitignore` 排除。
- 已经公开过的真实凭据应立即在对应服务端轮换；仅从当前代码删除不能使旧提交中的内容失效。

## 当前边界

当前仓库已经覆盖文件接入、索引任务和产物管理主链路；面向最终用户的问答检索、CRR/IR 与 Wiki 体验仍在持续完善。README 只描述已能从仓库验证的能力，不把规划功能标记为已完成。

## 上游与本地改造

- `graphrag/` 基于 [microsoft/graphrag](https://github.com/microsoft/graphrag)，包含模型接口与运行分析等本地适配。
- `hermes-agent/` 来源于 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)，其示例配置不代表本平台生产配置。
