"""
analysis_tasks / analysis_task_files / analysis_task_events / projects / file_records 的 PostgreSQL 访问。
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class AnalysisRepository:
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
                FROM projects
                WHERE project_code = %s
                """,
                (code,),
            ).fetchone()

    def get_project_by_id(self, project_id: UUID) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, project_code, project_slug, project_name, workspace_root, created_at
                FROM projects
                WHERE id = %s
                """,
                (str(project_id),),
            ).fetchone()

    def get_project_by_slug(self, project_slug: str) -> dict[str, Any] | None:
        slug = (project_slug or "").strip()
        if not slug:
            return None
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, project_code, project_slug, project_name, workspace_root, created_at
                FROM projects
                WHERE project_slug = %s
                """,
                (slug,),
            ).fetchone()

    def update_project_name(self, project_id: UUID, project_name: str) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                "UPDATE projects SET project_name = %s, updated_at = now() WHERE id = %s",
                (project_name, str(project_id)),
            )
            conn.commit()

    def update_project_workspace_root(self, *, project_id: UUID, workspace_root: str) -> int:
        with psycopg.connect(self._url) as conn:
            cur = conn.execute(
                """
                UPDATE projects SET workspace_root = %s, updated_at = now()
                WHERE id = %s
                """,
                (workspace_root, str(project_id)),
            )
            conn.commit()
            return cur.rowcount

    def get_file_record_by_id(self, file_id: int) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, bucket_name, object_key, kind, content_type, byte_length, local_path, created_at
                FROM file_records
                WHERE id = %s
                """,
                (file_id,),
            ).fetchone()

    def insert_analysis_task(
        self,
        *,
        project_id: UUID,
        project_code: str,
        skill_id: str,
        mode: str,
        created_by: int | None,
        workspace_task_path: str | None = None,
    ) -> dict[str, Any]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                INSERT INTO analysis_tasks (
                    project_id, project_code, skill_id, mode,
                    status, progress, workspace_task_path, created_by
                )
                VALUES (%s, %s, %s, %s, 'pending', 0, %s, %s)
                RETURNING id, project_id, project_code, skill_id, mode, status, progress,
                          current_step, workspace_task_path, model_task_id, created_at
                """,
                (
                    str(project_id),
                    project_code,
                    skill_id,
                    mode,
                    workspace_task_path,
                    created_by,
                ),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("insert analysis_tasks returned no row")
        return dict(row)

    def update_task_workspace_path(self, task_id: UUID, workspace_task_path: str) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                UPDATE analysis_tasks
                SET workspace_task_path = %s, updated_at = now()
                WHERE id = %s
                """,
                (workspace_task_path, str(task_id)),
            )
            conn.commit()

    def get_analysis_task_by_id(self, task_id: UUID) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, project_id, project_code, skill_id, mode, status, progress,
                       current_step, error_message, model_task_id, model_status,
                       workspace_task_path, created_by, created_at, updated_at, finished_at
                FROM analysis_tasks
                WHERE id = %s
                """,
                (str(task_id),),
            ).fetchone()

    def list_tasks_for_project(self, project_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, project_code, skill_id, mode, status, progress,
                       current_step, workspace_task_path, model_task_id, created_at
                FROM analysis_tasks
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (str(project_id), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_analysis_task_status(
        self,
        task_id: UUID,
        *,
        status: str,
        progress: int,
        current_step: str | None = None,
        error_message: str | None = None,
        model_task_id: str | None = None,
        model_status: str | None = None,
        finished: bool = False,
    ) -> None:
        sets = ["status = %s", "progress = %s", "updated_at = now()"]
        params: list[Any] = [status, progress]
        if current_step is not None:
            sets.append("current_step = %s")
            params.append(current_step)
        if error_message is not None:
            sets.append("error_message = %s")
            params.append(error_message)
        if model_task_id is not None:
            sets.append("model_task_id = %s")
            params.append(model_task_id)
        if model_status is not None:
            sets.append("model_status = %s")
            params.append(model_status)
        if finished:
            sets.append("finished_at = now()")
        params.append(str(task_id))
        sql = f"UPDATE analysis_tasks SET {', '.join(sets)} WHERE id = %s"
        with psycopg.connect(self._url) as conn:
            conn.execute(sql, params)
            conn.commit()

    def insert_analysis_task_file(
        self,
        *,
        task_id: UUID,
        project_id: UUID,
        file_record_id: int | None,
        filename: str,
        file_ext: str | None,
        content_type: str | None,
        byte_length: int | None,
        minio_bucket: str | None,
        minio_object_key: str | None,
        local_path: str | None,
    ) -> dict[str, Any]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                INSERT INTO analysis_task_files (
                    task_id, project_id, file_record_id, filename, file_ext, content_type,
                    byte_length, minio_bucket, minio_object_key, local_path, parse_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id, task_id, file_record_id, filename, parse_status, local_path
                """,
                (
                    str(task_id),
                    str(project_id),
                    file_record_id,
                    filename,
                    file_ext,
                    content_type,
                    byte_length,
                    minio_bucket,
                    minio_object_key,
                    local_path,
                ),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("insert analysis_task_files returned no row")
        return dict(row)

    def list_analysis_task_files(self, task_id: UUID) -> list[dict[str, Any]]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, project_id, file_record_id, filename, file_ext,
                       minio_bucket, minio_object_key, local_path, raw_workspace_path,
                       parsed_text_path, graphrag_input_path, parse_status, parse_error
                FROM analysis_task_files
                WHERE task_id = %s
                ORDER BY created_at
                """,
                (str(task_id),),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_analysis_task_file_staged(
        self,
        *,
        task_file_id: UUID,
        local_input_path: str,
        parse_error: str | None = None,
    ) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                UPDATE analysis_task_files
                SET local_path = %s,
                    raw_workspace_path = %s,
                    parse_status = 'staged',
                    parse_error = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (local_input_path, local_input_path, parse_error, str(task_file_id)),
            )
            conn.commit()

    def update_analysis_task_file_failed(self, *, task_file_id: UUID, error_message: str) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                UPDATE analysis_task_files
                SET parse_status = 'failed', parse_error = %s, updated_at = now()
                WHERE id = %s
                """,
                (error_message, str(task_file_id)),
            )
            conn.commit()

    def update_analysis_task_file_normalized(
        self,
        *,
        task_file_id: UUID,
        graphrag_input_path: str,
        parsed_text_path: str | None = None,
    ) -> None:
        pt = parsed_text_path or graphrag_input_path
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                UPDATE analysis_task_files
                SET graphrag_input_path = %s,
                    parsed_text_path = %s,
                    parse_status = 'normalized',
                    parse_error = NULL,
                    updated_at = now()
                WHERE id = %s
                """,
                (graphrag_input_path, pt, str(task_file_id)),
            )
            conn.commit()

    def insert_analysis_task_event(
        self,
        *,
        task_id: UUID,
        event_type: str,
        message: str | None,
        payload: dict[str, Any] | None,
    ) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                """
                INSERT INTO analysis_task_events (task_id, event_type, message, payload_json)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    str(task_id),
                    event_type,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
