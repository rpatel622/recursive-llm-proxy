"""Tests for the UI-facing API client boundary."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from rlm_proxy.ui_clients import (  # noqa: E402
    ApiClientConfig,
    CatalogApiClient,
    KnowledgeApiClient,
    ServiceUnavailableError,
    VersionConflictError,
)


def test_catalog_client_sends_expected_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/turns")
        assert b'"expected_version":7' in request.content
        return httpx.Response(200, json={"version": 8, "slots": []})

    client = CatalogApiClient(
        ApiClientConfig("http://test"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.append_turn("slot", "stream", "user", "hello", 7)["version"] == 8


def test_catalog_client_raises_version_conflict() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            409,
            json={"detail": {"message": "catalog version conflict"}},
        )
    )
    client = CatalogApiClient(
        ApiClientConfig("http://test"),
        httpx.Client(transport=transport),
    )
    with pytest.raises(VersionConflictError, match="version conflict"):
        client.delete_workstream("slot", "stream", 1)


def test_knowledge_client_maps_server_failure() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            503,
            json={"error": {"message": "offline"}},
        )
    )
    client = KnowledgeApiClient(
        ApiClientConfig("http://test"),
        httpx.Client(transport=transport),
    )
    with pytest.raises(ServiceUnavailableError, match="offline"):
        client.health()
