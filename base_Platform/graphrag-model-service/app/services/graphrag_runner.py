"""执行 graphrag index 子进程并捕获 stdout/stderr。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import config
from ..schemas import IndexOptions


def build_index_command(task_root: Path, options: IndexOptions | None) -> list[str]:
    opts = options or IndexOptions()
    cmd: list[str] = [
        config.graphrag_cli,
        "index",
        "--root",
        str(task_root.resolve()),
        "--method",
        opts.method,
    ]
    if opts.verbose:
        cmd.append("--verbose")
    if opts.dry_run:
        cmd.append("--dry-run")
    if opts.skip_validation:
        cmd.append("--skip-validation")
    if not opts.cache:
        cmd.extend(["--no-cache"])
    return cmd


def run_graphrag_index(
    task_root: Path,
    *,
    index_options: IndexOptions | None,
    stdout_file: Path,
    stderr_file: Path,
) -> int:
    """
    同步运行 graphrag CLI；退出码 0 表示 CLI 自认为成功。

    stdout/stderr 写入指定文件（覆盖写入）。
    """
    cmd = build_index_command(task_root, index_options)
    stdout_file.parent.mkdir(parents=True, exist_ok=True)
    stderr_file.parent.mkdir(parents=True, exist_ok=True)

    with stdout_file.open("w", encoding="utf-8", errors="replace") as out:  # type: ignore[assignment]
        with stderr_file.open("w", encoding="utf-8", errors="replace") as err:  # type: ignore[assignment]
            proc = subprocess.run(
                cmd,
                cwd=str(task_root.resolve()),
                stdout=out,
                stderr=err,
                text=True,
                timeout=None,
            )
    return int(proc.returncode)
