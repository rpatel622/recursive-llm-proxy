"""Aggregate local service health into one deterministic readiness snapshot."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class HealthCheck:
    name: str
    required: bool
    probe: Callable[[], Dict[str, Any]]


@dataclass(frozen=True)
class HealthResult:
    name: str
    required: bool
    healthy: bool
    latency_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None


def check_stack(checks: Iterable[HealthCheck]) -> Dict[str, Any]:
    results: List[HealthResult] = []
    for check in checks:
        started = time.perf_counter()
        try:
            details = dict(check.probe())
            healthy = details.get("status") in {"ok", "healthy", "ready"}
            result = HealthResult(
                name=check.name,
                required=check.required,
                healthy=healthy,
                latency_ms=(time.perf_counter() - started) * 1000,
                details=details,
            )
        except Exception as exc:
            result = HealthResult(
                name=check.name,
                required=check.required,
                healthy=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                details={},
                error=str(exc),
            )
        results.append(result)

    ready = all(item.healthy for item in results if item.required)
    degraded = ready and any(not item.healthy for item in results if not item.required)
    status = "degraded" if degraded else ("ready" if ready else "unavailable")
    return {
        "status": status,
        "ready": ready,
        "checks": [
            {
                "name": item.name,
                "required": item.required,
                "healthy": item.healthy,
                "latency_ms": round(item.latency_ms, 3),
                "details": item.details,
                "error": item.error,
            }
            for item in results
        ],
    }


__all__ = ["HealthCheck", "HealthResult", "check_stack"]
