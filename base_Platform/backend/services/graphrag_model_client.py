"""
GraphRAG 模型 HTTP 客户端：对接 graphrag-model-service (:8090)。
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests


class GraphragModelClient:
    def __init__(self, base_url: str | None = None, timeout_s: float = 120.0) -> None:
        self.base_url = (base_url or os.getenv("GRAPHRAG_HTTP_BASE_URL") or "").strip().rstrip("/")
        self.timeout_s = timeout_s
        self.poll_interval_s = float(os.getenv("GRAPHRAG_POLL_INTERVAL_S") or "3")
        self.poll_timeout_s = float(os.getenv("GRAPHRAG_POLL_TIMEOUT_S") or "3600")

    def _url(self, path: str) -> str:
        if not self.base_url:
            raise RuntimeError("GRAPHRAG_HTTP_BASE_URL is not configured")
        return f"{self.base_url}{path}"

    def health(self) -> dict[str, Any]:
        if not self.base_url:
            return {"configured": False, "base_url": None}
        r = requests.get(self._url("/api/health"), timeout=30)
        r.raise_for_status()
        body = r.json()
        body["configured"] = True
        body["base_url"] = self.base_url
        return body

    def health_stub(self) -> dict[str, Any]:
        try:
            return self.health()
        except Exception as e:  # noqa: BLE001
            return {
                "configured": bool(self.base_url),
                "base_url": self.base_url or None,
                "detail": str(e),
            }

    def create_index_task(
        self,
        *,
        source_files: list[dict[str, str]],
        index_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"source_files": source_files}
        if index_options:
            payload["index_options"] = index_options
        r = requests.post(
            self._url("/api/graphrag/index-tasks"),
            json=payload,
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        return dict(r.json())

    def get_task_status(self, model_task_id: str) -> dict[str, Any]:
        r = requests.get(
            self._url(f"/api/graphrag/index-tasks/{model_task_id}"),
            timeout=60,
        )
        r.raise_for_status()
        return dict(r.json())

    def poll_until_done(self, model_task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout_s
        while time.monotonic() < deadline:
            rec = self.get_task_status(model_task_id)
            st = (rec.get("status") or "").lower()
            if st in ("completed", "failed"):
                return rec
            time.sleep(self.poll_interval_s)
        raise TimeoutError(
            f"GraphRAG task {model_task_id} did not finish within {self.poll_timeout_s}s"
        )

    def get_artifacts(self, model_task_id: str) -> dict[str, Any]:
        r = requests.get(
            self._url(f"/api/graphrag/index-tasks/{model_task_id}/artifacts"),
            timeout=120,
        )
        r.raise_for_status()
        return dict(r.json())

    def get_logs(self, model_task_id: str) -> dict[str, str]:
        r = requests.get(
            self._url(f"/api/graphrag/index-tasks/{model_task_id}/logs"),
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        return {
            "stdout": str(body.get("stdout") or ""),
            "stderr": str(body.get("stderr") or ""),
        }
