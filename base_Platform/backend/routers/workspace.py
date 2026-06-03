"""
Wiki 工作区 API：初始化、目录树、读取 wiki 文件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth_users import require_user
from ..repositories.workspace_repository import WorkspaceRepository
from ..schemas.workspace import WorkspaceInitRequest
from ..services.workspace_initializer import WorkspaceInitializer
from ..services.workspace_path_service import resolve_under_project_root, validate_workspace_relative_path
from ..services.workspace_tree_service import WorkspaceTreeService

router = APIRouter()
_REPO = WorkspaceRepository()
_INIT = WorkspaceInitializer(repo=_REPO)
_TREE = WorkspaceTreeService()


@router.post("/init")
def init_workspace(
    body: WorkspaceInitRequest,
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    try:
        return _INIT.init_project_workspace(
            project_code=body.project_code,
            project_slug=body.project_slug,
            project_name=body.project_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tree")
def get_workspace_tree(
    project_code: str = Query(...),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    proj = _REPO.get_project_by_code(project_code)
    if not proj or not proj.get("workspace_root"):
        raise HTTPException(status_code=404, detail="project or workspace not found")
    root = Path(proj["workspace_root"])
    return {
        "project_code": project_code,
        "project_root": str(root),
        "tree": _TREE.build_tree(root),
    }


@router.get("/file")
def get_workspace_file(
    project_code: str = Query(...),
    path: str = Query(...),
    _user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    proj = _REPO.get_project_by_code(project_code)
    if not proj or not proj.get("workspace_root"):
        raise HTTPException(status_code=404, detail="project or workspace not found")
    try:
        rel = validate_workspace_relative_path(path)
        full = resolve_under_project_root(Path(proj["workspace_root"]), rel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not full.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return {"path": rel, "content": full.read_text(encoding="utf-8")}
