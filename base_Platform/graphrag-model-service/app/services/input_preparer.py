"""将 local_path 文件整理到任务根下 input/normalized/*.txt。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9._\-]+\.txt$")


def _read_as_utf8_or_fallback(src: Path) -> str:
    raw = src.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def prepare_normalized_inputs(
    task_root: Path,
    *,
    source_local_path: str,
    logical_name: str | None,
) -> Path:
    """
    将单个源文件复制/规范为 UTF-8 文本到 task_root/input/normalized/<name>.txt。

    - 若源为 .txt/.md/.log 等文本扩展名，按文本解码后写入 UTF-8。
    - 其他扩展名：仍尝试按文本读取并写入 .txt（便于统一索引）。
    """
    src = Path(source_local_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {src}")

    norm_dir = task_root / "input" / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)

    if logical_name:
        base = Path(logical_name).name
        if not base.lower().endswith(".txt"):
            base = f"{base}.txt"
    else:
        base = src.name
        if not base.lower().endswith(".txt"):
            base = f"{src.stem}.txt"

    # 防止路径穿越；仅允许简单文件名
    safe = Path(base).name
    if not _SAFE_NAME.match(safe):
        safe = re.sub(r"[^a-zA-Z0-9._\-]", "_", Path(base).stem)[:120] + ".txt"

    dest = (norm_dir / safe).resolve()
    try:
        dest.relative_to(norm_dir.resolve())
    except ValueError as e:
        raise ValueError(f"invalid logical_name / destination: {safe}") from e

    text = _read_as_utf8_or_fallback(src)
    dest.write_text(text, encoding="utf-8", newline="\n")
    return dest


def copy_prompts_bundle(task_root: Path, prompts_source: Path) -> Path | None:
    """将 prompts_source 整棵复制到 task_root/prompts。不存在则返回 None。"""
    if not prompts_source.is_dir():
        return None
    dest = task_root / "prompts"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(prompts_source, dest)
    return dest


def copy_settings_template(task_root: Path, template_path: Path) -> Path:
    """复制 settings.yaml 模板到任务根。"""
    if not template_path.is_file():
        raise FileNotFoundError(f"settings template missing: {template_path}")
    task_root.mkdir(parents=True, exist_ok=True)
    dest = task_root / "settings.yaml"
    shutil.copy2(template_path, dest)
    return dest
