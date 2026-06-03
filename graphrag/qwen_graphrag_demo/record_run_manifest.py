#!/usr/bin/env python3
"""
在每次全量建库、增量 update 或预处理完成后生成运行清单 JSON，便于追溯模型、路径与产物规模。

示例（项目根 qwen_graphrag_demo 下）：
  python record_run_manifest.py
  python record_run_manifest.py --output-dir ./output --task-id task_20260506_1
  python record_run_manifest.py --output-dir ./output_increment_xxx/yyy/delta --project-root .

环境变量（可选）：
  GRAPHRAG_PROJECT_ID   默认 qwen_graphrag_demo
  GRAPHRAG_MODEL_VERSION  写入 model_version
  GRAPHRAG_MODEL_TASK_ID  写入 model_task_id（不设则用 task_id）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


_DEMO_ROOT = Path(__file__).resolve().parent


def _try_load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_models(cfg: dict | None) -> dict:
    out: dict = {"completion": None, "embedding": None, "workflows": None}
    if not cfg:
        return out
    try:
        cm = cfg.get("completion_models") or {}
        default = cm.get("default_completion_model") or {}
        out["completion"] = {
            "type": default.get("type"),
            "model_provider": default.get("model_provider"),
            "model": default.get("model"),
        }
        em = cfg.get("embedding_models") or {}
        ed = em.get("default_embedding_model") or {}
        out["embedding"] = {
            "type": ed.get("type"),
            "model_provider": ed.get("model_provider"),
            "model": ed.get("model"),
        }
        out["workflows"] = cfg.get("workflows")
        out["embed_text_names"] = (cfg.get("embed_text") or {}).get("names")
    except Exception:
        pass
    return out


def _parquet_row_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        import pyarrow.parquet as pq  # type: ignore

        meta = pq.ParquetFile(path).metadata
        if meta is None:
            return None
        return int(meta.num_rows)
    except Exception:
        try:
            import pandas as pd  # type: ignore

            return int(len(pd.read_parquet(path)))
        except Exception:
            return None


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _walk_output_files(
    out_dir: Path, *, max_files: int
) -> tuple[list[dict], bool, int, int]:
    """返回 (file_entries, truncated, total_files, total_bytes)。"""
    entries: list[dict] = []
    total_files = 0
    total_bytes = 0
    truncated = False
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        total_files += 1
        try:
            sz = p.stat().st_size
        except OSError:
            sz = 0
        total_bytes += sz
        if len(entries) < max_files:
            rel = str(p.relative_to(out_dir)).replace("\\", "/")
            entries.append(
                {
                    "relative": rel,
                    "absolute": str(p.resolve()),
                    "size_bytes": sz,
                }
            )
        else:
            truncated = True
    return entries, truncated, total_files, total_bytes


def _graphrag_version() -> str | None:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "graphrag", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 GraphRAG 运行清单 JSON")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_DEMO_ROOT,
        help="项目根（含 settings.yaml、input、output）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="索引产物目录；默认 <project-root>/output",
    )
    parser.add_argument(
        "--input-normalized",
        type=Path,
        default=None,
        help="标准化文本目录；默认 <project-root>/input/normalized",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("GRAPHRAG_PROJECT_ID", "qwen_graphrag_demo"),
        help="业务项目 ID（可用环境变量 GRAPHRAG_PROJECT_ID）",
    )
    parser.add_argument(
        "--task-id",
        default="",
        help="任务 ID；不设则自动生成 task_UTC时间戳",
    )
    parser.add_argument(
        "--model-task-id",
        default=os.environ.get("GRAPHRAG_MODEL_TASK_ID", ""),
        help="模型侧任务 ID；不设则与 task_id 相同",
    )
    parser.add_argument(
        "--model-version",
        default=os.environ.get("GRAPHRAG_MODEL_VERSION", "graphrag-qwen-demo"),
        help="版本/场景标识（可用 GRAPHRAG_MODEL_VERSION）",
    )
    parser.add_argument(
        "--success",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否标记 success（默认 true；失败时用 --no-success）",
    )
    parser.add_argument(
        "--stdout-log",
        type=Path,
        default=None,
        help="标准输出日志路径（若有重定向）",
    )
    parser.add_argument(
        "--stderr-log",
        type=Path,
        default=None,
        help="标准错误日志路径",
    )
    parser.add_argument(
        "--indexing-log",
        type=Path,
        default=None,
        help="GraphRAG indexing-engine.log；默认 <project-root>/logs/indexing-engine.log",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="写入的清单路径；默认 <project-root>/run_manifest_<task_id>.json",
    )
    parser.add_argument(
        "--max-output-files",
        type=int,
        default=2000,
        help="output 文件清单最多列出的文件数，超出部分仅统计数量",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="JSON 缩进排版",
    )
    parser.add_argument(
        "--extra-json",
        default="",
        help='合并进根对象的 JSON 字符串，例如 \'{"preprocess_cmd":"python ingest/..."}\'',
    )
    args = parser.parse_args()

    root: Path = args.project_root.resolve()
    out_dir = (args.output_dir or (root / "output")).resolve()
    input_norm = (args.input_normalized or (root / "input" / "normalized")).resolve()
    settings_path = root / "settings.yaml"
    logs_dir = root / "logs"
    indexing_log = (
        args.indexing_log
        if args.indexing_log is not None
        else (logs_dir / "indexing-engine.log")
    )

    task_id = args.task_id.strip() or (
        "task_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    model_task_id = args.model_task_id.strip() or task_id
    out_json = args.out_json or (root / f"run_manifest_{task_id}.json")

    cfg = _try_load_yaml(settings_path)
    models = _extract_models(cfg)

    artifacts: dict[str, str | None] = {}
    for name in (
        "entities",
        "relationships",
        "text_units",
        "documents",
        "communities",
        "community_reports",
    ):
        p = out_dir / f"{name}.parquet"
        artifacts[name] = str(p) if p.is_file() else None

    stats = {
        "entity_count": _parquet_row_count(out_dir / "entities.parquet"),
        "relationship_count": _parquet_row_count(out_dir / "relationships.parquet"),
        "text_unit_count": _parquet_row_count(out_dir / "text_units.parquet"),
        "document_count": _parquet_row_count(out_dir / "documents.parquet"),
        "community_count": _parquet_row_count(out_dir / "communities.parquet"),
        "community_report_count": _parquet_row_count(
            out_dir / "community_reports.parquet"
        ),
    }

    file_entries, truncated, total_files, total_bytes = _walk_output_files(
        out_dir, max_files=max(1, args.max_output_files)
    )

    graphml = out_dir / "graph.graphml"
    lancedb_dir = out_dir / "lancedb"

    manifest: dict = {
        "success": bool(args.success),
        "model_task_id": model_task_id,
        "model_version": args.model_version,
        "project_id": args.project_id,
        "task_id": task_id,
        "task_uuid": str(uuid.uuid4()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "input_dir": str(input_norm),
        "output_dir": str(out_dir),
        "lancedb_uri": str(lancedb_dir.resolve()) if lancedb_dir.is_dir() else None,
        "settings_yaml": str(settings_path) if settings_path.is_file() else None,
        "settings_sha256": _sha256_file(settings_path),
        "graphrag_cli_version": _graphrag_version(),
        "models_config": models,
        "artifacts": artifacts,
        "artifacts_graphml": str(graphml) if graphml.is_file() else None,
        "stats": stats,
        "output_scan": {
            "listed_files": len(file_entries),
            "total_files_under_output": total_files,
            "total_bytes_under_output": total_bytes,
            "list_truncated": truncated,
            "files": file_entries,
        },
        "logs": {
            "indexing_engine": str(indexing_log.resolve())
            if indexing_log.is_file()
            else None,
            "query": str((logs_dir / "query.log").resolve())
            if (logs_dir / "query.log").is_file()
            else None,
            "stdout": str(args.stdout_log.resolve()) if args.stdout_log else None,
            "stderr": str(args.stderr_log.resolve()) if args.stderr_log else None,
        },
        "generator_script": str(Path(__file__).resolve()),
    }

    if args.extra_json.strip():
        try:
            extra = json.loads(args.extra_json)
            if isinstance(extra, dict):
                manifest.update(extra)
        except json.JSONDecodeError as e:
            print(f"无效 --extra-json: {e}", file=sys.stderr)
            return 1

    # 若未显式关闭 success，则根据关键产物推断
    if args.success and not (out_dir / "entities.parquet").is_file():
        manifest["success"] = False
        manifest["success_note"] = "未找到 entities.parquet"

    indent = 2 if args.pretty else None
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )
    print(str(out_json.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
