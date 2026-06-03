"""
阶段一编排：Step 4–7（staging → GraphRAG HTTP → model_artifacts → 更新 task 状态）。

Step 1–3 在 POST /api/analysis/tasks 创建任务时已完成。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from ..repositories.analysis_repository import AnalysisRepository
from ..repositories.artifact_repository import ArtifactRepository
from ..schemas.analysis import (
    PHASE1_SUCCESS_PROGRESS,
    PHASE1_SUCCESS_STATUS,
    PHASE1_SUCCESS_STEP,
)
from .analysis_file_prepare_service import AnalysisFilePrepareService
from .graphrag_model_client import GraphragModelClient
from .workspace_path_service import WorkspacePathService, project_root_from_task_workspace_path


class AnalysisPipelineService:
    def __init__(
        self,
        *,
        repo: AnalysisRepository | None = None,
        artifacts: ArtifactRepository | None = None,
        prepare: AnalysisFilePrepareService | None = None,
        graphrag: GraphragModelClient | None = None,
    ) -> None:
        self._repo = repo or AnalysisRepository()
        self._artifacts = artifacts or ArtifactRepository()
        self._prepare = prepare or AnalysisFilePrepareService(repo=self._repo)
        self._graphrag = graphrag or GraphragModelClient()

    def run_phase1(self, task_id: UUID, *, skip_staging: bool = False) -> dict[str, Any]:
        """
        执行阶段一 Step 4–7（若 skip_staging=False 则先 staging）。

        返回汇总 JSON，供前端刷新任务状态。
        """
        task = self._repo.get_analysis_task_by_id(task_id)
        if not task:
            raise ValueError("task not found")

        workspace_task_path = (task.get("workspace_task_path") or "").strip()
        if not workspace_task_path:
            raise ValueError("workspace_task_path missing")

        project_root = project_root_from_task_workspace_path(workspace_task_path)
        paths_svc = WorkspacePathService(project_root)
        subdirs = paths_svc.ensure_task_subdirs(str(task_id))
        logs_dir = subdirs["logs"]
        graphrag_out = subdirs["graphrag_out"]

        # Step 4
        if skip_staging:
            files = self._repo.list_analysis_task_files(task_id)
            staged = [
                {
                    "file_record_id": r.get("file_record_id"),
                    "filename": r.get("filename"),
                    "local_path": r.get("local_path"),
                }
                for r in files
                if (r.get("parse_status") == "staged" and r.get("local_path"))
            ]
            if not staged:
                raise ValueError("no staged files; run stage first or set skip_staging=false")
            stage_result = {"input_files": staged, "status": "staged"}
        else:
            stage_result = self._prepare.stage_files(task_id)
            if not stage_result.get("input_files"):
                return {
                    "task_id": str(task_id),
                    "phase": "phase1",
                    "status": "failed",
                    "step": "staging",
                    "detail": stage_result,
                }

        self._repo.update_analysis_task_status(
            task_id,
            status="running",
            progress=30,
            current_step="graphrag_index",
        )
        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="graphrag_started",
            message="submitting index task to GraphRAG service",
            payload={"staged_files": len(stage_result.get("input_files") or [])},
        )

        # Step 5
        source_files = []
        for item in stage_result["input_files"]:
            lp = (item.get("local_path") or "").strip()
            if not lp:
                continue
            source_files.append(
                {
                    "local_path": lp,
                    "logical_name": Path(item.get("filename") or Path(lp).name).name,
                }
            )
        if not source_files:
            raise ValueError("no local paths for GraphRAG")

        try:
            created = self._graphrag.create_index_task(source_files=source_files)
        except Exception as e:  # noqa: BLE001
            self._fail_task(task_id, step="graphrag_submit", error=str(e))
            raise

        model_task_id = str(created.get("model_task_id") or "")
        if not model_task_id:
            self._fail_task(task_id, step="graphrag_submit", error="empty model_task_id")
            raise RuntimeError("GraphRAG returned empty model_task_id")

        self._repo.update_analysis_task_status(
            task_id,
            status="running",
            progress=40,
            current_step="graphrag_polling",
            model_task_id=model_task_id,
            model_status=created.get("status") or "queued",
        )

        stdout_path = logs_dir / "graphrag.stdout.log"
        stderr_path = logs_dir / "graphrag.stderr.log"

        try:
            status_rec = self._graphrag.poll_until_done(model_task_id)
        except Exception as e:  # noqa: BLE001
            self._fail_task(
                task_id,
                step="graphrag_poll",
                error=str(e),
                model_task_id=model_task_id,
            )
            raise

        try:
            logs = self._graphrag.get_logs(model_task_id)
            stdout_path.write_text(logs.get("stdout") or "", encoding="utf-8")
            stderr_path.write_text(logs.get("stderr") or "", encoding="utf-8")
        except Exception:
            pass

        st = (status_rec.get("status") or "").lower()
        graphrag_task_root = status_rec.get("task_root")

        if st != "completed":
            msg = status_rec.get("message") or f"GraphRAG status={st}"
            self._artifacts.upsert_from_manifest(
                task_id=task_id,
                project_id=UUID(str(task["project_id"])),
                model_task_id=model_task_id,
                manifest={"status": st, "message": msg, "task_root": graphrag_task_root},
                manifest_path="",
                graphrag_out_dir=str(graphrag_out),
                logs_dir=str(logs_dir),
                status="failed",
                error_message=msg,
            )
            self._fail_task(
                task_id,
                step="graphrag_run",
                error=msg,
                model_task_id=model_task_id,
                model_status=st,
            )
            return {
                "task_id": str(task_id),
                "phase": "phase1",
                "status": "failed",
                "model_task_id": model_task_id,
                "graphrag_status": st,
                "message": msg,
            }

        # Step 6
        art_body = self._graphrag.get_artifacts(model_task_id)
        manifest = art_body.get("manifest") or {}

        platform_manifest_path = graphrag_out / "artifact_manifest.json"
        platform_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if graphrag_task_root:
            link_file = graphrag_out / "graphrag_service_task_root.txt"
            link_file.write_text(str(graphrag_task_root), encoding="utf-8")

        self._artifacts.upsert_from_manifest(
            task_id=task_id,
            project_id=UUID(str(task["project_id"])),
            model_task_id=model_task_id,
            manifest=manifest,
            manifest_path=str(platform_manifest_path),
            graphrag_out_dir=str(graphrag_out),
            logs_dir=str(logs_dir),
            status="completed",
        )

        # Step 6b：回填 8090 normalized txt 路径（不复制到平台 graphrag_input/）
        backfill: list[dict[str, Any]] = []
        if graphrag_task_root:
            backfill = self._backfill_graphrag_input_paths(task_id, graphrag_task_root)

        # Step 7
        self._repo.update_analysis_task_status(
            task_id,
            status=PHASE1_SUCCESS_STATUS,
            progress=PHASE1_SUCCESS_PROGRESS,
            current_step=PHASE1_SUCCESS_STEP,
            error_message=None,
            model_task_id=model_task_id,
            model_status="completed",
            finished=True,
        )
        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="phase1_completed",
            message="GraphRAG index completed; model_artifacts written",
            payload={
                "model_task_id": model_task_id,
                "manifest_path": str(platform_manifest_path),
                "graphrag_task_root": graphrag_task_root,
                "graphrag_input_backfill": backfill,
            },
        )

        return {
            "task_id": str(task_id),
            "phase": "phase1",
            "status": PHASE1_SUCCESS_STATUS,
            "model_task_id": model_task_id,
            "manifest_path": str(platform_manifest_path),
            "graphrag_output_dir": str(graphrag_out),
            "graphrag_service_task_root": graphrag_task_root,
        }

    def _backfill_graphrag_input_paths(
        self,
        task_id: UUID,
        graphrag_task_root: str | Path,
    ) -> list[dict[str, Any]]:
        norm_dir = Path(graphrag_task_root).resolve() / "input" / "normalized"
        if not norm_dir.is_dir():
            return []

        norm_files = sorted(norm_dir.glob("*.txt"))
        task_files = self._repo.list_analysis_task_files(task_id)
        updates: list[dict[str, Any]] = []

        for row in task_files:
            fname = str(row.get("filename") or "")
            stem = Path(fname).stem
            match = next(
                (p for p in norm_files if stem and stem in p.stem),
                norm_files[0] if len(norm_files) == 1 and len(task_files) == 1 else None,
            )
            if not match and norm_files:
                match = norm_files[0]
            if not match:
                continue
            path_str = str(match.resolve())
            self._repo.update_analysis_task_file_normalized(
                task_file_id=UUID(str(row["id"])),
                graphrag_input_path=path_str,
                parsed_text_path=path_str,
            )
            updates.append(
                {
                    "task_file_id": str(row["id"]),
                    "graphrag_input_path": path_str,
                }
            )
        return updates

    def _fail_task(
        self,
        task_id: UUID,
        *,
        step: str,
        error: str,
        model_task_id: str | None = None,
        model_status: str | None = None,
    ) -> None:
        self._repo.update_analysis_task_status(
            task_id,
            status="failed",
            progress=0,
            current_step=step,
            error_message=error,
            model_task_id=model_task_id,
            model_status=model_status or "failed",
            finished=True,
        )
        self._repo.insert_analysis_task_event(
            task_id=task_id,
            event_type="phase1_failed",
            message=error,
            payload={"step": step},
        )
