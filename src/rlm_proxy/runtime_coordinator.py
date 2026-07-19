"""Coordinate active recovery checks and aggregate local stack readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .recovery_supervisor import RecoverySupervisor
from .stack_health import HealthCheck, check_stack


@dataclass(frozen=True)
class ManagedRuntimeService:
    name: str
    required: bool
    supervisor: RecoverySupervisor


class RuntimeCoordinator:
    """Apply one recovery pass and publish a consistent readiness snapshot."""

    def __init__(self, services: Iterable[ManagedRuntimeService]) -> None:
        self.services: List[ManagedRuntimeService] = list(services)

    def reconcile_once(self) -> Dict[str, Any]:
        recovery: Dict[str, Dict[str, object]] = {}
        for service in self.services:
            recovery[service.name] = service.supervisor.check_once()

        checks = [
            HealthCheck(
                service.name,
                service.required,
                lambda name=service.name: self._probe(recovery[name]),
            )
            for service in self.services
        ]
        snapshot = check_stack(checks)
        snapshot["recovery"] = {
            service.name: {
                "restart_count": len(service.supervisor.state.restart_times),
                "last_error": service.supervisor.state.last_error,
                "exhausted": service.supervisor.state.exhausted,
            }
            for service in self.services
        }
        return snapshot

    @staticmethod
    def _probe(status: Dict[str, object]) -> Dict[str, Any]:
        return {
            "status": "ok" if status.get("running") else "unavailable",
            **status,
        }


__all__ = ["ManagedRuntimeService", "RuntimeCoordinator"]
