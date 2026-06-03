"""projects 表查询（工作区元数据）。"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class WorkspaceRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._url = (database_url or os.getenv("FILE_INDEX_DATABASE_URL") or "").strip()
        if not self._url:
            raise RuntimeError("FILE_INDEX_DATABASE_URL is not configured")

    def get_project_by_code(self, project_code: str) -> dict[str, Any] | None:
        code = (project_code or "").strip()
        if not code:
            return None
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, project_code, project_slug, project_name, workspace_root, created_at
                FROM projects WHERE project_code = %s
                """,
                (code,),
            ).fetchone()

    def insert_project(
        self,
        *,
        project_code: str,
        project_slug: str,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                INSERT INTO projects (project_code, project_slug, project_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (project_code) DO UPDATE SET project_name = EXCLUDED.project_name
                RETURNING id, project_code, project_slug, project_name, workspace_root, created_at
                """,
                (project_code, project_slug, project_name),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("insert projects returned no row")
        return dict(row)

    def update_workspace_root(self, project_id: UUID, workspace_root: str) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                "UPDATE projects SET workspace_root = %s, updated_at = now() WHERE id = %s",
                (workspace_root, str(project_id)),
            )
            conn.commit()
