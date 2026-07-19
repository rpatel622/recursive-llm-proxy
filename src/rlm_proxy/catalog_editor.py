"""Browser-facing catalog editor controller over the typed API client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .ui_clients import CatalogApiClient, VersionConflictError


@dataclass(frozen=True)
class CatalogEditorSnapshot:
    version: int
    slots: List[Dict[str, Any]]


class CatalogEditorController:
    """Coordinate versioned catalog edits without direct persistence access."""

    def __init__(self, client: CatalogApiClient) -> None:
        self.client = client

    def refresh(self) -> CatalogEditorSnapshot:
        catalog = self.client.get_catalog()
        return CatalogEditorSnapshot(
            version=int(catalog.get("version") or 0),
            slots=[dict(item) for item in catalog.get("slots", [])],
        )

    def replace(self, slots: List[Dict[str, Any]], version: int) -> CatalogEditorSnapshot:
        catalog = self.client.replace_catalog({"version": version, "slots": slots})
        return CatalogEditorSnapshot(
            version=int(catalog.get("version") or 0),
            slots=[dict(item) for item in catalog.get("slots", [])],
        )

    def append_turn(
        self,
        slot_slug: str,
        workstream_slug: str,
        role: str,
        content: str,
        version: int,
    ) -> CatalogEditorSnapshot:
        if not content.strip():
            raise ValueError("turn content is required")
        catalog = self.client.append_turn(
            slot_slug,
            workstream_slug,
            role,
            content,
            expected_version=version,
        )
        return CatalogEditorSnapshot(
            version=int(catalog.get("version") or 0),
            slots=[dict(item) for item in catalog.get("slots", [])],
        )

    def delete_workstream(
        self,
        slot_slug: str,
        workstream_slug: str,
        version: int,
    ) -> CatalogEditorSnapshot:
        catalog = self.client.delete_workstream(
            slot_slug,
            workstream_slug,
            expected_version=version,
        )
        return CatalogEditorSnapshot(
            version=int(catalog.get("version") or 0),
            slots=[dict(item) for item in catalog.get("slots", [])],
        )


__all__ = ["CatalogEditorController", "CatalogEditorSnapshot", "VersionConflictError"]
