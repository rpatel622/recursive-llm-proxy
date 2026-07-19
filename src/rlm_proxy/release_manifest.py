"""Generate and verify deterministic release file manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

MANIFEST_VERSION = 1


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    size: int
    sha256: str


def build_manifest(root: Path, relative_paths: Iterable[str]) -> Dict[str, object]:
    entries: List[ManifestEntry] = []
    for relative in sorted(set(relative_paths)):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        payload = path.read_bytes()
        entries.append(
            ManifestEntry(
                path=relative.replace("\\", "/"),
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    return {
        "manifest_version": MANIFEST_VERSION,
        "files": [entry.__dict__ for entry in entries],
    }


def encode_manifest(manifest: Dict[str, object]) -> bytes:
    return (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def verify_manifest(root: Path, manifest: Dict[str, object]) -> List[str]:
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("unsupported release manifest version")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("release manifest files must be a list")
    failures = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("release manifest entries must be objects")
        relative = str(item.get("path") or "")
        path = root / relative
        if not path.is_file():
            failures.append("missing: %s" % relative)
            continue
        payload = path.read_bytes()
        if len(payload) != int(item.get("size", -1)):
            failures.append("size mismatch: %s" % relative)
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest != str(item.get("sha256") or ""):
            failures.append("hash mismatch: %s" % relative)
    return failures


__all__ = [
    "MANIFEST_VERSION",
    "ManifestEntry",
    "build_manifest",
    "encode_manifest",
    "verify_manifest",
]
