"""内存任务表：queued / running / completed / failed。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    model_task_id: str
    status: TaskStatus
    task_root: Path
    message: str | None = None
    created_at: str = field(default_factory=_utc_iso)
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None
    manifest_path: Path | None = None
    stdout_log: Path | None = None
    stderr_log: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_task_id": self.model_task_id,
            "status": self.status.value,
            "message": self.message,
            "task_root": str(self.task_root),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "returncode": self.returncode,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "stdout_log": str(self.stdout_log) if self.stdout_log else None,
            "stderr_log": str(self.stderr_log) if self.stderr_log else None,
        }


class TaskRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskRecord] = {}

    def register_queued(self, model_task_id: str, task_root: Path) -> TaskRecord:
        """由调用方预先创建目录 model_task_id，再登记为 queued。"""
        rec = TaskRecord(model_task_id=model_task_id, status=TaskStatus.QUEUED, task_root=task_root)
        with self._lock:
            self._tasks[model_task_id] = rec
        return rec

    def get(self, model_task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(model_task_id)

    def update(
        self,
        model_task_id: str,
        *,
        status: TaskStatus | None = None,
        message: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        returncode: int | None = None,
        manifest_path: Path | None = None,
        stdout_log: Path | None = None,
        stderr_log: Path | None = None,
    ) -> None:
        with self._lock:
            rec = self._tasks.get(model_task_id)
            if not rec:
                return
            if status is not None:
                rec.status = status
            if message is not None:
                rec.message = message
            if started_at is not None:
                rec.started_at = started_at
            if finished_at is not None:
                rec.finished_at = finished_at
            if returncode is not None:
                rec.returncode = returncode
            if manifest_path is not None:
                rec.manifest_path = manifest_path
            if stdout_log is not None:
                rec.stdout_log = stdout_log
            if stderr_log is not None:
                rec.stderr_log = stderr_log


registry = TaskRegistry()
