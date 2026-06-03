#!/usr/bin/env python3
"""按文档时间从 LanceDB 中删除对应 text unit 向量（dry-run 默认开启）。

依据：documents.parquet 的 creation_date（与 graphrag 文本输入一致，通常来自源文件时间）。
详见 README「按时间淘汰旧向量」一节。

截止时间必须由用户显式指定（命令行或环境变量），脚本不会使用任何隐含默认日期。

用法示例：
  python purge_stale_vectors.py --output-dir ./output --cutoff 2024-06-01T00:00:00+00:00
  python purge_stale_vectors.py --output-dir ./output --cutoff-date 2024-06-01 --apply
  GRAPHRAG_PURGE_CUTOFF=2024-06-01T00:00:00Z python purge_stale_vectors.py --output-dir ./output --apply
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import timedelta, timezone
from pathlib import Path

import lancedb
import pandas as pd


def _detect_vector_table(db: lancedb.DB) -> str:
    names = db.table_names()
    for preferred in ("text_unit_text", "vector_index"):
        if preferred in names:
            return preferred
    if not names:
        raise SystemExit(f"LanceDB 中没有任何表：{db}")
    return names[0]


def _sql_quote(s: str) -> str:
    return str(s).replace("'", "''")


def _parse_cutoff_iso(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def _parse_cutoff_date_yyyy_mm_dd(value: str) -> pd.Timestamp:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise SystemExit(
            f"--cutoff-date 须为 YYYY-MM-DD，收到: {value!r}"
        )
    ts = pd.Timestamp(value.strip() + "T00:00:00", tz="UTC")
    return ts


def _delete_ids_in_batches(table, ids: list[str], batch_size: int) -> int:
    removed = 0
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        quoted = ", ".join(f"'{_sql_quote(x)}'" for x in chunk)
        table.delete(f"id IN ({quoted})")
        removed += len(chunk)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="删除「文档过旧」对应的 LanceDB 向量行。"
        " 截止时间须由用户通过命令行或环境变量 GRAPHRAG_PURGE_CUTOFF 显式设置。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="索引输出目录（含 documents.parquet、text_units.parquet、lancedb/）",
    )
    time_group = parser.add_mutually_exclusive_group(required=False)
    time_group.add_argument(
        "--cutoff",
        "--before",
        dest="cutoff_iso",
        metavar="ISO8601",
        default=None,
        help="删除 creation_date **早于**该时刻（UTC）的文档所关联向量；"
        " ISO8601，例如 2024-01-01T00:00:00+00:00 或 2024-06-01Z（与 --before 同义）",
    )
    time_group.add_argument(
        "--cutoff-date",
        dest="cutoff_date",
        metavar="YYYY-MM-DD",
        default=None,
        help="删除 creation_date 早于该日「UTC 零点」的文档所关联向量",
    )
    time_group.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        metavar="N",
        help="删除 creation_date 早于「当前 UTC 时间 − N 天」的文档所关联向量（N 由你指定）",
    )
    parser.add_argument(
        "--vector-table",
        type=str,
        default="",
        help="LanceDB 表名；留空则自动在 text_unit_text / vector_index 中探测",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="单次 DELETE 的 id 数量上限",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行删除；不加本参数时仅统计与打印（dry-run）",
    )
    args = parser.parse_args()

    env_cutoff = os.environ.get("GRAPHRAG_PURGE_CUTOFF", "").strip()
    cli_time_set = sum(
        1
        for v in (args.cutoff_iso, args.cutoff_date, args.max_age_days)
        if v is not None
    )
    if cli_time_set > 1:
        raise SystemExit("请在 --cutoff / --cutoff-date / --max-age-days 中只指定一种时间条件。")
    if cli_time_set == 0 and not env_cutoff:
        raise SystemExit(
            "必须设置截止时间（由用户指定，无默认值）。任选其一：\n"
            "  --cutoff <ISO8601>     例: 2024-06-01T00:00:00+00:00\n"
            "  --cutoff-date YYYY-MM-DD\n"
            "  --max-age-days N       例: 365 表示删掉早于「当前 UTC − N 天」的文档\n"
            "  或环境变量 GRAPHRAG_PURGE_CUTOFF=<ISO8601>（在未传上述参数时生效）"
        )

    out = args.output_dir.resolve()
    docs_path = out / "documents.parquet"
    tu_path = out / "text_units.parquet"
    lance_root = out / "lancedb"

    if not docs_path.is_file():
        raise SystemExit(f"未找到 {docs_path}")
    if not tu_path.is_file():
        raise SystemExit(f"未找到 {tu_path}")
    if not lance_root.is_dir():
        raise SystemExit(f"未找到 LanceDB 目录 {lance_root}")

    if args.cutoff_iso:
        cutoff = _parse_cutoff_iso(args.cutoff_iso)
    elif args.cutoff_date:
        cutoff = _parse_cutoff_date_yyyy_mm_dd(args.cutoff_date)
    elif args.max_age_days is not None:
        cutoff = pd.Timestamp.now(tz=timezone.utc) - timedelta(days=args.max_age_days)
    else:
        cutoff = _parse_cutoff_iso(env_cutoff)

    cutoff_source = (
        "--cutoff"
        if args.cutoff_iso
        else "--cutoff-date"
        if args.cutoff_date
        else "--max-age-days"
        if args.max_age_days is not None
        else "环境变量 GRAPHRAG_PURGE_CUTOFF"
    )

    docs = pd.read_parquet(docs_path)
    if "creation_date" not in docs.columns or "id" not in docs.columns:
        raise SystemExit("documents.parquet 缺少 id 或 creation_date 列")

    doc_times = pd.to_datetime(docs["creation_date"], utc=True, errors="coerce")
    old_mask = doc_times.notna() & (doc_times < cutoff)
    old_doc_ids = set(docs.loc[old_mask, "id"].astype(str))
    missing_date_docs = int(doc_times.isna().sum())

    tu = pd.read_parquet(tu_path)
    if "document_id" not in tu.columns or "id" not in tu.columns:
        raise SystemExit("text_units.parquet 缺少 id 或 document_id 列")

    stale_tu_ids = tu[tu["document_id"].astype(str).isin(old_doc_ids)]["id"].astype(str).tolist()

    db = lancedb.connect(str(lance_root))
    table_name = args.vector_table.strip() or _detect_vector_table(db)
    if table_name not in db.table_names():
        raise SystemExit(f"表 {table_name!r} 不存在，当前有：{db.table_names()}")

    tbl = db.open_table(table_name)
    before_rows = tbl.count_rows()

    print(f"输出目录: {out}")
    print(f"LanceDB 表: {table_name}（当前行数 {before_rows}）")
    print(f"截止时间(UTC): {cutoff}（来源: {cutoff_source}）")
    print(f"无有效 creation_date 的文档数（默认保留）: {missing_date_docs}")
    print(f"判定为过旧的文档数: {len(old_doc_ids)}")
    print(f"将删除的 text_unit 向量行数: {len(stale_tu_ids)}")

    if not stale_tu_ids:
        print("无需删除。")
        return

    if not args.apply:
        print("dry-run：未执行删除。确认后请加 --apply")
        return

    removed = _delete_ids_in_batches(tbl, stale_tu_ids, args.batch_size)
    after_rows = tbl.count_rows()
    print(f"已提交删除请求，涉及 id 数: {removed}；删除后行数: {after_rows}")


if __name__ == "__main__":
    main()
