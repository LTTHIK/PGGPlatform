"""校验 GraphRAG 索引产物：核心 Parquet 与 LanceDB 目录。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    ok: bool
    output_dir: Path
    errors: list[str] = field(default_factory=list)
    entities_parquet: Path | None = None
    relationships_parquet: Path | None = None
    text_units_parquet: Path | None = None
    community_reports_parquet: Path | None = None
    lancedb_dir: Path | None = None

    def to_manifest_fragment(self) -> dict:
        return {
            "validation_ok": self.ok,
            "validation_errors": list(self.errors),
            "artifacts": {
                "entities_parquet": _rel(self.entities_parquet),
                "relationships_parquet": _rel(self.relationships_parquet),
                "text_units_parquet": _rel(self.text_units_parquet),
                "community_reports_parquet": _rel(self.community_reports_parquet),
                "lancedb_dir": _rel(self.lancedb_dir),
            },
        }


def _rel(p: Path | None) -> str | None:
    if p is None:
        return None
    return str(p)


def validate_task_output(task_root: Path) -> ValidationResult:
    """
    默认假定 GraphRAG `output_storage.base_dir` 为相对路径 `output`。
    校验若干关键产物是否存在。
    """
    out = (task_root / "output").resolve()
    errors: list[str] = []

    entities = out / "entities.parquet"
    relationships = out / "relationships.parquet"
    text_units = out / "text_units.parquet"
    community_reports = out / "community_reports.parquet"
    lancedb = out / "lancedb"

    if not out.is_dir():
        errors.append(f"output directory missing: {out}")

    if not entities.is_file():
        errors.append(f"missing: {entities}")
    if not relationships.is_file():
        errors.append(f"missing: {relationships}")
    if not text_units.is_file():
        errors.append(f"missing: {text_units}")
    if not community_reports.is_file():
        errors.append(f"missing: {community_reports}")
    if not lancedb.is_dir():
        errors.append(f"missing or not a directory: {lancedb}")

    ok = len(errors) == 0
    return ValidationResult(
        ok=ok,
        output_dir=out,
        errors=errors,
        entities_parquet=entities if entities.is_file() else None,
        relationships_parquet=relationships if relationships.is_file() else None,
        text_units_parquet=text_units if text_units.is_file() else None,
        community_reports_parquet=community_reports if community_reports.is_file() else None,
        lancedb_dir=lancedb if lancedb.is_dir() else None,
    )
