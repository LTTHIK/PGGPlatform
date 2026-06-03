"""生成 artifact_manifest.json，供平台侧 model_artifacts 引用。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import config
from .artifact_validator import ValidationResult


def write_artifact_manifest(
    task_root: Path,
    *,
    model_task_id: str,
    validation: ValidationResult,
    extra: dict[str, Any] | None = None,
) -> Path:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "model_task_id": model_task_id,
        "graphrag_model_version": config.model_version,
        "task_root": str(task_root.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graphrag_root": str(task_root.resolve()),
        "output_dir": str(validation.output_dir),
        **validation.to_manifest_fragment(),
    }
    if extra:
        body["extra"] = extra

    path = task_root / "artifact_manifest.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(task_root: Path) -> dict[str, Any] | None:
    path = task_root / "artifact_manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
