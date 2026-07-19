"""Tests for scoped knowledge search filtering."""

from __future__ import annotations

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from rlm_proxy.scoped_knowledge_gateway import create_scoped_gateway


def test_scoped_search_filters_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "chunk": {
                            "id": "a",
                            "document_id": "doc-a",
                            "text": "alpha",
                            "metadata": {"rlm.collection": "team-a"},
                        },
                        "score": 0.9,
                    },
                    {
                        "chunk": {
                            "id": "b",
                            "document_id": "doc-b",
                            "text": "beta",
                            "metadata": {"rlm.collection": "team-b"},
                        },
                        "score": 0.8,
                    },
                ]
            },
        )

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TestClient(create_scoped_gateway(async_client))
    response = client.post(
        "/v1/knowledge/search/scoped",
        json={"query": "a", "collection": "team-a", "limit": 2},
    )

    assert response.status_code == 200
    assert [hit["chunk"]["id"] for hit in response.json()["hits"]] == ["a"]
    assert response.json()["scope"]["collection"] == "team-a"
