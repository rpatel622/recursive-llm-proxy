"""Tests for restart, rotation, and diagnostics behavior."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from rlm_proxy.runtime_diagnostics import RestartPolicy, create_diagnostics_bundle, rotate_log


def test_restart_policy_bounds_attempts_and_delay() -> None:
    policy = RestartPolicy(max_attempts=2, window_seconds=10, base_delay_seconds=2)
    assert policy.delay_for(1) == 2
    assert policy.delay_for(3) == 8
    assert policy.permits([91.0], now=100.0) is True
    assert policy.permits([91.0, 99.0], now=100.0) is False


def test_rotate_log_preserves_bounded_history(tmp_path: Path) -> None:
    path = tmp_path / "service.log"
    path.write_text("first payload", encoding="utf-8")
    assert rotate_log(path, max_bytes=4, backups=2) is True
    assert path.read_text(encoding="utf-8") == ""
    assert (tmp_path / "service.log.1").read_text(encoding="utf-8") == "first payload"


def test_diagnostics_bundle_contains_status_and_logs(tmp_path: Path) -> None:
    log = tmp_path / "service.log"
    log.write_text("healthy", encoding="utf-8")
    output = create_diagnostics_bundle(
        tmp_path / "diagnostics.zip",
        statuses={"knowledge": {"running": True}},
        log_paths=[log],
    )
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read("status.json"))["knowledge"]["running"] is True
        assert archive.read("files/service.log") == b"healthy"
