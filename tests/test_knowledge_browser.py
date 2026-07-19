"""Tests for the browser-facing knowledge controller."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from rlm_proxy.knowledge_browser import KnowledgeBrowserController


class FakeKnowledgeClient:
    def health(self) -> Dict[str, Any]:
        return {"status": "ok"}

    def stats(self) -> Dict[str, Any]:
        return {"document_count": 1}

    def list_documents(self) -> List[Dict[str, Any]]:
        return [{"document_id": "doc-1"}]

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [{"id": "job-1", "status": "running"}]

    def enqueue_ingestion(self, source_uri: str, media_type: str, content_base64: str) -> Dict[str, Any]:
        return {"source_uri": source_uri, "media_type": media_type, "content_base64": content_base64}

    def search(self, query: str, candidate_limit: int = 24, limit: int = 6, rerank: bool = True, max_context_chars: int = 24000) -> Dict[str, Any]:
        return {"query": query, "limit": limit}

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        return {"id": job_id, "status": "cancelled"}

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        return {"document_id": document_id, "deleted": True}


def test_refresh_combines_service_views() -> None:
    snapshot = KnowledgeBrowserController(FakeKnowledgeClient()).refresh()  # type: ignore[arg-type]
    assert snapshot.health["status"] == "ok"
    assert snapshot.documents[0]["document_id"] == "doc-1"
    assert snapshot.jobs[0]["status"] == "running"


def test_upload_encodes_file(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    result = KnowledgeBrowserController(FakeKnowledgeClient()).upload(path, "text/plain")  # type: ignore[arg-type]
    assert result["content_base64"] == "aGVsbG8="


def test_blank_search_is_rejected() -> None:
    with pytest.raises(ValueError, match="required"):
        KnowledgeBrowserController(FakeKnowledgeClient()).search("   ")  # type: ignore[arg-type]
