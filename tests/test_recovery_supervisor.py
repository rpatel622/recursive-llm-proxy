"""Tests for bounded managed-service recovery."""

from __future__ import annotations

import zipfile

from rlm_proxy.recovery_supervisor import RecoverySupervisor
from rlm_proxy.runtime_diagnostics import RestartPolicy


def test_restarts_failed_service_with_backoff(tmp_path) -> None:
    running = {"value": False}
    delays = []

    def status():
        return {"running": running["value"]}

    def restart():
        running["value"] = True
        return {"running": True}

    supervisor = RecoverySupervisor(
        status=status,
        restart=restart,
        policy=RestartPolicy(base_delay_seconds=2.0),
        sleep=delays.append,
        clock=lambda: 10.0,
    )

    assert supervisor.check_once()["running"] is True
    assert delays == [2.0]


def test_exhaustion_writes_diagnostics(tmp_path) -> None:
    diagnostics = tmp_path / "diagnostics.zip"
    supervisor = RecoverySupervisor(
        status=lambda: {"running": False, "exit_code": 1},
        restart=lambda: {"running": False},
        policy=RestartPolicy(max_attempts=0),
        diagnostics_path=diagnostics,
        sleep=lambda _: None,
        clock=lambda: 10.0,
    )

    supervisor.check_once()
    assert supervisor.state.exhausted is True
    with zipfile.ZipFile(diagnostics) as archive:
        assert "status.json" in archive.namelist()
