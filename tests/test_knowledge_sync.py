"""Tests for deterministic directory synchronization."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

from rlm_proxy.knowledge_sync import load_manifest, synchronize


class RecordingClient:
    def __init__(self) -> None:
        self.sources = []

    def enqueue_ingestion(self, source_uri, media_type, content_base64):
        self.sources.append((source_uri, media_type, content_base64))
        return {"id": str(len(self.sources))}


def test_sync_submits_only_changed_files(tmp_path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    client = RecordingClient()

    first = synchronize(client, root, manifest)
    second = synchronize(client, root, manifest)
    (root / "a.txt").write_text("beta", encoding="utf-8")
    third = synchronize(client, root, manifest)

    assert first.submitted == ["a.txt"]
    assert second.unchanged == ["a.txt"]
    assert third.submitted == ["a.txt"]
    assert len(client.sources) == 2
    assert load_manifest(manifest)["a.txt"].sha256


def test_sync_records_deleted_paths(tmp_path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    manifest = tmp_path / "manifest.json"
    path = root / "gone.md"
    path.write_text("content", encoding="utf-8")
    client = RecordingClient()
    synchronize(client, root, manifest)
    path.unlink()

    result = synchronize(client, root, manifest)
    assert result.deleted == ["gone.md"]
