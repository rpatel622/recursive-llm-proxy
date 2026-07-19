from __future__ import annotations

from rlm_proxy.recovery_supervisor import RecoverySupervisor
from rlm_proxy.runtime_coordinator import ManagedRuntimeService, RuntimeCoordinator


def test_reconcile_restarts_failed_service_and_reports_ready() -> None:
    state = {"running": False}

    def status():
        return dict(state)

    def restart():
        state["running"] = True
        return dict(state)

    supervisor = RecoverySupervisor(status=status, restart=restart, sleep=lambda _: None)
    coordinator = RuntimeCoordinator([ManagedRuntimeService("proxy", True, supervisor)])

    snapshot = coordinator.reconcile_once()

    assert snapshot["status"] == "ready"
    assert snapshot["ready"] is True
    assert snapshot["recovery"]["proxy"]["restart_count"] == 1


def test_optional_failure_reports_degraded() -> None:
    required = RecoverySupervisor(
        status=lambda: {"running": True},
        restart=lambda: {"running": True},
        sleep=lambda _: None,
    )
    optional = RecoverySupervisor(
        status=lambda: {"running": False},
        restart=lambda: {"running": False},
        sleep=lambda _: None,
    )
    coordinator = RuntimeCoordinator(
        [
            ManagedRuntimeService("proxy", True, required),
            ManagedRuntimeService("knowledge", False, optional),
        ]
    )

    snapshot = coordinator.reconcile_once()

    assert snapshot["status"] == "degraded"
    assert snapshot["ready"] is True
