"""Tests for catalog import, export, and backup operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from rlm_proxy.catalog_store import SlotRegistry
from rlm_proxy.catalog_transfer import backup_catalog_database, export_catalog, import_catalog
from rlm_proxy.models import SlotCatalog, SlotDefinition, WorkstreamDefinition


def _registry(path: Path) -> SlotRegistry:
    registry = SlotRegistry(str(path))
    registry.replace(
        SlotCatalog(
            slots=[
                SlotDefinition(
                    slug="engineering",
                    workstreams=[WorkstreamDefinition(slug="release")],
                )
            ]
        )
    )
    return registry


def test_export_is_deterministic(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "catalog.sqlite3")
    first = export_catalog(registry)
    second = export_catalog(registry)
    assert first == second
    assert json.loads(first)["catalog_version"] == 1


def test_import_round_trip_increments_target_version(tmp_path: Path) -> None:
    source = _registry(tmp_path / "source.sqlite3")
    target = SlotRegistry(str(tmp_path / "target.sqlite3"))
    restored = import_catalog(target, export_catalog(source), expected_version=0)
    assert restored.version == 1
    assert restored.slots[0].slug == "engineering"


def test_import_rejects_corrupt_payload_without_data_loss(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "catalog.sqlite3")
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        import_catalog(registry, b"not json")
    assert registry.snapshot().slots[0].slug == "engineering"


def test_backup_restores_catalog(tmp_path: Path) -> None:
    registry = _registry(tmp_path / "catalog.sqlite3")
    backup = backup_catalog_database(registry, tmp_path / "backups" / "catalog.sqlite3")
    restored = SlotRegistry(str(backup))
    assert restored.snapshot().version == 1
    assert restored.snapshot().slots[0].workstreams[0].slug == "release"
