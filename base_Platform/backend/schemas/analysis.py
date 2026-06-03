"""
分析任务相关 Pydantic 模型与阶段一状态常量。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# 阶段一 GraphRAG 索引成功后的任务状态
PHASE1_SUCCESS_STATUS = "completed"
PHASE1_SUCCESS_PROGRESS = 100
PHASE1_SUCCESS_STEP = "phase1_done"


class CreateAnalysisTaskRequest(BaseModel):
    project_code: str = Field(..., min_length=1, max_length=128)
    project_name: str | None = None
    skill_id: str = Field(..., min_length=1, max_length=128)
    mode: str = Field(default="auto", max_length=64)
    file_record_ids: list[int] = Field(..., min_length=1)


class AnalysisTaskCreate(BaseModel):
    project_id: UUID
    project_code: str
    skill_id: str
    mode: str = "auto"


class AnalysisTaskRead(BaseModel):
    id: UUID
    project_id: UUID
    project_code: str
    skill_id: str
    mode: str
    status: str
    progress: int
    current_step: str | None = None
    error_message: str | None = None
    model_task_id: str | None = None
    workspace_task_path: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AnalysisTaskRead:
        return cls(
            id=UUID(str(row["id"])),
            project_id=UUID(str(row["project_id"])),
            project_code=str(row["project_code"]),
            skill_id=str(row["skill_id"]),
            mode=str(row["mode"]),
            status=str(row["status"]),
            progress=int(row.get("progress") or 0),
            current_step=row.get("current_step"),
            error_message=row.get("error_message"),
            model_task_id=row.get("model_task_id"),
            workspace_task_path=row.get("workspace_task_path"),
            created_at=row.get("created_at"),
        )


class AnalysisTaskFileRead(BaseModel):
    id: UUID
    task_id: UUID
    file_record_id: int | None = None
    filename: str
    parse_status: str | None = None
    local_path: str | None = None
    graphrag_input_path: str | None = None
    parsed_text_path: str | None = None
    parse_error: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AnalysisTaskFileRead:
        return cls(
            id=UUID(str(row["id"])),
            task_id=UUID(str(row["task_id"])),
            file_record_id=row.get("file_record_id"),
            filename=str(row.get("filename") or ""),
            parse_status=row.get("parse_status"),
            local_path=row.get("local_path"),
            graphrag_input_path=row.get("graphrag_input_path"),
            parsed_text_path=row.get("parsed_text_path"),
            parse_error=row.get("parse_error"),
        )


class RunPhase1Response(BaseModel):
    task_id: str
    phase: str
    status: str
    model_task_id: str | None = None
    manifest_path: str | None = None
    graphrag_output_dir: str | None = None
    graphrag_service_task_root: str | None = None
    message: str | None = None
