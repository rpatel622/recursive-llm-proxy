"""Deterministic filesystem synchronization over the knowledge job API."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .ui_clients import KnowledgeApiClient


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True)
class SyncResult:
    submitted: List[str]
    unchanged: List[str]
    deleted: List[str]


def fingerprint(path: Path) -> FileFingerprint:
    data = path.read_bytes()
    stat = path.stat()
    return FileFingerprint(
        size=len(data),
        modified_ns=stat.st_mtime_ns,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def scan(root: Path, patterns: Iterable[str] = ("**/*",)) -> Dict[str, FileFingerprint]:
    root = root.expanduser().resolve()
    discovered: Dict[str, FileFingerprint] = {}
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                discovered[relative] = fingerprint(path)
    return discovered


def load_manifest(path: Path) -> Dict[str, FileFingerprint]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    files = value.get("files", {}) if isinstance(value, dict) else {}
    return {
        str(name): FileFingerprint(
            size=int(item["size"]),
            modified_ns=int(item["modified_ns"]),
            sha256=str(item["sha256"]),
        )
        for name, item in files.items()
    }


def save_manifest(path: Path, files: Dict[str, FileFingerprint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "rlm-knowledge-sync",
        "version": 1,
        "files": {name: asdict(files[name]) for name in sorted(files)},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def synchronize(
    client: KnowledgeApiClient,
    root: Path,
    manifest_path: Path,
    *,
    source_prefix: Optional[str] = None,
) -> SyncResult:
    root = root.expanduser().resolve()
    previous = load_manifest(manifest_path)
    current = scan(root)
    submitted: List[str] = []
    unchanged: List[str] = []

    for relative, current_fingerprint in current.items():
        if previous.get(relative) == current_fingerprint:
            unchanged.append(relative)
            continue
        path = root / relative
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        source_uri = f"{source_prefix.rstrip('/')}/{relative}" if source_prefix else path.as_uri()
        client.enqueue_ingestion(
            source_uri,
            media_type,
            base64.b64encode(path.read_bytes()).decode("ascii"),
        )
        submitted.append(relative)

    deleted = sorted(set(previous) - set(current))
    save_manifest(manifest_path, current)
    return SyncResult(sorted(submitted), sorted(unchanged), deleted)
