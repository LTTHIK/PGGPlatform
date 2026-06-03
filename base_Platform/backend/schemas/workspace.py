"""Wiki 工作区 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceInitRequest(BaseModel):
    project_code: str = Field(..., min_length=1)
    project_slug: str | None = None
    project_name: str | None = None
