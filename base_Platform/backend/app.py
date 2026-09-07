from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import psycopg
import requests
import soundfile as sf
from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from .auth_users import (
    AdminCreateUserRequest,
    AdminPatchUserRequest,
    LoginRequest,
    RegisterRequest,
    UserStore,
    configure_auth,
    create_access_token,
    require_admin,
    require_user,
    resolve_jwt_secret,
    user_from_websocket_token,
)
from .transcriber import Transcriber

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEFAULT_MODEL_DIR = (PROJECT_DIR / "paraformer_model").resolve()
RECORDINGS_DIR = (PROJECT_DIR / "recordings").resolve()


def resolve_model_dir() -> Path:
    raw_model_dir = (os.getenv("MODEL_DIR") or "").strip()
    candidates: list[Path] = []
    if raw_model_dir:
        raw_path = Path(raw_model_dir).expanduser()
        if raw_path.is_absolute():
            candidates.append(raw_path.resolve())
        else:
            candidates.append((PROJECT_DIR / raw_path).resolve())
            candidates.append((Path.cwd() / raw_path).resolve())
    candidates.extend(
        [
            DEFAULT_MODEL_DIR,
            (Path.cwd() / "paraformer_model").resolve(),
        ]
    )
    for path in candidates:
        if path.exists():
            if raw_model_dir and path != candidates[0]:
                print(
                    f"[ASR] MODEL_DIR 无效，已回退到可用模型目录: {path}",
                    flush=True,
                )
            return path
    if raw_model_dir:
        return candidates[0]
    return DEFAULT_MODEL_DIR


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="utf-16")
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].rstrip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


load_env_file(PROJECT_DIR / ".env")

MODEL_DIR = resolve_model_dir()
DEVICE = os.getenv("MODEL_DEVICE", "cpu").split("#", 1)[0].strip() or "cpu"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "80"))

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_VERIFY_SSL = env_flag("DEEPSEEK_VERIFY_SSL", True)
DEEPSEEK_TIMEOUT_S = int(os.getenv("DEEPSEEK_TIMEOUT_S", "120"))

MINIO_ENDPOINT = (os.getenv("MINIO_ENDPOINT") or "").strip()
MINIO_ACCESS_KEY = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
MINIO_SECRET_KEY = (os.getenv("MINIO_SECRET_KEY") or "").strip()

if not MINIO_ENDPOINT or not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    raise RuntimeError("MINIO_ENDPOINT, MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be configured")

DEFAULT_SAMPLE_RATE = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
MAX_RECORDING_BUFFER_S = float(os.getenv("MAX_RECORDING_BUFFER_S", "180"))
FILE_INDEX_DATABASE_URL = (os.getenv("FILE_INDEX_DATABASE_URL") or "").strip()


@dataclass
class StreamConfig:
    sample_rate: int = 16000
    voice_threshold: float = 0.001
    silence_ms: int = 800
    min_utter_ms: int = 300
    emit_ms: int = 1800
    max_utter_s: float = 8.0


@dataclass
class StreamSession:
    session_id: str
    cfg: StreamConfig
    utter_chunks: list[np.ndarray] = field(default_factory=list)
    full_chunks: list[np.ndarray] = field(default_factory=list)
    full_samples: int = 0
    full_buffer_truncated: bool = False
    spoken_samples: int = 0
    trailing_silence_samples: int = 0
    last_recording_path: str | None = None


class DeepSeekClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 120,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.verify_ssl = verify_ssl

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not self.api_key.strip():
            raise ValueError("DeepSeek API key is empty")
        endpoint = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "temperature": 0.2, "messages": messages}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        response = requests.post(
            endpoint,
            data=json.dumps(payload),
            headers=headers,
            timeout=self.timeout_s,
            verify=self.verify_ssl,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"DeepSeek API error {response.status_code}: {response.text[:240]}")
        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek returned empty choices")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError("DeepSeek returned empty content")
        return str(content).strip()


class MinioClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str) -> None:
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.s3.head_bucket(Bucket=bucket)
            return
        except ClientError:
            pass
        self.s3.create_bucket(Bucket=bucket)

    def list_buckets(self) -> list[str]:
        body = self.s3.list_buckets()
        return [b.get("Name", "") for b in body.get("Buckets", []) if b.get("Name")]

    def list_objects(self, bucket: str) -> list[str]:
        keys: list[str] = []
        continuation = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": bucket, "MaxKeys": 1000}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = self.s3.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = item.get("Key")
                if key:
                    keys.append(key)
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
        return keys

    def get_object_bytes(self, bucket: str, key: str) -> bytes:
        response = self.s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def upload_file(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        self.s3.upload_file(
            Filename=file_path,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )

    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


class FileRecordStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("FILE_INDEX_DATABASE_URL is required for PostgreSQL file index store")
        self._lock = threading.Lock()
        self._conn = psycopg.connect(database_url, row_factory=dict_row)
        self._conn.autocommit = False
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_records (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT,
                    bucket_name TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content_type TEXT,
                    byte_length BIGINT,
                    local_path TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(bucket_name, object_key)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_records_session ON file_records(session_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_records_kind ON file_records(kind)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_records_created ON file_records(created_at DESC)"
            )
            self._conn.commit()

    def upsert_record(
        self,
        *,
        session_id: str | None,
        bucket_name: str,
        object_key: str,
        kind: str,
        content_type: str,
        byte_length: int | None,
        local_path: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO file_records (
                    session_id, bucket_name, object_key, kind, content_type, byte_length, local_path
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(bucket_name, object_key) DO UPDATE SET
                    session_id = excluded.session_id,
                    kind = excluded.kind,
                    content_type = excluded.content_type,
                    byte_length = excluded.byte_length,
                    local_path = excluded.local_path,
                    updated_at = now()
                """,
                (session_id, bucket_name, object_key, kind, content_type, byte_length, local_path),
            )
            self._conn.commit()

    def list_records(
        self,
        *,
        session_id: str | None = None,
        bucket_name: str | None = None,
        kind: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if bucket_name:
            clauses.append("bucket_name = %s")
            params.append(bucket_name)
        if kind:
            clauses.append("kind = %s")
            params.append(kind)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT id, session_id, bucket_name, object_key, kind, content_type, byte_length, local_path, created_at, updated_at "
            f"FROM file_records {where_sql} ORDER BY id DESC LIMIT %s"
        )
        params.append(max(1, min(limit, 1000)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


class StreamManager:
    def __init__(self, transcriber: Transcriber) -> None:
        self.transcriber = transcriber
        self.sessions: dict[str, StreamSession] = {}
        self._lock = threading.Lock()

    def create_session(self, cfg_data: dict[str, Any] | None = None) -> StreamSession:
        cfg_data = cfg_data or {}
        cfg = StreamConfig(
            sample_rate=int(cfg_data.get("sample_rate", DEFAULT_SAMPLE_RATE)),
            voice_threshold=float(cfg_data.get("voice_threshold", 0.001)),
            silence_ms=int(cfg_data.get("silence_ms", 800)),
            min_utter_ms=int(cfg_data.get("min_utter_ms", 300)),
            emit_ms=int(cfg_data.get("emit_ms", 1800)),
            max_utter_s=float(cfg_data.get("max_utter_s", 8.0)),
        )
        session = StreamSession(session_id=uuid.uuid4().hex, cfg=cfg)
        with self._lock:
            self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> StreamSession | None:
        with self._lock:
            return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self.sessions.pop(session_id, None)

    def process_audio(self, session: StreamSession, chunk: np.ndarray) -> tuple[float, list[str]]:
        cfg = session.cfg
        max_full_samples = max(1, int(cfg.sample_rate * MAX_RECORDING_BUFFER_S))
        if session.full_samples < max_full_samples:
            remain = max_full_samples - session.full_samples
            if len(chunk) <= remain:
                session.full_chunks.append(chunk)
                session.full_samples += len(chunk)
            else:
                session.full_chunks.append(chunk[:remain].copy())
                session.full_samples += remain
                session.full_buffer_truncated = True
        else:
            session.full_buffer_truncated = True
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        voiced = rms >= cfg.voice_threshold or (
            bool(session.utter_chunks) and rms >= cfg.voice_threshold * 0.5
        )

        if voiced:
            session.utter_chunks.append(chunk)
            session.spoken_samples += len(chunk)
            session.trailing_silence_samples = 0
        elif session.utter_chunks:
            session.utter_chunks.append(chunk)
            session.trailing_silence_samples += len(chunk)

        silence_samples_target = int(cfg.sample_rate * cfg.silence_ms / 1000)
        min_samples = int(cfg.sample_rate * cfg.min_utter_ms / 1000)
        emit_samples_target = int(cfg.sample_rate * cfg.emit_ms / 1000)
        max_samples = int(cfg.sample_rate * cfg.max_utter_s)

        should_flush = False
        if session.utter_chunks and session.trailing_silence_samples >= silence_samples_target:
            should_flush = True
        if session.spoken_samples >= emit_samples_target:
            should_flush = True
        if session.spoken_samples >= max_samples:
            should_flush = True

        results: list[str] = []
        if should_flush:
            text = self._flush_utterance(session, min_samples=min_samples)
            if text:
                results.append(text)
        return rms, results

    def flush_remaining(self, session: StreamSession) -> list[str]:
        min_samples = int(session.cfg.sample_rate * session.cfg.min_utter_ms / 1000)
        text = self._flush_utterance(session, min_samples=min_samples)
        return [text] if text else []

    def _flush_utterance(self, session: StreamSession, min_samples: int) -> str:
        if session.spoken_samples < min_samples or not session.utter_chunks:
            session.utter_chunks = []
            session.spoken_samples = 0
            session.trailing_silence_samples = 0
            return ""
        audio = np.concatenate(session.utter_chunks, axis=0)
        session.utter_chunks = []
        session.spoken_samples = 0
        session.trailing_silence_samples = 0
        return self.transcriber.transcribe_array(audio, sample_rate=session.cfg.sample_rate).strip()

    def save_full_recording(self, session: StreamSession) -> str | None:
        if not session.full_chunks:
            return None
        audio = np.concatenate(session.full_chunks, axis=0)
        if audio.size == 0:
            return None
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        file_name = f"recording_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
        out_path = RECORDINGS_DIR / file_name
        sf.write(str(out_path), audio, session.cfg.sample_rate)
        session.last_recording_path = str(out_path)
        if session.full_buffer_truncated:
            print(
                f"[WS] recording buffer truncated at {MAX_RECORDING_BUFFER_S:.1f}s; saved partial audio to {out_path}",
                flush=True,
            )
        return session.last_recording_path


class PolishRequest(BaseModel):
    text: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]


class UploadTextRequest(BaseModel):
    kind: str
    content: str


class UploadRecordingRequest(BaseModel):
    session_id: str


class ClientUploadAudioResponse(BaseModel):
    bucket: str
    key: str
    bytes: int
    client_recording_id: str | None = None


class UploadAllRequest(BaseModel):
    session_id: str | None = None
    raw: str | None = None
    formal: str | None = None
    minutes: str | None = None


class LlmConfigRequest(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""


app = FastAPI(title="Minimal Craft ASR Web API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

transcriber = Transcriber(model_dir=MODEL_DIR, device=DEVICE)
stream_manager = StreamManager(transcriber=transcriber)
minio = MinioClient(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
)
file_record_store = FileRecordStore(database_url=FILE_INDEX_DATABASE_URL)
user_store = UserStore(database_url=FILE_INDEX_DATABASE_URL)
configure_auth(user_store, resolve_jwt_secret())
llm_config_lock = threading.Lock()
llm_runtime_config: dict[str, Any] = {
    "base_url": DEEPSEEK_BASE_URL,
    "api_key": DEEPSEEK_API_KEY,
    "model": DEEPSEEK_MODEL,
    "timeout_s": DEEPSEEK_TIMEOUT_S,
    "verify_ssl": DEEPSEEK_VERIFY_SSL,
}
current_bucket: str | None = None
bucket_lock = threading.Lock()


def get_llm_runtime_config() -> dict[str, Any]:
    with llm_config_lock:
        return dict(llm_runtime_config)


def set_llm_runtime_config(req: LlmConfigRequest) -> dict[str, Any]:
    base_url = req.base_url.strip() or "https://api.deepseek.com/v1"
    model = req.model.strip() or "deepseek-chat"
    api_key = req.api_key.strip()
    with llm_config_lock:
        llm_runtime_config["base_url"] = base_url.rstrip("/")
        llm_runtime_config["model"] = model
        llm_runtime_config["api_key"] = api_key
        return dict(llm_runtime_config)


def build_llm_client() -> DeepSeekClient:
    cfg = get_llm_runtime_config()
    return DeepSeekClient(
        base_url=str(cfg.get("base_url") or "https://api.deepseek.com/v1"),
        api_key=str(cfg.get("api_key") or ""),
        model=str(cfg.get("model") or "deepseek-chat"),
        timeout_s=int(cfg.get("timeout_s") or DEEPSEEK_TIMEOUT_S),
        verify_ssl=bool(cfg.get("verify_ssl", DEEPSEEK_VERIFY_SSL)),
    )


def ensure_bucket() -> str:
    global current_bucket
    with bucket_lock:
        if current_bucket:
            return current_bucket
        base = time.strftime("asr-%Y%m%d-%H%M%S")
        bucket = base
        for _ in range(5):
            try:
                minio.ensure_bucket(bucket)
                current_bucket = bucket
                return bucket
            except Exception:
                bucket = f"{base}-{uuid.uuid4().hex[:4]}"
        raise RuntimeError("Failed to create MinIO bucket")


def new_object_key(prefix: str, ext: str) -> str:
    return f"{prefix}/{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"


def decode_preview(data: bytes, key: str) -> str:
    lower = key.lower()
    if lower.endswith((".txt", ".md", ".json", ".csv", ".log")):
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")
    if lower.endswith((".wav", ".mp3", ".flac", ".m4a")):
        return f"Audio file: {key}\nSize: {len(data)} bytes\nPreview does not play audio."
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
        return f"Image file: {key}\nSize: {len(data)} bytes\nPreview does not render image."
    snippet = data[:2000]
    return f"Binary file: {key}\nSize: {len(data)} bytes\nFirst 2000 bytes:\n{snippet!r}"


@app.get("/api/health")
def health() -> dict[str, Any]:
    llm_cfg = get_llm_runtime_config()
    return {
        "status": "ok",
        "model_dir": str(MODEL_DIR),
        "device": DEVICE,
        "model_loaded": transcriber.loaded,
        "deepseek_configured": bool(str(llm_cfg.get("api_key") or "").strip()),
    }


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest) -> dict[str, Any]:
    """开放注册仅创建普通用户，管理员须由管理员在后台指定。"""
    try:
        row = user_store.create_user(username=req.username.strip(), password=req.password, role="user")
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail="该账号已被注册") from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return {"user": row}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest) -> dict[str, Any]:
    row = user_store.authenticate(req.username, req.password)
    if not row:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = create_access_token(
        user_id=int(row["id"]),
        username=str(row["username"]),
        role=str(row["role"]),
    )
    return {"access_token": token, "token_type": "bearer", "user": row}


@app.get("/api/auth/me")
def auth_me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"user": user}


@app.get("/api/admin/users")
def admin_list_users(_admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"items": user_store.list_users()}


@app.post("/api/admin/users")
def admin_create_user(req: AdminCreateUserRequest, _admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        role = req.normalized_role()
        row = user_store.create_user(username=req.username.strip(), password=req.password, role=role)
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail="该账号已存在") from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return {"user": row}


@app.patch("/api/admin/users/{user_id}")
def admin_patch_user(
    user_id: int,
    req: AdminPatchUserRequest,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    try:
        role = req.normalized_role()
        row = user_store.update_user(
            user_id,
            role=role,
            is_active=req.is_active,
            password=req.password,
            actor_id=int(admin["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": row}


@app.get("/api/llm/config")
def get_llm_config(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    cfg = get_llm_runtime_config()
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key": cfg["api_key"],
        "verify_ssl": cfg["verify_ssl"],
    }


@app.post("/api/llm/config")
def update_llm_config(
    req: LlmConfigRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    cfg = set_llm_runtime_config(req)
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key": cfg["api_key"],
        "verify_ssl": cfg["verify_ssl"],
    }


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in {".wav", ".flac", ".aiff", ".aif", ".mp3", ".m4a"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")
    try:
        text = transcriber.transcribe_bytes(data=data, suffix=suffix)
        return {"text": text.strip()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc


@app.websocket("/ws/asr")
async def asr_socket(ws: WebSocket, token: str | None = Query(default=None)) -> None:
    ws_user = user_from_websocket_token(token)
    if ws_user is None:
        await ws.accept()
        await ws.close(code=1008, reason="unauthorized")
        return
    await ws.accept()
    session: StreamSession | None = None
    try:
        while True:
            message = await ws.receive_json()
            msg_type = message.get("type")
            print(f"[WS] received type={msg_type} session={session.session_id if session else 'none'} keys={list(message.keys())}")
            if msg_type == "start":
                if session is not None:
                    await ws.send_json({"type": "status", "text": "session already started"})
                    continue
                session = stream_manager.create_session(message.get("config"))
                print(f"[WS] start session={session.session_id} config={message.get('config')}")
                await ws.send_json(
                    {
                        "type": "started",
                        "session_id": session.session_id,
                        "sample_rate": session.cfg.sample_rate,
                    }
                )
                await ws.send_json({"type": "status", "text": "listening"})
            elif msg_type == "audio":
                if session is None:
                    await ws.send_json({"type": "error", "text": "session not started"})
                    continue
                payload = message.get("pcm16")
                if not payload:
                    continue
                pcm = np.frombuffer(base64.b64decode(payload), dtype=np.int16).astype(np.float32) / 32768.0
                if pcm.size == 0:
                    continue
                print(f"[WS] audio session={session.session_id} pcm16_len={len(payload)} samples={pcm.size}")
                try:
                    rms, texts = stream_manager.process_audio(session, pcm)
                except Exception as exc:
                    print(f"[WS] audio processing failed session={session.session_id} error={exc}")
                    await ws.send_json({"type": "error", "text": f"audio processing failed: {exc}"})
                    continue
                await ws.send_json({"type": "level", "rms": rms})
                for text in texts:
                    await ws.send_json({"type": "transcript", "text": text})
            elif msg_type == "stop":
                if session is None:
                    await ws.send_json({"type": "stopped"})
                    break
                print(f"[WS] stop session={session.session_id}")
                try:
                    for text in stream_manager.flush_remaining(session):
                        await ws.send_json({"type": "transcript", "text": text})
                except Exception as exc:
                    print(f"[WS] flush_remaining failed session={session.session_id} error={exc}")
                    await ws.send_json({"type": "error", "text": f"flush remaining failed: {exc}"})
                recording_path = stream_manager.save_full_recording(session)
                await ws.send_json({"type": "status", "text": "stopped"})
                await ws.send_json(
                    {"type": "stopped", "session_id": session.session_id, "recording_path": recording_path}
                )
                break
            else:
                await ws.send_json({"type": "error", "text": f"unknown type: {msg_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        if session is not None:
            stream_manager.flush_remaining(session)
            stream_manager.save_full_recording(session)


@app.post("/api/polish")
def polish(
    req: PolishRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    system_prompt = (
        "You are a Chinese editor. Rewrite colloquial transcript into faithful formal written Chinese. "
        "Remove filler words and duplicates, keep facts/numbers/names/time unchanged, do not invent facts."
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": req.text}]
    try:
        output = build_llm_client().chat(messages)
        return {"text": output}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Polish failed: {exc}") from exc


@app.post("/api/minutes")
def minutes(
    req: PolishRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    system_prompt = (
        "You are a senior meeting secretary. Generate structured Chinese minutes with: "
        "discussion points, conclusions/decisions, action items with owner/deadline if available, "
        "open issues and risks. Keep it faithful and actionable."
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": req.text}]
    try:
        output = build_llm_client().chat(messages)
        return {"text": output}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Minutes failed: {exc}") from exc


@app.post("/api/chat")
def chat(
    req: ChatRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")
    try:
        output = build_llm_client().chat(req.messages)
        return {"text": output}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc


@app.get("/api/minio/tree")
def minio_tree(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    try:
        buckets = minio.list_buckets()
        items = []
        for bucket in buckets:
            keys = minio.list_objects(bucket)
            items.append({"bucket": bucket, "keys": keys})
        return {"items": items, "current_bucket": current_bucket}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Load tree failed: {exc}") from exc


@app.get("/api/minio/object")
def minio_object(
    bucket: str = Query(..., min_length=1),
    key: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    try:
        data = minio.get_object_bytes(bucket, key)
        preview = decode_preview(data, key)
        return {"bucket": bucket, "key": key, "preview": preview}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Read object failed: {exc}") from exc


@app.get("/api/files/records")
def list_file_records(
    session_id: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    items = file_record_store.list_records(
        session_id=session_id,
        bucket_name=bucket,
        kind=kind,
        limit=limit,
    )
    return {"items": items}


def _upload_recording_body(req: UploadRecordingRequest) -> dict[str, str]:
    session = stream_manager.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.last_recording_path:
        raise HTTPException(status_code=400, detail="no recording available in session")
    try:
        bucket = ensure_bucket()
        key = new_object_key("recordings", "wav")
        minio.upload_file(bucket, key, session.last_recording_path, "audio/wav")
        byte_length = Path(session.last_recording_path).stat().st_size if session.last_recording_path else None
        file_record_store.upsert_record(
            session_id=req.session_id,
            bucket_name=bucket,
            object_key=key,
            kind="recording_wav",
            content_type="audio/wav",
            byte_length=byte_length,
            local_path=session.last_recording_path,
        )
        return {"bucket": bucket, "key": key}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload recording failed: {exc}") from exc


@app.post("/api/upload/recording")
def upload_recording(
    req: UploadRecordingRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    return _upload_recording_body(req)


@app.post("/api/upload/recording/latest")
def upload_latest_recording(_user: dict[str, Any] = Depends(require_user)) -> dict[str, str]:
    try:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        candidates = [p for p in RECORDINGS_DIR.glob("*.wav") if p.is_file()]
        if not candidates:
            raise HTTPException(status_code=404, detail="no local recording file found")
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        bucket = ensure_bucket()
        key = new_object_key("recordings", "wav")
        minio.upload_file(bucket, key, str(latest), "audio/wav")
        file_record_store.upsert_record(
            session_id=None,
            bucket_name=bucket,
            object_key=key,
            kind="recording_wav",
            content_type="audio/wav",
            byte_length=latest.stat().st_size,
            local_path=str(latest),
        )
        return {"bucket": bucket, "key": key}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload latest recording failed: {exc}") from exc


@app.post("/api/client/upload/audio")
async def client_upload_audio(
    audio: UploadFile = File(...),
    client_recording_id: str | None = Form(default=None),
    _user: dict[str, Any] = Depends(require_user),
) -> ClientUploadAudioResponse:
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in {".wav", ".flac", ".aiff", ".aif", ".mp3", ".m4a"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")
    ext = suffix[1:] if suffix.startswith(".") else "wav"
    content_type = (audio.content_type or "").strip() or f"audio/{ext}"
    try:
        bucket = ensure_bucket()
        key = new_object_key("recordings", ext)
        minio.upload_bytes(bucket, key, data, content_type)
        file_record_store.upsert_record(
            session_id=(client_recording_id or None),
            bucket_name=bucket,
            object_key=key,
            kind="recording_wav",
            content_type=content_type,
            byte_length=len(data),
            local_path=None,
        )
        return ClientUploadAudioResponse(
            bucket=bucket,
            key=key,
            bytes=len(data),
            client_recording_id=client_recording_id or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Client upload failed: {exc}") from exc


def _upload_text_body(req: UploadTextRequest) -> dict[str, str]:
    kind_map = {"raw": "raw_transcript", "formal": "formal_text", "minutes": "meeting_minutes"}
    prefix = kind_map.get(req.kind)
    if prefix is None:
        raise HTTPException(status_code=400, detail="kind must be one of: raw, formal, minutes")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content is empty")
    try:
        bucket = ensure_bucket()
        key = new_object_key(prefix, "txt")
        payload = req.content.encode("utf-8")
        minio.upload_bytes(bucket, key, payload, "text/plain; charset=utf-8")
        file_record_store.upsert_record(
            session_id=None,
            bucket_name=bucket,
            object_key=key,
            kind=prefix,
            content_type="text/plain; charset=utf-8",
            byte_length=len(payload),
            local_path=None,
        )
        return {"bucket": bucket, "key": key}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload text failed: {exc}") from exc


@app.post("/api/upload/text")
def upload_text(
    req: UploadTextRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, str]:
    return _upload_text_body(req)


@app.post("/api/upload/all")
def upload_all(
    req: UploadAllRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    results: list[dict[str, str]] = []
    errors: list[str] = []
    if req.session_id:
        try:
            results.append(
                {"type": "recording", **_upload_recording_body(UploadRecordingRequest(session_id=req.session_id))}
            )
        except HTTPException as exc:
            errors.append(f"recording: {exc.detail}")
    if req.raw and req.raw.strip():
        try:
            results.append({"type": "raw", **_upload_text_body(UploadTextRequest(kind="raw", content=req.raw))})
        except HTTPException as exc:
            errors.append(f"raw: {exc.detail}")
    if req.formal and req.formal.strip():
        try:
            results.append({"type": "formal", **_upload_text_body(UploadTextRequest(kind="formal", content=req.formal))})
        except HTTPException as exc:
            errors.append(f"formal: {exc.detail}")
    if req.minutes and req.minutes.strip():
        try:
            results.append({"type": "minutes", **_upload_text_body(UploadTextRequest(kind="minutes", content=req.minutes))})
        except HTTPException as exc:
            errors.append(f"minutes: {exc.detail}")
    return {"results": results, "errors": errors}


from .routers import analysis_tasks, ir, workspace  # noqa: E402

app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(analysis_tasks.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(ir.router, prefix="/api/ir", tags=["ir"])

