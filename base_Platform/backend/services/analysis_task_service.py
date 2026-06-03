"""
分析任务编排：Step 1–3 创建任务并绑定 file_records。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from ..repositories.analysis_repository import AnalysisRepository
from ..schemas.analysis import (
    AnalysisTaskCreate,
    AnalysisTaskRead,
    CreateAnalysisTaskRequest,
)
from .workspace_path_service import WorkspacePathService


class AnalysisTaskService:
    def __init__(
        self,
        *,
        repo: AnalysisRepository | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._repo = repo or AnalysisRepository()
        self._project_dir = project_dir

    def create_task(self, body: AnalysisTaskCreate, *, user_id: int | None) -> AnalysisTaskRead:
        proj = self._repo.get_project_by_id(body.project_id)
        if not proj:
            raise ValueError("project not found")
        root = (proj.get("workspace_root") or "").strip()
        if not root:
            raise ValueError("workspace not initialized: call POST /api/workspace/init first")
        project_root = Path(root).resolve()
        if not project_root.is_dir():
            raise ValueError("workspace_root path missing on disk")

        row = self._repo.insert_analysis_task(
            project_id=body.project_id,
            project_code=body.project_code.strip(),
            skill_id=body.skill_id.strip(),
            mode=body.mode.strip(),
            created_by=user_id,
            workspace_task_path=None,
        )
        task_id = UUID(str(row["id"]))
        paths = WorkspacePathService(project_root)
        paths.ensure_task_subdirs(str(task_id))
        task_dir = paths.task_dir(str(task_id))
        self._repo.update_task_workspace_path(task_id, str(task_dir))
        row["workspace_task_path"] = str(task_dir)
        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="task_created",
            message="analysis_tasks row created (legacy path, no files)",
            payload={"project_id": str(body.project_id), "skill_id": body.skill_id},
        )
        return AnalysisTaskRead.from_row(row)

    def create_task_with_files(
        self, body: CreateAnalysisTaskRequest, *, user_id: int | None
    ) -> AnalysisTaskRead:
        proj = self._repo.get_project_by_code(body.project_code.strip())
        if not proj:
            raise ValueError(f"project not found: project_code={body.project_code!r}")
        if body.project_name and str(body.project_name).strip():
            self._repo.update_project_name(UUID(str(proj["id"])), str(body.project_name).strip())

        root = (proj.get("workspace_root") or "").strip()
        if not root:
            raise ValueError("workspace not initialized: call POST /api/workspace/init first")
        project_root = Path(root).resolve()
        if not project_root.is_dir():
            raise ValueError("workspace_root path missing on disk")

        project_id = UUID(str(proj["id"]))
        project_code = str(proj["project_code"])

        files_meta: list[tuple[int, dict[str, Any]]] = []
        for fid in body.file_record_ids:
            fr = self._repo.get_file_record_by_id(int(fid))
            if not fr:
                raise ValueError(f"file_record not found: id={fid}")
            files_meta.append((int(fid), fr))

        row = self._repo.insert_analysis_task(
            project_id=project_id,
            project_code=project_code,
            skill_id=body.skill_id.strip(),
            mode=body.mode.strip(),
            created_by=user_id,
            workspace_task_path=None,
        )
        task_id = UUID(str(row["id"]))
        paths = WorkspacePathService(project_root)
        paths.ensure_task_subdirs(str(task_id))
        task_dir = paths.task_dir(str(task_id))
        self._repo.update_task_workspace_path(task_id, str(task_dir))
        row["workspace_task_path"] = str(task_dir)

        for fid, fr in files_meta:
            key = str(fr.get("object_key") or "")
            name = Path(key).name if key else f"file_{fid}"
            ext = Path(name).suffix.lower().lstrip(".") or None
            self._repo.insert_analysis_task_file(
                task_id=task_id,
                project_id=project_id,
                file_record_id=fid,
                filename=name,
                file_ext=ext,
                content_type=fr.get("content_type"),
                byte_length=int(fr["byte_length"]) if fr.get("byte_length") is not None else None,
                minio_bucket=fr.get("bucket_name"),
                minio_object_key=fr.get("object_key"),
                local_path=fr.get("local_path"),
            )

        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="task_created",
            message="analysis_tasks + analysis_task_files bound",
            payload={
                "project_code": project_code,
                "file_record_ids": body.file_record_ids,
            },
        )
        return AnalysisTaskRead.from_row(row)
