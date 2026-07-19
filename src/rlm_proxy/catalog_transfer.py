"""Deterministic catalog import, export, and SQLite backup operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from .catalog_store import SlotRegistry
from .models import SlotCatalog

EXPORT_FORMAT = "rlm-slot-catalog"
EXPORT_VERSION = 1


def export_catalog(registry: SlotRegistry) -> bytes:
    """Serialize one catalog snapshot with stable ordering and metadata."""
    catalog = registry.snapshot()
    envelope: Dict[str, Any] = {
        "format": EXPORT_FORMAT,
        "export_version": EXPORT_VERSION,
        "schema_version": 1,
        "catalog_version": catalog.version,
        "catalog": catalog.model_dump(exclude={"version"}),
    }
    return (json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def import_catalog(
    registry: SlotRegistry,
    payload: bytes,
    *,
    expected_version: Optional[int] = None,
) -> SlotCatalog:
    """Validate and atomically replace the current catalog from an export."""
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("catalog import must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("catalog import root must be an object")
    if value.get("format") != EXPORT_FORMAT:
        raise ValueError("unsupported catalog export format")
    if value.get("export_version") != EXPORT_VERSION:
        raise ValueError("unsupported catalog export version")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported catalog schema version")
    try:
        catalog = SlotCatalog.model_validate(value["catalog"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("catalog export contains an invalid catalog") from exc
    return registry.replace(catalog, expected_version=expected_version)


def backup_catalog_database(registry: SlotRegistry, destination: Path) -> Path:
    """Create a consistent SQLite backup without stopping the registry."""
    if registry.path == ":memory:":
        raise ValueError("in-memory catalogs cannot be backed up by path")
    destination = destination.expanduser().resolve()
    source = Path(registry.path).expanduser().resolve()
    if destination == source:
        raise ValueError("backup destination must differ from the catalog database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as target:
        source_connection.backup(target)
    return destination
