"""Small thread-safe in-memory metrics store for the proxy process."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, Optional


class ProxyMetrics:
    """Aggregate process-local request metrics and bounded recent records."""

    def __init__(self, recent_limit: int = 50) -> None:
        if recent_limit <= 0:
            raise ValueError("recent_limit must be greater than zero")
        self._lock = Lock()
        self._started_at = time.time()
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=recent_limit)
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._clarifications = 0
        self._total_latency_ms = 0.0
        self._prompt_tokens = 0
        self._completion_tokens = 0

    def record(
        self,
        *,
        request_id: str,
        status: str,
        latency_ms: float,
        routing: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        stats = stats or {}
        prompt_tokens = int(stats.get("prompt_tokens") or 0)
        completion_tokens = int(stats.get("completion_tokens") or 0)
        record = {
            "request_id": request_id,
            "timestamp": int(time.time()),
            "status": status,
            "latency_ms": round(latency_ms, 2),
            "routing": routing,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "error": error,
        }
        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += latency_ms
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            if status == "ok":
                self._successful_requests += 1
            elif status == "clarify":
                self._clarifications += 1
            else:
                self._failed_requests += 1
            self._recent.appendleft(record)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            average_latency = (
                self._total_latency_ms / self._total_requests if self._total_requests else 0.0
            )
            return {
                "started_at": int(self._started_at),
                "uptime_seconds": max(0, int(time.time() - self._started_at)),
                "total_requests": self._total_requests,
                "successful_requests": self._successful_requests,
                "failed_requests": self._failed_requests,
                "clarifications": self._clarifications,
                "average_latency_ms": round(average_latency, 2),
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "recent": list(self._recent),
            }


metrics = ProxyMetrics()
