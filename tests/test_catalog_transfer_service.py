"""Tests for the catalog transfer HTTP service."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from rlm_proxy.catalog_store import SlotRegistry
from rlm_proxy.catalog_transfer_service import create_catalog_transfer_app
from rlm_proxy.models import SlotCatalog, SlotDefinition
import rlm_proxy.catalog_transfer_service as service


def test_export_and_import_round_trip(tmp_path, monkeypatch) -> None:
    source = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    source.replace(SlotCatalog(slots=[SlotDefinition(slug="engineering")]))
    monkeypatch.setattr(service, "registry", source)
    client = TestClient(create_catalog_transfer_app())

    exported = client.get("/v1/rlm/catalog/export")
    assert exported.status_code == 200
    source.replace(SlotCatalog(slots=[]), expected_version=1)

    imported = client.post(
        "/v1/rlm/catalog/import",
        json={"payload": exported.text, "expected_version": 2},
    )
    assert imported.status_code == 200
    assert imported.json()["slots"][0]["slug"] == "engineering"


def test_import_reports_stale_version(tmp_path, monkeypatch) -> None:
    source = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    source.replace(SlotCatalog(slots=[]))
    monkeypatch.setattr(service, "registry", source)
    client = TestClient(create_catalog_transfer_app())
    payload = client.get("/v1/rlm/catalog/export").text

    response = client.post(
        "/v1/rlm/catalog/import",
        json={"payload": payload, "expected_version": 0},
    )
    assert response.status_code == 409
