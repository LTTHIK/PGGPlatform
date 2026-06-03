import argparse
import json
import re
from pathlib import Path

_DEMO_ROOT = Path(__file__).resolve().parent


def _import_pandas():
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "缺少 pandas，请先在当前环境安装：python -m pip install pandas pyarrow"
        ) from exc
    return pd


def _pick_col(columns, candidates):
    lower_map = {c.lower(): c for c in columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def _bad_text_ratio(series):
    pat = re.compile(r"[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){2,}")
    s = series.fillna("").astype(str)
    if len(s) == 0:
        return 0.0
    bad = s.str.contains(pat) & (~s.str.contains(r"[\u4e00-\u9fff]"))
    return float(bad.mean())


def main():
    parser = argparse.ArgumentParser(description="GraphRAG 质量体检（实体/关系）")
    parser.add_argument(
        "--output-dir",
        default=str(_DEMO_ROOT / "output"),
        help="包含 entities.parquet / relationships.parquet 的目录",
    )
    parser.add_argument(
        "--report",
        default="quality_report.json",
        help="输出 JSON 报告文件名（保存在 output-dir 下）",
    )
    parser.add_argument(
        "--topn",
        type=int,
        default=20,
        help="导出可疑实体和边的 TopN",
    )
    args = parser.parse_args()

    pd = _import_pandas()

    out_dir = Path(args.output_dir)
    entities_path = out_dir / "entities.parquet"
    rel_path = out_dir / "relationships.parquet"

    if not entities_path.exists() or not rel_path.exists():
        raise SystemExit(f"未找到必要文件：{entities_path} 或 {rel_path}")

    entities = pd.read_parquet(entities_path)
    rel = pd.read_parquet(rel_path)

    name_col = _pick_col(entities.columns, ["title", "name", "entity", "id"])
    type_col = _pick_col(entities.columns, ["type", "entity_type", "category"])
    degree_col = _pick_col(entities.columns, ["degree", "rank"])

    src_col = _pick_col(rel.columns, ["source", "src", "from"])
    tgt_col = _pick_col(rel.columns, ["target", "dst", "to"])
    weight_col = _pick_col(rel.columns, ["weight", "score", "confidence", "rank"])
    rel_type_col = _pick_col(rel.columns, ["type", "relation", "predicate", "label"])

    if name_col is None or src_col is None or tgt_col is None:
        raise SystemExit(
            f"列名无法识别。entities列={list(entities.columns)}; relationships列={list(rel.columns)}"
        )

    names = entities[name_col].fillna("").astype(str).str.strip()
    duplicate_ratio = float(names.duplicated().mean()) if len(names) else 0.0
    bad_name_ratio = _bad_text_ratio(names)

    if type_col is not None:
        type_dist = (
            entities[type_col].fillna("UNKNOWN").astype(str).value_counts().head(10).to_dict()
        )
    else:
        type_dist = {"UNKNOWN": int(len(entities))}

    if weight_col is not None:
        w = pd.to_numeric(rel[weight_col], errors="coerce").fillna(0.0)
    else:
        w = pd.Series([1.0] * len(rel))
    low_weight_ratio = float((w < 0.6).mean()) if len(w) else 0.0

    # 可疑边：低权重 + 节点名看起来像乱码
    src = rel[src_col].fillna("").astype(str)
    tgt = rel[tgt_col].fillna("").astype(str)
    bad_name_pat = re.compile(r"^[A-Z\s]{6,}$")
    suspicious_mask = (w < 0.6) | src.str.match(bad_name_pat) | tgt.str.match(bad_name_pat)
    suspicious_edges = rel.loc[suspicious_mask].copy()
    if weight_col is None:
        suspicious_edges["_weight"] = 1.0
        sort_col = "_weight"
    else:
        sort_col = weight_col
    suspicious_edges = suspicious_edges.sort_values(sort_col, ascending=True).head(args.topn)

    suspicious_entities = entities.copy()
    suspicious_entities["_bad"] = names.str.match(bad_name_pat) | names.str.len().lt(2)
    if degree_col is not None:
        suspicious_entities = suspicious_entities.sort_values(degree_col, ascending=False)
    suspicious_entities = suspicious_entities[suspicious_entities["_bad"]].head(args.topn)

    summary = {
        "entities_count": int(len(entities)),
        "relationships_count": int(len(rel)),
        "duplicate_entity_name_ratio": round(duplicate_ratio, 4),
        "bad_entity_name_ratio": round(bad_name_ratio, 4),
        "low_weight_relationship_ratio": round(low_weight_ratio, 4),
        "top_entity_types": type_dist,
        "detected_columns": {
            "entity_name": name_col,
            "entity_type": type_col,
            "entity_degree": degree_col,
            "rel_source": src_col,
            "rel_target": tgt_col,
            "rel_weight": weight_col,
            "rel_type": rel_type_col,
        },
        "tips": [
            "bad_entity_name_ratio > 0.15：优先清洗 OCR 文本并做别名合并",
            "duplicate_entity_name_ratio > 0.1：需要做实体规范化（同名合并）",
            "low_weight_relationship_ratio > 0.4：提高抽取阈值或收紧关系白名单",
        ],
    }

    report_path = out_dir / args.report
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    suspicious_entities_path = out_dir / "suspicious_entities.csv"
    suspicious_edges_path = out_dir / "suspicious_relationships.csv"
    suspicious_entities.to_csv(suspicious_entities_path, index=False, encoding="utf-8")
    suspicious_edges.to_csv(suspicious_edges_path, index=False, encoding="utf-8")

    print("质量体检完成：")
    print(f"- 报告: {report_path}")
    print(f"- 可疑实体: {suspicious_entities_path}")
    print(f"- 可疑关系: {suspicious_edges_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
