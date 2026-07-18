"""Tests for durable slot and workstream catalog storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from rlm_proxy.catalog_store import SlotRegistry
from rlm_proxy.models import (
    SlotCatalog,
    SlotDefinition,
    StoredTurn,
    WorkstreamDefinition,
)


def _catalog(version: int | None = None) -> SlotCatalog:
    return SlotCatalog(
        version=version,
        slots=[
            SlotDefinition(
                slug="engineering",
                name="Engineering",
                description="Engineering work",
                workstreams=[
                    WorkstreamDefinition(
                        slug="deployment",
                        name="Deployment",
                        description="Release operations",
                        turns=[StoredTurn(role="user", content="Initial plan")],
                    )
                ],
            )
        ],
    )


def test_catalog_survives_registry_restart(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    first = SlotRegistry(str(path))
    stored = first.replace(_catalog())

    second = SlotRegistry(str(path))
    restored = second.snapshot()

    assert stored.version == 1
    assert restored.version == 1
    assert restored.slots[0].slug == "engineering"
    assert restored.slots[0].workstreams[0].turns[0].content == "Initial plan"


def test_replace_is_atomic_and_increments_version(tmp_path: Path) -> None:
    registry = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    first = registry.replace(_catalog())
    replacement = SlotCatalog(
        slots=[SlotDefinition(slug="research", workstreams=[])],
    )
    second = registry.replace(replacement, expected_version=first.version)

    assert first.version == 1
    assert second.version == 2
    assert [slot.slug for slot in second.slots] == ["research"]


def test_replace_rejects_stale_version_without_data_loss(tmp_path: Path) -> None:
    registry = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    registry.replace(_catalog())

    with pytest.raises(ValueError, match="version conflict"):
        registry.replace(SlotCatalog(slots=[]), expected_version=0)

    snapshot = registry.snapshot()
    assert snapshot.version == 1
    assert snapshot.slots[0].slug == "engineering"


def test_append_turn_is_ordered_and_versioned(tmp_path: Path) -> None:
    registry = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    initial = registry.replace(_catalog())
    updated = registry.append_turn(
        "engineering",
        "deployment",
        StoredTurn(role="assistant", content="Use blue-green deployment"),
        expected_version=initial.version,
    )

    turns = updated.slots[0].workstreams[0].turns
    assert updated.version == 2
    assert [turn.content for turn in turns] == [
        "Initial plan",
        "Use blue-green deployment",
    ]


def test_delete_workstream_cascades_turns(tmp_path: Path) -> None:
    registry = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    initial = registry.replace(_catalog())
    updated = registry.delete_workstream(
        "engineering",
        "deployment",
        expected_version=initial.version,
    )

    assert updated.version == 2
    assert updated.slots[0].workstreams == []
