"""
结构化分析任务 API：创建任务、staging、run-phase1。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth_users import require_user
from ..repositories.analysis_repository import AnalysisRepository
from ..schemas.analysis import (
    AnalysisTaskFileRead,
    AnalysisTaskRead,
    CreateAnalysisTaskRequest,
    RunPhase1Response,
)
from ..services.analysis_file_prepare_service import AnalysisFilePrepareService
from ..services.analysis_pipeline_service import AnalysisPipelineService
from ..services.analysis_task_service import AnalysisTaskService
from ..services.graphrag_model_client import GraphragModelClient

router = APIRouter()

_SERVICE = AnalysisTaskService()
_PREPARE = AnalysisFilePrepareService()
_PIPELINE = AnalysisPipelineService()
_GRAPHRAG = GraphragModelClient()
_REPO = AnalysisRepository()


@router.post("/tasks", response_model=AnalysisTaskRead)
def create_analysis_task(
    body: CreateAnalysisTaskRequest,
    user: dict[str, Any] = Depends(require_user),
) -> AnalysisTaskRead:
    try:
        return _SERVICE.create_task_with_files(body, user_id=int(user["id"]))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tasks", response_model=list[AnalysisTaskRead])
def list_analysis_tasks(
    project_id: UUID = Query(...),
    _user: dict[str, Any] = Depends(require_user),
) -> list[AnalysisTaskRead]:
    rows = _REPO.list_tasks_for_project(project_id)
    return [AnalysisTaskRead.from_row(r) for r in rows]


@router.get("/tasks/{task_id}", response_model=AnalysisTaskRead)
def get_analysis_task(
    task_id: UUID,
    _user: dict[str, Any] = Depends(require_user),
) -> AnalysisTaskRead:
    row = _REPO.get_analysis_task_by_id(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    return AnalysisTaskRead.from_row(row)


@router.get("/tasks/{task_id}/files", response_model=list[AnalysisTaskFileRead])
def list_task_files(
    task_id: UUID,
    _user: dict[str, Any] = Depends(require_user),
) -> list[AnalysisTaskFileRead]:
    if not _REPO.get_analysis_task_by_id(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    rows = _REPO.list_analysis_task_files(task_id)
    return [AnalysisTaskFileRead.from_row(r) for r in rows]


@router.post("/tasks/{task_id}/stage")
def stage_task_files(
    task_id: UUID,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    try:
        return _PREPARE.stage_files(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/tasks/{task_id}/run-phase1", response_model=RunPhase1Response)
def run_phase1_pipeline(
    task_id: UUID,
    skip_staging: bool = Query(False, description="为 true 时跳过 Step 4，要求文件已为 staged"),
    _user: dict[str, Any] = Depends(require_user),
) -> RunPhase1Response:
    try:
        result = _PIPELINE.run_phase1(task_id, skip_staging=skip_staging)
        return RunPhase1Response(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tasks/{task_id}/prepare-stub")
def prepare_stub(task_id: UUID, _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {
        "deprecated": True,
        "use_post_stage": f"/api/analysis/tasks/{task_id}/stage",
        "use_post_run_phase1": f"/api/analysis/tasks/{task_id}/run-phase1",
    }


@router.get("/graphrag/health")
def graphrag_health(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return _GRAPHRAG.health_stub()
