"""Tests for the browser-facing catalog editor controller."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from rlm_proxy.catalog_editor import CatalogEditorController


class FakeCatalogClient:
    def __init__(self) -> None:
        self.catalog: Dict[str, Any] = {"version": 1, "slots": []}

    def get_catalog(self) -> Dict[str, Any]:
        return dict(self.catalog)

    def replace_catalog(self, catalog: Dict[str, Any]) -> Dict[str, Any]:
        self.catalog = {"version": 2, "slots": list(catalog["slots"])}
        return dict(self.catalog)

    def append_turn(
        self,
        slot_slug: str,
        workstream_slug: str,
        role: str,
        content: str,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {"version": int(expected_version or 0) + 1, "slots": []}

    def delete_workstream(
        self,
        slot_slug: str,
        workstream_slug: str,
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {"version": int(expected_version or 0) + 1, "slots": []}


def test_refresh_and_replace_preserve_versions() -> None:
    controller = CatalogEditorController(FakeCatalogClient())  # type: ignore[arg-type]
    assert controller.refresh().version == 1
    assert controller.replace([{"slug": "engineering", "workstreams": []}], 1).version == 2


def test_append_turn_requires_content() -> None:
    controller = CatalogEditorController(FakeCatalogClient())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="required"):
        controller.append_turn("engineering", "release", "user", " ", 1)


def test_delete_workstream_returns_new_version() -> None:
    controller = CatalogEditorController(FakeCatalogClient())  # type: ignore[arg-type]
    assert controller.delete_workstream("engineering", "release", 4).version == 5
