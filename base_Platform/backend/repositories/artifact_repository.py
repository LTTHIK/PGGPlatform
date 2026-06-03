"""
model_artifacts 表的读写。

职责：记录 GraphRAG 索引产物路径与 manifest；由 AnalysisPipelineService 在 Step 6 写入。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def _parquet_row_count(path: str | None) -> int | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        import pandas as pd

        return int(len(pd.read_parquet(p)))
    except Exception:
        return None


def _manifest_paths(manifest: dict[str, Any], *, graphrag_out_dir: str) -> dict[str, Any]:
    arts = manifest.get("artifacts") or {}
    output_dir = manifest.get("output_dir") or str(Path(graphrag_out_dir).resolve())
    entities_path = arts.get("entities_parquet")
    relationships_path = arts.get("relationships_parquet")
    text_units_path = arts.get("text_units_parquet")
    community_reports_path = arts.get("community_reports_parquet")
    lancedb_dir = arts.get("lancedb_dir")
    documents_path = str(Path(output_dir) / "documents.parquet") if output_dir else None
    communities_path = str(Path(output_dir) / "communities.parquet") if output_dir else None

    entity_count = _parquet_row_count(entities_path)
    relationship_count = _parquet_row_count(relationships_path)
    text_unit_count = _parquet_row_count(text_units_path)
    document_count = _parquet_row_count(documents_path)
    community_count = _parquet_row_count(communities_path)
    community_report_count = _parquet_row_count(community_reports_path)

    return {
        "output_dir": output_dir,
        "lancedb_uri": lancedb_dir,
        "entities_path": entities_path,
        "relationships_path": relationships_path,
        "text_units_path": text_units_path,
        "communities_path": communities_path,
        "community_reports_path": community_reports_path,
        "entity_count": entity_count,
        "relationship_count": relationship_count,
        "text_unit_count": text_unit_count,
        "document_count": document_count,
        "community_count": community_count,
        "community_report_count": community_report_count,
    }


class ArtifactRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._url = (database_url or os.getenv("FILE_INDEX_DATABASE_URL") or "").strip()
        if not self._url:
            raise RuntimeError("FILE_INDEX_DATABASE_URL is not configured")

    def get_by_task(self, task_id: UUID) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            return conn.execute(
                """
                SELECT id, task_id, project_id, model_task_id, model_version, manifest_path,
                       manifest_json, project_root, output_dir, lancedb_uri,
                       entities_path, relationships_path, text_units_path,
                       communities_path, community_reports_path,
                       entity_count, relationship_count, text_unit_count,
                       community_count, community_report_count,
                       stdout_path, stderr_path, status, error_message,
                       created_at, updated_at
                FROM model_artifacts
                WHERE task_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(task_id),),
            ).fetchone()

    def insert_pending_stub(
        self,
        *,
        task_id: UUID,
        project_id: UUID,
        model_task_id: str | None = None,
    ) -> dict[str, Any]:
        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                INSERT INTO model_artifacts (task_id, project_id, model_task_id, status, manifest_json)
                VALUES (%s, %s, %s, 'pending', %s::jsonb)
                RETURNING id, task_id, project_id, status, model_task_id
                """,
                (str(task_id), str(project_id), model_task_id, json.dumps({})),
            ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("insert model_artifacts returned no row")
        return dict(row)

    def upsert_from_manifest(
        self,
        *,
        task_id: UUID,
        project_id: UUID,
        model_task_id: str,
        manifest: dict[str, Any],
        manifest_path: str,
        graphrag_out_dir: str,
        logs_dir: str,
        status: str,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        paths = _manifest_paths(manifest, graphrag_out_dir=graphrag_out_dir)
        stdout_path = str(Path(logs_dir) / "graphrag.stdout.log")
        stderr_path = str(Path(logs_dir) / "graphrag.stderr.log")
        existing = self.get_by_task(task_id)

        row_values = (
            model_task_id,
            manifest.get("graphrag_model_version"),
            manifest_path,
            json.dumps(manifest, ensure_ascii=False),
            manifest.get("task_root") or manifest.get("graphrag_root"),
            paths.get("output_dir"),
            paths.get("lancedb_uri"),
            paths.get("entities_path"),
            paths.get("relationships_path"),
            paths.get("text_units_path"),
            paths.get("community_reports_path"),
            paths.get("entity_count"),
            paths.get("relationship_count"),
            paths.get("text_unit_count"),
            paths.get("community_count"),
            paths.get("community_report_count"),
            stdout_path,
            stderr_path,
            status,
            error_message,
        )

        with psycopg.connect(self._url, row_factory=dict_row) as conn:
            if existing:
                row = conn.execute(
                    """
                    UPDATE model_artifacts
                    SET model_task_id = %s,
                        model_version = %s,
                        manifest_path = %s,
                        manifest_json = %s::jsonb,
                        project_root = %s,
                        output_dir = %s,
                        lancedb_uri = %s,
                        entities_path = %s,
                        relationships_path = %s,
                        text_units_path = %s,
                        community_reports_path = %s,
                        entity_count = %s,
                        relationship_count = %s,
                        text_unit_count = %s,
                        community_count = %s,
                        community_report_count = %s,
                        stdout_path = %s,
                        stderr_path = %s,
                        status = %s,
                        error_message = %s,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, task_id, project_id, status, model_task_id, manifest_path, output_dir
                    """,
                    (*row_values, str(existing["id"])),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    INSERT INTO model_artifacts (
                        task_id, project_id, model_task_id, model_version,
                        manifest_path, manifest_json, project_root, output_dir, lancedb_uri,
                        entities_path, relationships_path, text_units_path, community_reports_path,
                        entity_count, relationship_count, text_unit_count,
                        community_count, community_report_count,
                        stdout_path, stderr_path, status, error_message
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, task_id, project_id, status, model_task_id, manifest_path, output_dir
                    """,
                    (
                        str(task_id),
                        str(project_id),
                        *row_values,
                    ),
                ).fetchone()
            conn.commit()
        if not row:
            raise RuntimeError("upsert model_artifacts returned no row")
        return dict(row)
