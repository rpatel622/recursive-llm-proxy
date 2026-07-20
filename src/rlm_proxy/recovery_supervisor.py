"""Bounded recovery orchestration for managed local services."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .runtime_diagnostics import RestartPolicy, create_diagnostics_bundle, rotate_log


@dataclass
class RecoveryState:
    restart_times: List[float] = field(default_factory=list)
    last_error: Optional[str] = None
    exhausted: bool = False


class RecoverySupervisor:
    """Restart a failed managed service without hiding repeated crashes."""

    def __init__(
        self,
        *,
        status: Callable[[], Dict[str, object]],
        restart: Callable[[], Dict[str, object]],
        policy: RestartPolicy = RestartPolicy(),
        log_path: Optional[Path] = None,
        diagnostics_path: Optional[Path] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._status = status
        self._restart = restart
        self._policy = policy
        self._log_path = log_path
        self._diagnostics_path = diagnostics_path
        self._sleep = sleep
        self._clock = clock
        self.state = RecoveryState()

    def check_once(self) -> Dict[str, object]:
        snapshot = self._status()
        if snapshot.get("running"):
            self.state.last_error = None
            return snapshot

        now = self._clock()
        if not self._policy.permits(self.state.restart_times, now=now):
            self.state.exhausted = True
            self._write_diagnostics(snapshot)
            return snapshot

        attempt = (
            len(
                [
                    value
                    for value in self.state.restart_times
                    if now - value <= self._policy.window_seconds
                ]
            )
            + 1
        )
        self._sleep(self._policy.delay_for(attempt))
        if self._log_path is not None:
            rotate_log(self._log_path, max_bytes=5_000_000, backups=3)
        try:
            restarted = self._restart()
        except Exception as exc:
            self.state.last_error = str(exc)
            self.state.restart_times.append(self._clock())
            return self._status()

        self.state.restart_times.append(self._clock())
        self.state.last_error = None
        return restarted

    def _write_diagnostics(self, snapshot: Dict[str, object]) -> None:
        if self._diagnostics_path is None:
            return
        logs = [self._log_path] if self._log_path is not None else []
        create_diagnostics_bundle(
            self._diagnostics_path,
            statuses={"service": snapshot, "recovery": self.state.__dict__},
            log_paths=logs,
        )
