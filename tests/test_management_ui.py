"""Tests for management UI handler behavior."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("httpx")

import rlm_proxy.management_ui as ui


class FakeCatalog:
    def replace(self, slots, version):
        return type("Snapshot", (), {"slots": slots, "version": version + 1})()


class FakeKnowledge:
    def search(self, query, limit):
        return {"query": query, "limit": limit}


def test_replace_catalog_validates_list(monkeypatch) -> None:
    monkeypatch.setattr(ui, "_controllers", lambda *args: (FakeCatalog(), FakeKnowledge()))
    slots, version, status = ui.replace_catalog("proxy", "key", '[{"slug":"a"}]', 2)
    assert json.loads(slots)[0]["slug"] == "a"
    assert version == 3
    assert status == "Catalog saved"


def test_search_handler_uses_requested_limit(monkeypatch) -> None:
    monkeypatch.setattr(ui, "_controllers", lambda *args: (FakeCatalog(), FakeKnowledge()))
    assert ui.search_knowledge("knowledge", "rust", 4) == {"query": "rust", "limit": 4}
