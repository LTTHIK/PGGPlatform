"""向项目 Wiki 工作区写入 Markdown 页面。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .workspace_path_service import WorkspacePathService, validate_workspace_relative_path


class WikiWriter:
    _ALLOWED_SECTIONS = frozenset({"sources", "topics", "entities", "analyses"})

    def __init__(self, project_root: Path) -> None:
        self._paths = WorkspacePathService(Path(project_root).resolve())

    def write_page(self, section: str, filename: str, content: str) -> Path:
        sec = (section or "").strip().lower()
        if sec not in self._ALLOWED_SECTIONS:
            raise ValueError(f"section 须为 {sorted(self._ALLOWED_SECTIONS)} 之一")
        name = (filename or "").strip()
        if not name.endswith(".md"):
            name = f"{name}.md"
        rel = f"wiki/{sec}/{name}"
        validate_workspace_relative_path(rel)
        dest = self._paths.wiki_dir / sec / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest.resolve()

    def write_index(self, content: str) -> Path:
        dest = self._paths.wiki_dir / "index.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest.resolve()

    def write_overview(self, content: str) -> Path:
        dest = self._paths.wiki_dir / "overview.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest.resolve()

    def append_log(self, line: str) -> Path:
        dest = self._paths.wiki_dir / "log.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"- [{ts}] {line.rstrip()}\n"
        if dest.exists():
            with dest.open("a", encoding="utf-8") as fh:
                fh.write(entry)
        else:
            dest.write_text(f"# 项目日志\n\n{entry}", encoding="utf-8")
        return dest.resolve()

    def write_task_readme(self, task_id: str, content: str) -> Path:
        task_dir = self._paths.ensure_task_dir(task_id)
        dest = task_dir / "README.md"
        dest.write_text(content, encoding="utf-8")
        return dest.resolve()
