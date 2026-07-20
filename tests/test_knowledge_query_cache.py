"""Tests for the bounded knowledge query cache."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

from rlm_proxy.knowledge_query_cache import CachedKnowledgeApiClient


class FakeClient:
    def __init__(self) -> None:
        self.search_calls = 0
        self.deleted = 0

    def search(self, query, **kwargs):
        self.search_calls += 1
        return {"query": query, "calls": self.search_calls, "kwargs": kwargs}

    def delete_document(self, document_id):
        self.deleted += 1
        return {"document_id": document_id}


def test_reuses_identical_query_and_returns_copies() -> None:
    client = FakeClient()
    cached = CachedKnowledgeApiClient(client, ttl_seconds=60.0, clock=lambda: 1.0)

    first = cached.search("rust", limit=4)
    first["calls"] = 99
    second = cached.search("rust", limit=4)

    assert client.search_calls == 1
    assert second["calls"] == 1


def test_mutation_invalidates_cache() -> None:
    client = FakeClient()
    cached = CachedKnowledgeApiClient(client, ttl_seconds=60.0, clock=lambda: 1.0)
    cached.search("rust")
    cached.delete_document("doc")
    cached.search("rust")

    assert client.search_calls == 2
    assert client.deleted == 1


def test_lru_limit_evicts_oldest_entry() -> None:
    client = FakeClient()
    cached = CachedKnowledgeApiClient(
        client, maximum_entries=1, ttl_seconds=60.0, clock=lambda: 1.0
    )
    cached.search("a")
    cached.search("b")
    cached.search("a")

    assert client.search_calls == 3
