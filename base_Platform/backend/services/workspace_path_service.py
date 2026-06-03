"""项目 Wiki 工作区路径解析：按 project_slug / task_id 生成绝对路径，并防止路径穿越。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_TASK_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_project_slug(project_slug: str) -> str:
    s = (project_slug or "").strip().lower()
    if not s or not _SLUG_RE.match(s):
        raise ValueError(
            "project_slug 无效：须为小写字母数字开头，仅含 [a-z0-9_-]，长度 1–63"
        )
    return s


def validate_task_id(task_id: str) -> str:
    t = (task_id or "").strip()
    if not t or not _TASK_ID_RE.match(t):
        raise ValueError("task_id 须为 UUID 字符串（带连字符）")
    return t


def _resolve_under_base(base: Path, *parts: str) -> Path:
    p = base.joinpath(*parts).resolve()
    base_r = base.resolve()
    if base_r != p and base_r not in p.parents:
        raise ValueError("路径穿越：目标不在项目工作区根目录下")
    return p


@dataclass(frozen=True)
class WorkspacePathService:
    project_root: Path

    @property
    def raw_dir(self) -> Path:
        return self.project_root / "raw"

    @property
    def wiki_dir(self) -> Path:
        return self.project_root / "wiki"

    @property
    def templates_dir(self) -> Path:
        return self.project_root / "templates"

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / "runtime"

    def tasks_dir(self) -> Path:
        return self.runtime_dir / "tasks"

    def task_dir(self, task_id: str) -> Path:
        tid = validate_task_id(task_id)
        return _resolve_under_base(self.tasks_dir(), tid)

    def ensure_task_dir(self, task_id: str) -> Path:
        d = self.task_dir(task_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def task_subdir_map(self, task_id: str) -> dict[str, Path]:
        base = self.task_dir(task_id)
        return {
            "inputs": base / "inputs",
            "parsed": base / "parsed",
            "graphrag_input": base / "graphrag_input",
            "graphrag_out": base / "graphrag_out",
            "snapshots": base / "snapshots",
            "logs": base / "logs",
        }

    def ensure_task_subdirs(self, task_id: str) -> dict[str, Path]:
        base = self.ensure_task_dir(task_id)
        base_r = base.resolve()
        out: dict[str, Path] = {}
        for name, d in self.task_subdir_map(task_id).items():
            d = d.resolve()
            d.relative_to(base_r)
            d.mkdir(parents=True, exist_ok=True)
            out[name] = d
        return out


def project_root_from_task_workspace_path(workspace_task_path: str) -> Path:
    task_dir = Path((workspace_task_path or "").strip()).resolve()
    if not task_dir.is_dir():
        raise ValueError(f"workspace_task_path 不是有效目录: {workspace_task_path!r}")
    return task_dir.parent.parent.parent.resolve()


def workspace_projects_base(project_dir: Path | None = None) -> Path:
    root = project_dir or _default_project_dir()
    base = (os.getenv("WORKSPACE_PROJECTS_ROOT") or "").strip()
    if base:
        return Path(base).expanduser().resolve()
    return (root / "workspace" / "projects").resolve()


def project_workspace_root(project_slug: str, project_dir: Path | None = None) -> Path:
    slug = validate_project_slug(project_slug)
    base = workspace_projects_base(project_dir)
    return _resolve_under_base(base, slug)


def _default_project_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def validate_workspace_relative_path(rel: str, *, allowed_prefix: str = "wiki/") -> str:
    s = (rel or "").strip().replace("\\", "/").lstrip("/")
    parts = [p for p in s.split("/") if p != ""]
    if ".." in parts:
        raise ValueError("非法 path")
    ap = allowed_prefix.rstrip("/") + "/"
    if not s.startswith(ap):
        raise ValueError(f"path 必须以 {ap} 开头")
    return s


def resolve_under_project_root(project_root: Path, relative: str) -> Path:
    root_r = project_root.resolve()
    full = (root_r / relative).resolve()
    if full != root_r and root_r not in full.parents:
        raise ValueError("路径穿越：目标不在项目根目录下")
    return full
