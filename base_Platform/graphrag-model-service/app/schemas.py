"""HTTP 契约：创建索引任务、查询状态、manifest、日志。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    """待编入索引的本地文件（须为 GraphRAG 服务进程可读的绝对路径）。"""

    local_path: str = Field(..., min_length=1, description="服务器本地绝对路径")
    logical_name: str | None = Field(
        default=None,
        description="写入 input/normalized/ 时的文件名（仅 basename，不含路径）；缺省则沿用源文件名",
    )


class IndexOptions(BaseModel):
    """透传给 `graphrag index` 的选项。"""

    method: str = Field(default="standard", description="standard | fast | ...")
    verbose: bool = False
    dry_run: bool = False
    skip_validation: bool = False
    cache: bool = True


class CreateIndexTaskRequest(BaseModel):
    source_files: list[SourceFile] = Field(..., min_length=1)
    index_options: IndexOptions | None = None


class CreateIndexTaskResponse(BaseModel):
    model_task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    model_task_id: str
    status: str
    message: str | None = None
    task_root: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None


class ArtifactsResponse(BaseModel):
    """与 artifact_manifest.json 内容一致（或子集），便于平台直接反序列化。"""

    manifest: dict[str, Any]


class LogsResponse(BaseModel):
    stdout: str
    stderr: str
