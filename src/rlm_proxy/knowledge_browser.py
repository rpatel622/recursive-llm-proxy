"""Browser-facing knowledge management controller over the typed API client."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .ui_clients import KnowledgeApiClient


@dataclass(frozen=True)
class KnowledgeBrowserSnapshot:
    health: Dict[str, Any]
    stats: Dict[str, Any]
    documents: List[Dict[str, Any]]
    jobs: List[Dict[str, Any]]


class KnowledgeBrowserController:
    """Coordinate upload, progress, search, and deletion without storage access."""

    def __init__(self, client: KnowledgeApiClient) -> None:
        self.client = client

    def refresh(self) -> KnowledgeBrowserSnapshot:
        return KnowledgeBrowserSnapshot(
            health=self.client.health(),
            stats=self.client.stats(),
            documents=self.client.list_documents(),
            jobs=self.client.list_jobs(),
        )

    def upload(self, path: Path, media_type: str) -> Dict[str, Any]:
        content = base64.b64encode(path.read_bytes()).decode("ascii")
        return self.client.enqueue_ingestion(path.resolve().as_uri(), media_type, content)

    def search(self, query: str, limit: int = 6) -> Dict[str, Any]:
        if not query.strip():
            raise ValueError("search query is required")
        return self.client.search(query, limit=limit)

    def cancel(self, job_id: str) -> Dict[str, Any]:
        return self.client.cancel_job(job_id)

    def delete(self, document_id: str) -> Dict[str, Any]:
        return self.client.delete_document(document_id)
