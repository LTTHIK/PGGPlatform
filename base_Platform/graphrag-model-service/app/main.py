"""
GraphRAG HTTP Model Service — FastAPI 入口。

启动示例（在 graphrag-model-service 目录）::

    pip install -r requirements.txt
    export GRAPHRAG_PROMPTS_DIR=/path/to/qwen_graphrag_demo/prompts
    uvicorn app.main:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .config import config
from .schemas import (
    ArtifactsResponse,
    CreateIndexTaskRequest,
    CreateIndexTaskResponse,
    IndexOptions,
    LogsResponse,
    TaskStatusResponse,
)
from .services.artifact_validator import validate_task_output
from .services.graphrag_runner import run_graphrag_index
from .services.input_preparer import (
    copy_prompts_bundle,
    copy_settings_template,
    prepare_normalized_inputs,
)
from .services.manifest_writer import load_manifest, write_artifact_manifest
from .services.task_registry import TaskStatus, registry


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_pipeline(model_task_id: str, task_root: Path, index_options: IndexOptions | None) -> None:
    stdout_log = task_root / "logs" / "service_index.stdout.log"
    stderr_log = task_root / "logs" / "service_index.stderr.log"
    registry.update(
        model_task_id,
        status=TaskStatus.RUNNING,
        started_at=_utc_iso(),
        stdout_log=stdout_log,
        stderr_log=stderr_log,
    )
    try:
        rc = run_graphrag_index(
            task_root,
            index_options=index_options,
            stdout_file=stdout_log,
            stderr_file=stderr_log,
        )
        validation = validate_task_output(task_root)
        manifest_path = write_artifact_manifest(
            task_root,
            model_task_id=model_task_id,
            validation=validation,
            extra={"graphrag_cli_exit_code": rc},
        )
        registry.update(
            model_task_id,
            manifest_path=manifest_path,
            finished_at=_utc_iso(),
            returncode=rc,
        )
        if rc != 0:
            registry.update(
                model_task_id,
                status=TaskStatus.FAILED,
                message=f"graphrag CLI exited with code {rc}",
            )
            return
        if not validation.ok:
            registry.update(
                model_task_id,
                status=TaskStatus.FAILED,
                message="artifact validation failed: " + "; ".join(validation.errors),
            )
            return
        registry.update(model_task_id, status=TaskStatus.COMPLETED, message=None)
    except Exception as exc:  # noqa: BLE001
        registry.update(
            model_task_id,
            status=TaskStatus.FAILED,
            message=str(exc),
            finished_at=_utc_iso(),
        )


app = FastAPI(
    title="GraphRAG Model Service",
    version="1.0.0",
    description="HTTP 封装 graphrag index：创建异步任务、查询状态、获取 manifest 与 CLI 日志。",
)


@app.on_event("startup")
def _startup() -> None:
    config.run_root.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "run_root": str(config.run_root),
        "graphrag_cli": config.graphrag_cli,
        "settings_template": str(config.settings_template),
        "prompts_dir_configured": config.prompts_dir is not None,
        "model_version": config.model_version,
    }


@app.post("/api/graphrag/index-tasks", response_model=CreateIndexTaskResponse)
def create_index_task(body: CreateIndexTaskRequest) -> CreateIndexTaskResponse:
    model_task_id = uuid.uuid4().hex
    task_root = config.run_root / model_task_id
    task_root.mkdir(parents=True, exist_ok=True)
    registry.register_queued(model_task_id, task_root)

    try:
        copy_settings_template(task_root, config.settings_template)
        if config.prompts_dir:
            copied = copy_prompts_bundle(task_root, config.prompts_dir)
            if copied is None:
                raise FileNotFoundError(
                    f"GRAPHRAG_PROMPTS_DIR is set but not a directory: {config.prompts_dir}"
                )
        for sf in body.source_files:
            prepare_normalized_inputs(
                task_root,
                source_local_path=sf.local_path,
                logical_name=sf.logical_name,
            )
    except Exception as exc:  # noqa: BLE001
        registry.update(
            model_task_id,
            status=TaskStatus.FAILED,
            message=f"prepare stage failed: {exc}",
            finished_at=_utc_iso(),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    thread = threading.Thread(
        target=_run_pipeline,
        args=(model_task_id, task_root, body.index_options),
        daemon=True,
        name=f"graphrag-{model_task_id[:8]}",
    )
    thread.start()

    return CreateIndexTaskResponse(model_task_id=model_task_id, status=TaskStatus.QUEUED.value)


@app.get("/api/graphrag/index-tasks/{model_task_id}", response_model=TaskStatusResponse)
def get_task_status(model_task_id: str) -> TaskStatusResponse:
    rec = registry.get(model_task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="model_task_id not found")
    return TaskStatusResponse(
        model_task_id=rec.model_task_id,
        status=rec.status.value,
        message=rec.message,
        task_root=str(rec.task_root),
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        returncode=rec.returncode,
    )


@app.get("/api/graphrag/index-tasks/{model_task_id}/artifacts", response_model=ArtifactsResponse)
def get_task_artifacts(model_task_id: str) -> ArtifactsResponse:
    rec = registry.get(model_task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="model_task_id not found")
    if rec.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
        raise HTTPException(
            status_code=409,
            detail="artifacts not ready: task still queued or running",
        )
    manifest = load_manifest(rec.task_root)
    if not manifest:
        raise HTTPException(status_code=404, detail="artifact_manifest.json missing")
    return ArtifactsResponse(manifest=manifest)


@app.get("/api/graphrag/index-tasks/{model_task_id}/logs", response_model=LogsResponse)
def get_task_logs(model_task_id: str) -> LogsResponse:
    rec = registry.get(model_task_id)
    if not rec:
        raise HTTPException(status_code=404, detail="model_task_id not found")

    def _read(p: Path | None) -> str:
        if not p or not p.is_file():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    return LogsResponse(
        stdout=_read(rec.stdout_log),
        stderr=_read(rec.stderr_log),
    )
