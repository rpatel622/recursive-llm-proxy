"""Runtime restart decisions, bounded log rotation, and diagnostics bundles."""

from __future__ import annotations

import json
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class RestartPolicy:
    max_attempts: int = 3
    window_seconds: float = 60.0
    base_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 30.0

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("restart attempt must be at least one")
        return min(self.maximum_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))

    def permits(self, restart_times: Iterable[float], now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        recent = [value for value in restart_times if current - value <= self.window_seconds]
        return len(recent) < self.max_attempts


def rotate_log(path: Path, *, max_bytes: int, backups: int) -> bool:
    """Rotate one log file when it exceeds the configured size."""
    if max_bytes <= 0 or backups < 0:
        raise ValueError("log rotation limits must be positive")
    if not path.exists() or path.stat().st_size <= max_bytes:
        return False
    if backups == 0:
        path.write_bytes(b"")
        return True
    oldest = path.with_name(f"{path.name}.{backups}")
    oldest.unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.exists():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))
    path.touch()
    return True


def create_diagnostics_bundle(
    destination: Path,
    *,
    statuses: Dict[str, object],
    log_paths: Iterable[Path],
    manifest_paths: Iterable[Path] = (),
) -> Path:
    """Create a sanitized local diagnostics ZIP without database contents."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("status.json", json.dumps(statuses, indent=2, sort_keys=True) + "\n")
        for path in [*log_paths, *manifest_paths]:
            if path.exists() and path.is_file():
                archive.write(path, arcname=f"files/{path.name}")
    return destination


def policy_metadata(policy: RestartPolicy) -> Dict[str, object]:
    return asdict(policy)
