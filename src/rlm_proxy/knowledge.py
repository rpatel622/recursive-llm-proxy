"""Client and context helpers for the native knowledge service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass(frozen=True)
class KnowledgeResult:
    """Retrieved context and citation metadata."""

    context: str
    citations: List[Dict[str, Any]]
    hits: List[Dict[str, Any]]


async def retrieve_knowledge(
    *,
    api_base: str,
    query: str,
    candidate_limit: int,
    limit: int,
    rerank: bool,
    max_context_chars: int,
    timeout_seconds: float,
) -> KnowledgeResult:
    """Run hybrid retrieval through the native service."""

    endpoint = f"{api_base.rstrip('/')}/v1/knowledge/search"
    payload = {
        "query": query,
        "candidate_limit": candidate_limit,
        "limit": limit,
        "rerank": rerank,
        "max_context_chars": max_context_chars,
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(endpoint, json=payload)
    response.raise_for_status()
    body = response.json()
    return KnowledgeResult(
        context=str(body.get("context") or ""),
        citations=list(body.get("citations") or []),
        hits=list(body.get("hits") or []),
    )


def combine_context(*parts: Optional[str]) -> str:
    """Join non-empty context sections with stable separation."""

    return "\n\n".join(part.strip() for part in parts if part and part.strip())
