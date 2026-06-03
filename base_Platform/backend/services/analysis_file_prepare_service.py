"""
分析任务文件 Staging（阶段一 Step 4）：从 MinIO 下载到 task inputs/，不做格式转换。

PDF/Word/Excel → txt 由 GraphRAG 服务（8090）的 input_preparer 负责。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

from ..repositories.analysis_repository import AnalysisRepository
from .minio_download import download_object_to_file
from .workspace_path_service import WorkspacePathService, project_root_from_task_workspace_path

_SAFE_NAME_RE = re.compile(r"[^\w.\-]+", re.UNICODE)


def _safe_filename(name: str) -> str:
    base = Path(name).name or "file"
    return _SAFE_NAME_RE.sub("_", base).strip("._") or "file"


class AnalysisFilePrepareService:
    def __init__(self, *, repo: AnalysisRepository | None = None) -> None:
        self._repo = repo or AnalysisRepository()

    def prepare_stub(self, task_id: UUID) -> dict[str, Any]:
        return self.stage_files(task_id)

    def stage_files(self, task_id: UUID) -> dict[str, Any]:
        task = self._repo.get_analysis_task_by_id(task_id)
        if not task:
            raise ValueError("task not found")

        workspace_task_path = (task.get("workspace_task_path") or "").strip()
        if not workspace_task_path:
            raise ValueError("workspace_task_path missing; create task first")

        project_root = project_root_from_task_workspace_path(workspace_task_path)
        paths_svc = WorkspacePathService(project_root)
        subdirs = paths_svc.ensure_task_subdirs(str(task_id))
        inputs_dir = subdirs["inputs"]

        rows = self._repo.list_analysis_task_files(task_id)
        if not rows:
            raise ValueError("no analysis_task_files for task")

        input_files: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for row in rows:
            task_file_id = UUID(str(row["id"]))
            fid = row.get("file_record_id")
            bucket = (row.get("minio_bucket") or "").strip()
            key = (row.get("minio_object_key") or "").strip()
            filename = str(row.get("filename") or "file")

            if not bucket or not key:
                if fid is not None:
                    fr = self._repo.get_file_record_by_id(int(fid))
                    if fr:
                        bucket = (fr.get("bucket_name") or "").strip()
                        key = (fr.get("object_key") or "").strip()
                        if not filename or filename == "file":
                            filename = Path(key).name if key else filename

            if not bucket or not key:
                msg = "missing minio bucket/key"
                self._repo.update_analysis_task_file_failed(
                    task_file_id=task_file_id, error_message=msg
                )
                errors.append({"file_record_id": fid, "error": msg})
                continue

            dest_name = f"{fid}_{_safe_filename(filename)}" if fid is not None else _safe_filename(filename)
            dest = (inputs_dir / dest_name).resolve()
            try:
                download_object_to_file(bucket=bucket, key=key, dest=dest)
                local_path = str(dest)
                self._repo.update_analysis_task_file_staged(
                    task_file_id=task_file_id,
                    local_input_path=local_path,
                )
                input_files.append(
                    {
                        "file_record_id": fid,
                        "task_file_id": str(task_file_id),
                        "filename": filename,
                        "local_path": local_path,
                    }
                )
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self._repo.update_analysis_task_file_failed(
                    task_file_id=task_file_id, error_message=msg
                )
                errors.append({"file_record_id": fid, "filename": filename, "error": msg})

        status = "staged" if input_files and not errors else ("partial" if input_files else "failed")

        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="files_staged",
            message=f"staged {len(input_files)} file(s), {len(errors)} error(s)",
            payload={
                "input_files": input_files,
                "errors": errors,
                "inputs_dir": str(inputs_dir),
            },
        )

        if input_files:
            self._repo.update_analysis_task_status(
                task_id,
                status="running",
                progress=20,
                current_step="files_staged",
            )

        return {
            "task_id": str(task_id),
            "status": status,
            "staged_count": len(input_files),
            "input_files": input_files,
            "errors": errors,
            "graphrag_input_dir": str(subdirs["graphrag_input"]),
            "graphrag_output_dir": str(subdirs["graphrag_out"]),
            "logs_dir": str(subdirs["logs"]),
            "inputs_dir": str(inputs_dir),
        }
