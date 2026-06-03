# Copyright (C) 2025 Microsoft
# Licensed under the MIT License

"""Workflow profiling utilities."""

import time
from types import TracebackType
from typing import Self

from graphrag.index.typing.stats import WorkflowMetrics


class WorkflowProfiler:
    """Context manager for profiling workflow execution.

    Records per-workflow wall-clock time only. Memory tracing via tracemalloc
    is disabled: it can hang the pipeline on create_base_text_units (pandas/pyarrow).

    Example
    -------
        with WorkflowProfiler() as profiler:
            result = await workflow_function(config, context)
        metrics = profiler.metrics
    """

    def __init__(self) -> None:
        self._start_time: float = 0.0
        self._elapsed: float = 0.0

    def __enter__(self) -> Self:
        """Start profiling: record start time."""
        self._start_time = time.time()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop profiling: capture elapsed time."""
        self._elapsed = time.time() - self._start_time

    @property
    def metrics(self) -> WorkflowMetrics:
        """Return collected metrics as a WorkflowMetrics dataclass."""
        return WorkflowMetrics(
            overall=self._elapsed,
            peak_memory_bytes=0,
            memory_delta_bytes=0,
            tracemalloc_overhead_bytes=0,
        )
