#!/usr/bin/env python3
"""将 GraphRAG 主库/增量库的 entities + relationships 导入 Neo4j，便于用 Browser 交互浏览与 Cypher 查询。

依赖：pip install neo4j pandas pyarrow

默认只写入标签 :Entity 与关系类型 :RELATED（关系在 parquet 中无独立“类型”字段，描述见属性 description）。
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Any

_DEMO_ROOT = Path(__file__).resolve().parent


def _to_neo4j_value(v: Any) -> Any:
    if v is None:
        return None
    try:
        import pandas as pd

        if v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return None
    except ImportError:
        pass
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        import numpy as np

        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            if np.isnan(v):
                return None
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
    except ImportError:
        pass
    if hasattr(v, "item") and callable(v.item):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, (list, tuple)):
        return [_to_neo4j_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _to_neo4j_value(val) for k, val in v.items()}
    return v


def _entity_props(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k == "id":
            continue
        val = _to_neo4j_value(v)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[k] = val
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="GraphRAG parquet → Neo4j（Browser 浏览）")
    parser.add_argument(
        "--output-dir",
        default=str(_DEMO_ROOT / "output"),
        help="含 entities.parquet、relationships.parquet 的目录",
    )
    parser.add_argument(
        "--uri",
        default=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        help="Bolt URI（可用环境变量 NEO4J_URI）",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("NEO4J_USER", "neo4j"),
        help="用户名（NEO4J_USER）",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("NEO4J_PASSWORD", ""),
        help="密码（NEO4J_PASSWORD，勿写进 shell 历史时可仅用环境变量）",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("NEO4J_DATABASE", "neo4j"),
        help="Neo4j 5+ 库名（NEO4J_DATABASE）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="每批 UNWIND 行数",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="导入前删除图中所有带 :Entity 标签的节点及其关系",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读 parquet 并打印统计，不写库",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    ent_path = out_dir / "entities.parquet"
    rel_path = out_dir / "relationships.parquet"
    if not ent_path.is_file():
        print(f"缺少文件: {ent_path}", file=sys.stderr)
        return 1
    if not rel_path.is_file():
        print(f"缺少文件: {rel_path}", file=sys.stderr)
        return 1

    try:
        import pandas as pd
    except ImportError:
        print("需要 pandas：pip install pandas pyarrow", file=sys.stderr)
        return 1

    entities = pd.read_parquet(ent_path)
    relationships = pd.read_parquet(rel_path)

    required_e = {"id", "title"}
    required_r = {"id", "source", "target"}
    ec, rc = set(entities.columns), set(relationships.columns)
    if not required_e <= ec:
        print(f"entities.parquet 缺少列 {required_e - ec}", file=sys.stderr)
        return 1
    if not required_r <= rc:
        print(f"relationships.parquet 缺少列 {required_r - rc}", file=sys.stderr)
        return 1

    title_to_id: dict[str, str] = {}
    dup_titles: set[str] = set()
    for _, row in entities.iterrows():
        tid = str(row["id"])
        title = str(row["title"]).strip()
        if not title:
            continue
        if title in title_to_id and title_to_id[title] != tid:
            dup_titles.add(title)
        elif title not in title_to_id:
            title_to_id[title] = tid

    if dup_titles:
        print(
            f"警告：以下 title 对应多个实体 id，关系将按首次出现的 id 连接："
            f"{sorted(dup_titles)[:20]}{'…' if len(dup_titles) > 20 else ''}",
            file=sys.stderr,
        )

    rel_rows: list[dict[str, Any]] = []
    skipped = 0
    for _, r in relationships.iterrows():
        st = str(r["source"]).strip()
        tt = str(r["target"]).strip()
        sid = title_to_id.get(st)
        tid = title_to_id.get(tt)
        if not sid or not tid:
            skipped += 1
            continue
        props = {
            "graphrag_id": str(r["id"]),
            "source_title": st,
            "target_title": tt,
        }
        for col in ("description", "weight", "combined_degree", "human_readable_id", "text_unit_ids"):
            if col in r.index and r[col] is not None and str(r[col]) != "nan":
                v = _to_neo4j_value(r[col])
                if v is not None:
                    props[col] = v
        rel_rows.append({"source_id": sid, "target_id": tid, "props": props})

    entity_records = []
    for _, row in entities.iterrows():
        d = {k: _to_neo4j_value(row[k]) for k in entities.columns}
        d["graphrag_id"] = str(d.pop("id"))
        entity_records.append(d)

    print(
        f"实体 {len(entity_records)}，关系 {len(rel_rows)}，"
        f"因 title 未匹配跳过的关系 {skipped}"
    )

    if args.dry_run:
        return 0

    if not args.password:
        print("未设置密码：使用 --password 或环境变量 NEO4J_PASSWORD", file=sys.stderr)
        return 1

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("需要 neo4j 驱动：pip install neo4j", file=sys.stderr)
        return 1

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))

    def write_tx(tx: Any, *, clear: bool) -> None:
        if clear:
            tx.run("MATCH (n:Entity) DETACH DELETE n")
        # 分批 MERGE 实体
        bs = max(1, args.batch_size)
        for i in range(0, len(entity_records), bs):
            batch = entity_records[i : i + bs]
            tx.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {graphrag_id: row.graphrag_id})
                SET e += row
                REMOVE e.id
                """,
                rows=batch,
            )
        for i in range(0, len(rel_rows), bs):
            batch = rel_rows[i : i + bs]
            tx.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {graphrag_id: row.source_id})
                MATCH (t:Entity {graphrag_id: row.target_id})
                MERGE (s)-[r:RELATED {graphrag_id: row.props.graphrag_id}]->(t)
                SET r += row.props
                """,
                rows=batch,
            )

    try:
        with driver.session(database=args.database) as session:
            session.execute_write(lambda tx: write_tx(tx, clear=args.clear))
    finally:
        driver.close()

    print("导入完成。打开 Neo4j Browser，例如：")
    print("  MATCH (n:Entity) RETURN n LIMIT 50")
    print("  MATCH (a:Entity)-[r:RELATED]->(b:Entity) RETURN a,r,b LIMIT 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
