import argparse
import re
from pathlib import Path

_DEMO_ROOT = Path(__file__).resolve().parent


def _import_deps():
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise SystemExit("缺少 pandas，请先安装：python -m pip install pandas pyarrow") from exc
    try:
        import networkx as nx
    except Exception as exc:  # pragma: no cover
        raise SystemExit("缺少 networkx，请先安装：python -m pip install networkx") from exc
    return pd, nx


def _pick_col(columns, candidates):
    lower_map = {c.lower(): c for c in columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def _is_bad_entity_name(name: str, strict: bool) -> bool:
    if not name:
        return True
    s = str(name).strip()
    if len(s) < 2:
        return True
    if strict:
        # 严格模式：过滤更多疑似 OCR 噪声
        if re.fullmatch(r"[A-Z\s]{6,}", s):
            return True
        if re.search(r"[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){2,}", s) and not re.search(
            r"[\u4e00-\u9fff]", s
        ):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="清洗 GraphRAG 输出的实体与关系。")
    parser.add_argument(
        "--output-dir",
        default=str(_DEMO_ROOT / "output"),
        help="原始 output 目录（包含 entities.parquet 和 relationships.parquet）",
    )
    parser.add_argument(
        "--clean-dir",
        default=str(_DEMO_ROOT / "output_clean"),
        help="清洗后输出目录",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.0,
        help="过滤低于该阈值的关系权重；0 表示不过滤",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格清洗模式（会过滤更多疑似 OCR 噪声）。",
    )
    parser.add_argument(
        "--min-keep-ratio",
        type=float,
        default=0.3,
        help="清洗后保留实体比例下限；低于该值自动回退到轻度清洗。",
    )
    args = parser.parse_args()

    pd, nx = _import_deps()

    output_dir = Path(args.output_dir)
    clean_dir = Path(args.clean_dir)
    clean_dir.mkdir(parents=True, exist_ok=True)

    entities_path = output_dir / "entities.parquet"
    rel_path = output_dir / "relationships.parquet"
    if not entities_path.exists() or not rel_path.exists():
        raise SystemExit(f"未找到必要文件：{entities_path} 或 {rel_path}")

    entities = pd.read_parquet(entities_path)
    relationships = pd.read_parquet(rel_path)

    name_col = _pick_col(entities.columns, ["title", "name", "entity", "id"])
    src_col = _pick_col(relationships.columns, ["source", "src", "from"])
    tgt_col = _pick_col(relationships.columns, ["target", "dst", "to"])
    weight_col = _pick_col(relationships.columns, ["weight", "score", "confidence", "rank"])

    if name_col is None or src_col is None or tgt_col is None:
        raise SystemExit(
            f"列名无法识别。entities列={list(entities.columns)}; relationships列={list(relationships.columns)}"
        )

    entities = entities.copy()
    entities["_entity_name"] = entities[name_col].fillna("").astype(str).str.strip()
    entities["_is_bad"] = entities["_entity_name"].apply(lambda x: _is_bad_entity_name(x, args.strict))

    clean_entities = entities.loc[~entities["_is_bad"]].copy()
    keep_ratio = (len(clean_entities) / len(entities)) if len(entities) else 0.0
    # 保底：如果删太多，自动回退到轻度清洗（只去空值/超短）
    if keep_ratio < args.min_keep_ratio:
        entities["_is_bad"] = entities["_entity_name"].apply(lambda x: _is_bad_entity_name(x, strict=False))
        clean_entities = entities.loc[~entities["_is_bad"]].copy()
        print(
            f"提示：严格规则保留比例过低({keep_ratio:.2f})，已自动回退到轻度清洗。"
        )
    keep_names = set(clean_entities["_entity_name"].tolist())

    clean_relationships = relationships.copy()
    clean_relationships[src_col] = clean_relationships[src_col].fillna("").astype(str).str.strip()
    clean_relationships[tgt_col] = clean_relationships[tgt_col].fillna("").astype(str).str.strip()

    clean_relationships = clean_relationships[
        clean_relationships[src_col].isin(keep_names)
        & clean_relationships[tgt_col].isin(keep_names)
    ].copy()

    if weight_col is not None and args.min_weight > 0:
        w = pd.to_numeric(clean_relationships[weight_col], errors="coerce").fillna(0.0)
        clean_relationships = clean_relationships[w >= args.min_weight].copy()

    # 导出清洗后的 parquet
    clean_entities_out = clean_dir / "entities.parquet"
    clean_rel_out = clean_dir / "relationships.parquet"
    clean_entities.drop(columns=["_is_bad"], errors="ignore").to_parquet(clean_entities_out, index=False)
    clean_relationships.to_parquet(clean_rel_out, index=False)

    # 同步导出 graphml，便于可视化脚本直接使用
    g = nx.Graph()
    for _, row in clean_relationships.iterrows():
        s = str(row[src_col])
        t = str(row[tgt_col])
        attrs = {}
        if weight_col is not None:
            try:
                attrs["weight"] = float(row[weight_col])
            except Exception:
                attrs["weight"] = 1.0
        else:
            attrs["weight"] = 1.0
        g.add_edge(s, t, **attrs)
    # 补齐无边节点
    for n in keep_names:
        if n not in g:
            g.add_node(n)
    graphml_out = clean_dir / "graph_clean.graphml"
    nx.write_graphml(g, graphml_out)

    removed_entities = int(len(entities) - len(clean_entities))
    removed_rel = int(len(relationships) - len(clean_relationships))

    print("清洗完成：")
    print(f"- 原实体数: {len(entities)} -> 清洗后: {len(clean_entities)} (移除 {removed_entities})")
    print(f"- 原关系数: {len(relationships)} -> 清洗后: {len(clean_relationships)} (移除 {removed_rel})")
    print(f"- 输出实体: {clean_entities_out}")
    print(f"- 输出关系: {clean_rel_out}")
    print(f"- 输出图谱: {graphml_out}")


if __name__ == "__main__":
    main()
