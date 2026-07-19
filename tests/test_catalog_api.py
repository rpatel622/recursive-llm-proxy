"""API tests for append-oriented catalog mutations."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import rlm_proxy.routing as routing
from rlm_proxy.app import create_app
from rlm_proxy.catalog_store import SlotRegistry
from rlm_proxy.models import SlotCatalog, SlotDefinition, WorkstreamDefinition


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    registry = SlotRegistry(str(tmp_path / "catalog.sqlite3"))
    registry.replace(
        SlotCatalog(
            slots=[
                SlotDefinition(
                    slug="engineering",
                    workstreams=[WorkstreamDefinition(slug="deployment")],
                )
            ]
        )
    )
    monkeypatch.setattr(routing, "registry", registry)
    monkeypatch.setattr("rlm_proxy.catalog_api.registry", registry)
    return TestClient(create_app())


def test_append_turn_returns_new_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/rlm/slots/engineering/workstreams/deployment/turns",
        json={"role": "user", "content": "Ship the release", "expected_version": 1},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 2
    turns = response.json()["slots"][0]["workstreams"][0]["turns"]
    assert turns[0]["content"] == "Ship the release"
    assert response.headers["etag"] == '"2"'


def test_append_turn_rejects_stale_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/v1/rlm/slots/engineering/workstreams/deployment/turns",
        json={"role": "user", "content": "Ship", "expected_version": 0},
    )

    assert response.status_code == 409
    assert "version conflict" in response.json()["detail"]["message"]


def test_delete_workstream_supports_if_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    response = client.request(
        "DELETE",
        "/v1/rlm/slots/engineering/workstreams/deployment",
        headers={"If-Match": '"1"'},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["slots"][0]["workstreams"] == []
