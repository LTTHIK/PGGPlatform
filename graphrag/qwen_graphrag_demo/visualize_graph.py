import argparse
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager
import networkx as nx

_DEMO_ROOT = Path(__file__).resolve().parent


def _pick_cjk_sans_font() -> str | None:
    """在已注册字体中找支持中文的 sans（注册名与「首选列表」常不一致，需模糊匹配）。"""
    keywords = (
        "noto sans cjk",
        "noto serif cjk",
        "source han sans",
        "source han serif",
        "wenquanyi",
        "zen hei",
        "simhei",
        "microsoft yahei",
        "pingfang",
        "stheit",
        "noto cjk",
    )
    seen: set[str] = set()
    for font in font_manager.fontManager.ttflist:
        name = (font.name or "").lower()
        path = (getattr(font, "fname", None) or "").lower()
        blob = f"{name} {path}"
        if any(kw in blob for kw in keywords) and font.name:
            if font.name not in seen:
                seen.add(font.name)
                return font.name
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化 GraphML 知识图谱。")
    parser.add_argument(
        "--graph",
        default=str(_DEMO_ROOT / "output" / "graph.graphml"),
        help="graph.graphml 文件路径",
    )
    parser.add_argument(
        "--out",
        default="graph_preview.png",
        help="输出图片路径",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=300,
        help="节点数超过该阈值时，仅保留最大连通子图。",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=0,
        help="只展示度数最高的前 K 个节点；0 表示不过滤。",
    )
    parser.add_argument(
        "--show-edge-weight",
        action="store_true",
        help="在边上显示 weight（小图推荐）。",
    )
    parser.add_argument(
        "--html-out",
        default="",
        help="可选：导出交互式 HTML（需安装 pyvis）。",
    )
    parser.add_argument(
        "--font",
        default="",
        help="matplotlib 无衬线字体名（须已安装）；不设则自动探测 CJK 字体。例：Noto Sans CJK SC",
    )
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.exists():
        raise FileNotFoundError(
            f"未找到图文件: {graph_path}。"
            " 请先在项目根目录成功跑完 `graphrag index`（会执行到 finalize_graph 并写出 graphml）。"
        )

    g = nx.read_graphml(graph_path)

    if len(g) > args.max_nodes:
        undirected = g.to_undirected()
        largest_cc = max(nx.connected_components(undirected), key=len)
        g = g.subgraph(largest_cc).copy()

    if args.topk and args.topk > 0 and len(g) > args.topk:
        top_nodes = sorted(g.degree, key=lambda x: x[1], reverse=True)[: args.topk]
        g = g.subgraph([node for node, _ in top_nodes]).copy()

    if args.font.strip():
        matplotlib.rcParams["font.sans-serif"] = [args.font.strip(), "DejaVu Sans"]
    else:
        cjk = _pick_cjk_sans_font()
        if cjk:
            matplotlib.rcParams["font.sans-serif"] = [cjk, "DejaVu Sans"]
        else:
            print(
                "提示：未检测到常见中文字体，图中中文可能显示为方块。"
                " 可安装 fonts-noto-cjk 或 fonts-wqy-zenhei，或用 --font 指定已安装字体名。",
                flush=True,
            )
    matplotlib.rcParams["axes.unicode_minus"] = False

    plt.figure(figsize=(14, 10))
    pos = nx.spring_layout(g, k=0.5, iterations=100, seed=42)
    degree = dict(g.degree())
    node_sizes = [50 + degree[n] * 20 for n in g.nodes()]
    edge_weights = []
    for _, _, data in g.edges(data=True):
        w = data.get("weight", 1.0)
        try:
            edge_weights.append(float(w))
        except (TypeError, ValueError):
            edge_weights.append(1.0)
    max_weight = max(edge_weights) if edge_weights else 1.0
    edge_widths = [0.8 + 2.5 * (w / max_weight) for w in edge_weights]

    nx.draw_networkx_nodes(g, pos, node_size=node_sizes, alpha=0.8)
    nx.draw_networkx_edges(g, pos, alpha=0.35, width=edge_widths)
    if len(g) <= 80:
        nx.draw_networkx_labels(g, pos, font_size=8)
    if args.show_edge_weight and len(g.edges()) <= 120:
        labels = {}
        for u, v, data in g.edges(data=True):
            if "weight" in data:
                try:
                    labels[(u, v)] = f"{float(data['weight']):.2f}"
                except (TypeError, ValueError):
                    labels[(u, v)] = str(data["weight"])
        nx.draw_networkx_edge_labels(g, pos, edge_labels=labels, font_size=7)

    # 左上角加统计信息，帮助判断图谱是否“信息不全”
    components = nx.number_connected_components(g.to_undirected()) if len(g) else 0
    avg_degree = sum(degree.values()) / len(degree) if degree else 0.0
    info_text = (
        f"节点: {g.number_of_nodes()}  边: {g.number_of_edges()}  "
        f"连通分量: {components}  平均度: {avg_degree:.2f}"
    )
    plt.title("GraphRAG 知识图谱（结构概览）")
    plt.gcf().text(0.01, 0.98, info_text, ha="left", va="top", fontsize=10)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(args.out, dpi=200)
    print(f"已保存: {Path(args.out).resolve()}")

    if args.html_out:
        try:
            from pyvis.network import Network

            net = Network(height="820px", width="100%", bgcolor="#ffffff", font_color="#222222")
            net.force_atlas_2based()
            for node in g.nodes():
                net.add_node(
                    node,
                    label=str(node),
                    title=f"节点: {node}<br>度数: {degree.get(node, 0)}",
                    value=max(1, degree.get(node, 1)),
                )
            for u, v, data in g.edges(data=True):
                w = data.get("weight", 1.0)
                try:
                    wf = float(w)
                except (TypeError, ValueError):
                    wf = 1.0
                net.add_edge(u, v, value=wf, title=f"weight: {wf:.4f}")
            net.write_html(args.html_out)
            print(f"已保存交互图: {Path(args.html_out).resolve()}")
        except ImportError:
            print("未安装 pyvis，跳过 HTML 导出。安装: python -m pip install pyvis")

    plt.show()


if __name__ == "__main__":
    main()
