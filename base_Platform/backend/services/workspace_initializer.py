"""从 wiki 模板初始化项目工作区目录。"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..repositories.workspace_repository import WorkspaceRepository
from .workspace_path_service import project_workspace_root, validate_project_slug


class WorkspaceInitializer:
    TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "resources" / "wiki_template" / "base_wiki"

    def __init__(self, *, repo: WorkspaceRepository | None = None) -> None:
        self._repo = repo or WorkspaceRepository()

    def init_project_workspace(
        self,
        *,
        project_code: str,
        project_slug: str | None = None,
        project_name: str | None = None,
    ) -> dict:
        slug = validate_project_slug(project_slug or project_code)
        row = self._repo.insert_project(
            project_code=project_code.strip(),
            project_slug=slug,
            project_name=project_name,
        )
        root = project_workspace_root(slug)
        root.mkdir(parents=True, exist_ok=True)
        if self.TEMPLATE_DIR.is_dir():
            for name in ("wiki", "templates", "raw"):
                src = self.TEMPLATE_DIR / name
                dest = root / name
                if src.is_dir() and not dest.exists():
                    shutil.copytree(src, dest)
            for f in self.TEMPLATE_DIR.glob("*.md"):
                dest = root / f.name
                if not dest.exists():
                    shutil.copy2(f, dest)
        (root / "runtime" / "tasks").mkdir(parents=True, exist_ok=True)
        self._repo.update_workspace_root(row["id"], str(root))
        return {
            "project_code": project_code,
            "project_slug": slug,
            "project_root": str(root),
            "created_from_template": self.TEMPLATE_DIR.is_dir(),
        }
