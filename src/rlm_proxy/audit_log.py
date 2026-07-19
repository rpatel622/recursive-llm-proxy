"""Append-only JSONL audit events with a verifiable hash chain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: float
    actor: str
    action: str
    resource: str
    outcome: str
    details: Dict[str, Any]
    previous_hash: str
    event_hash: str


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def append(
        self,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ) -> AuditEvent:
        if not actor or not action or not resource or not outcome:
            raise ValueError("actor, action, resource, and outcome are required")
        with self._lock:
            events = self.read()
            previous_hash = events[-1].event_hash if events else ""
            payload = {
                "sequence": len(events),
                "timestamp": time.time() if timestamp is None else timestamp,
                "actor": actor,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "details": details or {},
                "previous_hash": previous_hash,
            }
            encoded = _canonical(payload)
            event = AuditEvent(event_hash=hashlib.sha256(encoded).hexdigest(), **payload)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), sort_keys=True, separators=(",", ":")))
                handle.write("\n")
            return event

    def read(self) -> List[AuditEvent]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(AuditEvent(**json.loads(line)))
        return events

    def verify(self) -> bool:
        previous_hash = ""
        for expected_sequence, event in enumerate(self.read()):
            if event.sequence != expected_sequence or event.previous_hash != previous_hash:
                return False
            payload = asdict(event)
            claimed = str(payload.pop("event_hash"))
            if hashlib.sha256(_canonical(payload)).hexdigest() != claimed:
                return False
            previous_hash = claimed
        return True


def _canonical(value: Dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = ["AuditEvent", "AuditLog"]
