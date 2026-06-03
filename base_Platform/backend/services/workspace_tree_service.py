"""扫描本地 wiki/ 目录生成树 JSON。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WorkspaceTreeService:
    def build_tree(self, project_root: Path) -> dict[str, Any]:
        wiki = project_root / "wiki"
        if not wiki.is_dir():
            return {"name": "wiki", "type": "dir", "children": []}

        def walk(p: Path) -> dict[str, Any]:
            if p.is_file():
                return {"name": p.name, "type": "file", "path": str(p.relative_to(project_root)).replace("\\", "/")}
            children = [walk(c) for c in sorted(p.iterdir()) if c.name != ".gitkeep"]
            return {"name": p.name, "type": "dir", "children": children}

        return walk(wiki)
