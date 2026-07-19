"""HTTP gateway adding collection, namespace, and metadata filters to knowledge search."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

_COLLECTION_KEY = "rlm.collection"
_NAMESPACE_KEY = "rlm.namespace"


class ScopedSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    collection: Optional[str] = None
    namespace: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    candidate_limit: int = Field(default=48, ge=1)
    limit: int = Field(default=6, ge=1)
    rerank: bool = True
    max_context_chars: int = Field(default=24000, ge=1)


def _matches(hit: Dict[str, Any], request: ScopedSearchRequest) -> bool:
    chunk = hit.get("chunk") if isinstance(hit, dict) else None
    metadata = chunk.get("metadata") if isinstance(chunk, dict) else None
    if not isinstance(metadata, dict):
        metadata = {}
    expected = dict(request.metadata)
    if request.collection is not None:
        expected[_COLLECTION_KEY] = request.collection
    if request.namespace is not None:
        expected[_NAMESPACE_KEY] = request.namespace
    return all(str(metadata.get(key)) == value for key, value in expected.items())


def _bounded_context(hits: list[Dict[str, Any]], maximum: int) -> str:
    parts = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        chunk = hit.get("chunk") or {}
        text = str(chunk.get("text") or "")
        block = f"[{index}] {text}" if text else ""
        if not block or used + len(block) > maximum:
            continue
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def create_scoped_gateway(client: Optional[httpx.AsyncClient] = None) -> FastAPI:
    app = FastAPI(title="RLM scoped knowledge gateway", version="1.0")
    upstream = os.getenv("RLM_KNOWLEDGE_API_BASE", "http://127.0.0.1:8010").rstrip("/")
    http = client or httpx.AsyncClient(timeout=30.0)

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/knowledge/search/scoped")
    async def search(request: ScopedSearchRequest) -> Dict[str, Any]:
        payload = request.model_dump(
            include={"query", "candidate_limit", "limit", "rerank", "max_context_chars"}
        )
        payload["limit"] = max(request.limit, request.candidate_limit)
        try:
            response = await http.post(f"{upstream}/v1/knowledge/search", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
        value = response.json()
        raw_hits = value.get("hits", []) if isinstance(value, dict) else []
        hits = [dict(hit) for hit in raw_hits if isinstance(hit, dict) and _matches(hit, request)]
        hits = hits[: request.limit]
        citations = []
        for index, hit in enumerate(hits, start=1):
            chunk = hit.get("chunk") or {}
            metadata = chunk.get("metadata") or {}
            citations.append(
                {
                    "index": index,
                    "document_id": chunk.get("document_id"),
                    "chunk_id": chunk.get("id"),
                    "source_uri": metadata.get("source_uri"),
                    "title": metadata.get("title"),
                    "score": hit.get("score"),
                }
            )
        return {
            "hits": hits,
            "citations": citations,
            "context": _bounded_context(hits, request.max_context_chars),
            "scope": {
                "collection": request.collection,
                "namespace": request.namespace,
                "metadata": request.metadata,
            },
        }

    return app


app = create_scoped_gateway()
