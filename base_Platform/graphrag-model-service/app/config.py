"""
GraphRAG Model Service — 集中配置。

环境变量（均可选，除 RUN_ROOT 外均有默认值）：
  GRAPHRAG_RUN_ROOT          任务根目录，默认 ./graphrag_runs（相对服务根目录解析）
  GRAPHRAG_CLI               graphrag 可执行文件，默认 graphrag
  GRAPHRAG_SETTINGS_TEMPLATE settings.yaml 模板路径
  GRAPHRAG_PROMPTS_DIR       含 prompts/*.txt 的目录，整棵复制到任务根 prompts/
  GRAPHRAG_MODEL_VERSION     写入 manifest，默认 dev
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(env_name: str, default_relative: str) -> Path:
    raw = (os.getenv(env_name) or "").strip()
    p = Path(raw or default_relative)
    return p.resolve() if p.is_absolute() else (_SERVICE_ROOT / p).resolve()


def _optional_prompts_dir() -> Path | None:
    raw = (os.getenv("GRAPHRAG_PROMPTS_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (_SERVICE_ROOT / p).resolve()


@dataclass(frozen=True)
class AppConfig:
    run_root: Path
    graphrag_cli: str
    settings_template: Path
    prompts_dir: Path | None
    model_version: str


def load_config() -> AppConfig:
    cli = (os.getenv("GRAPHRAG_CLI") or "graphrag").strip() or "graphrag"
    ver = (os.getenv("GRAPHRAG_MODEL_VERSION") or "dev").strip() or "dev"
    return AppConfig(
        run_root=_resolve_path("GRAPHRAG_RUN_ROOT", "graphrag_runs"),
        graphrag_cli=cli,
        settings_template=_resolve_path(
            "GRAPHRAG_SETTINGS_TEMPLATE",
            str(Path("templates") / "settings.yaml"),
        ),
        prompts_dir=_optional_prompts_dir(),
        model_version=ver,
    )


# 模块级单例，供各模块导入
config = load_config()
