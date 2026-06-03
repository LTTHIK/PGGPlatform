# Minimal Craft（Web 全功能版）

当前工程已按 `realtime_gui.py` 的能力拆成前后端：
- 前端：`frontend/`（TypeScript + Vite）
- 后端：`backend/`（Python + FastAPI + WebSocket）
- 模型：`paraformer_model/`

## 已覆盖功能
- 实时语音转写（WebSocket 推送、RMS 音量显示、停止后保存录音）
- 口语稿 -> 书面稿（DeepSeek）
- 书面稿 -> 会议纪要（DeepSeek）
- 四项上传到 MinIO（录音、口语稿、书面稿、会议纪要）
- MinIO 树浏览 + 文件预览
- 基于当前文件内容的对话加工 + 会话归档

## 启动方式（Windows PowerShell）

### 1) 启动后端
```powershell
cd E:\ubuntu\wenet-asr\minimal_craft
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 18000 --reload
```

### 2) 启动前端
```powershell
cd E:\ubuntu\wenet-asr\minimal_craft\frontend
npm install
npm run dev
```

默认访问：`http://localhost:5173`

Vite 代理：
- `/api/* -> http://127.0.0.1:18000`
- `/ws/* -> ws://127.0.0.1:18000`

## 主要接口
- `GET /api/health`
- `POST /api/transcribe`
- `WS /ws/asr`
- `POST /api/polish`
- `POST /api/minutes`
- `POST /api/chat`
- `GET /api/minio/tree`
- `GET /api/minio/object`
- `POST /api/upload/recording`
- `POST /api/upload/text`
- `POST /api/upload/all`

## 兼容性
- 原 `realtime_gui.py`、`minimal_streaming.py`、`check_prereqs.py` 保留不变。
