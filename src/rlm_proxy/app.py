"""FastAPI application exposing recursive-llm as an OpenAI-compatible service."""

from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from rlm import RLM
from rlm.errors import RLMError

from .adapter import forwarded_llm_kwargs, split_query_context
from .catalog_api import build_catalog_mutation_router
from .config import Settings, get_settings
from .ingestion import preprocess_dump, should_preprocess
from .knowledge import combine_context, retrieve_knowledge
from .metrics import metrics
from .models import ChatCompletionRequest, IngestionOptions, SlotCatalog
from .routing import (
    build_routed_context,
    clarification_text,
    normalized_catalog,
    registry,
    resolve_route,
)


def _verify_auth(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected_secret = settings.public_api_key
    if expected_secret is None:
        return
    expected = f"Bearer {expected_secret.get_secret_value()}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Invalid API key", "type": "invalid_request_error"},
        )


def _usage(stats: Dict[str, Any]) -> Dict[str, int]:
    prompt = int(stats.get("prompt_tokens") or 0)
    completion = int(stats.get("completion_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _completion_payload(
    request_id: str,
    model: str,
    answer: str,
    stats: Dict[str, Any],
    routing: Optional[Dict[str, Any]] = None,
    ingestion: Optional[Dict[str, Any]] = None,
    knowledge: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"stats": stats}
    if routing is not None:
        metadata["routing"] = routing
    if ingestion is not None:
        metadata["ingestion"] = ingestion
    if knowledge is not None:
        metadata["knowledge"] = knowledge
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage(stats),
        "rlm": metadata,
    }


async def _single_chunk_stream(payload: Dict[str, Any]) -> AsyncIterator[bytes]:
    choice = payload["choices"][0]
    chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": choice["message"]["content"]},
                "finish_reason": None,
            }
        ],
        "rlm": payload.get("rlm", {}),
    }
    yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n".encode()
    final_chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk, separators=(',', ':'))}\n\n".encode()
    yield b"data: [DONE]\n\n"


def create_app() -> FastAPI:
    app = FastAPI(title="recursive-llm OpenAI proxy", version="0.5.0")
    app.include_router(build_catalog_mutation_router(_verify_auth))

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=[Depends(_verify_auth)])
    async def models(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": settings.model,
                    "object": "model",
                    "created": 0,
                    "owned_by": "recursive-llm",
                }
            ],
        }

    @app.get("/v1/rlm/slots", dependencies=[Depends(_verify_auth)])
    async def get_slots() -> Dict[str, Any]:
        return normalized_catalog(registry.snapshot()).model_dump()

    @app.put("/v1/rlm/slots", dependencies=[Depends(_verify_auth)])
    async def replace_slots(catalog: SlotCatalog) -> Dict[str, Any]:
        normalized = normalized_catalog(catalog)
        stored = registry.replace(normalized, expected_version=catalog.version)
        return normalized_catalog(stored).model_dump()

    @app.get("/v1/rlm/metrics", dependencies=[Depends(_verify_auth)])
    async def get_metrics() -> Dict[str, Any]:
        snapshot = metrics.snapshot()
        catalog = registry.snapshot()
        snapshot["slot_count"] = len(catalog.slots)
        snapshot["workstream_count"] = sum(len(slot.workstreams) for slot in catalog.slots)
        return snapshot

    @app.post("/v1/chat/completions", dependencies=[Depends(_verify_auth)])
    async def chat_completions(
        request: ChatCompletionRequest,
        settings: Settings = Depends(get_settings),
    ) -> Any:
        started = time.perf_counter()
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        request_dict = request.model_dump(exclude_none=True)
        try:
            query, message_context = split_query_context(
                request.messages,
                request.rlm.context if request.rlm else None,
            )
        except ValueError as exc:
            metrics.record(
                request_id=request_id,
                status="error",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
            )
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc

        options = request.rlm
        ingestion_options = (
            options.ingestion if options and options.ingestion else IngestionOptions()
        )
        ingestion_metadata: Optional[Dict[str, Any]] = None
        if should_preprocess(query, ingestion_options):
            try:
                ingested = await preprocess_dump(
                    text=query,
                    options=ingestion_options,
                    model=settings.model,
                    api_base=settings.private_api_base.rstrip("/"),
                    api_key=settings.private_api_key.get_secret_value(),
                )
            except ValueError as exc:
                metrics.record(
                    request_id=request_id,
                    status="error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=str(exc),
                )
                raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
            except Exception as exc:
                metrics.record(
                    request_id=request_id,
                    status="error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=str(exc),
                )
                raise HTTPException(
                    status_code=502,
                    detail={"message": str(exc), "type": "ingestion_error"},
                ) from exc
            query = ingested.query
            message_context = combine_context(ingested.context, message_context)
            ingestion_metadata = ingested.metadata

        route_metadata: Optional[Dict[str, Any]] = None
        routed_context = ""
        routing_options = options.routing if options and options.routing else None
        if routing_options is not None:
            catalog = registry.snapshot()
            try:
                decision = await resolve_route(
                    query=query,
                    catalog=catalog,
                    options=routing_options,
                    model=settings.model,
                    api_base=settings.private_api_base.rstrip("/"),
                    api_key=settings.private_api_key.get_secret_value(),
                )
            except (ValueError, json.JSONDecodeError) as exc:
                metrics.record(
                    request_id=request_id,
                    status="error",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=str(exc),
                )
                raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
            route_metadata = {
                "status": decision.status,
                "slot_slug": decision.slot_slug,
                "workstream_slugs": list(decision.workstream_slugs),
                "loaded_turn_count": decision.loaded_turn_count,
                "candidate_slugs": [item["slug"] for item in decision.candidates],
                "reason": decision.reason,
            }
            if decision.status == "clarify":
                payload = _completion_payload(
                    request_id,
                    request.model,
                    clarification_text(decision),
                    {},
                    route_metadata,
                    ingestion_metadata,
                )
                metrics.record(
                    request_id=request_id,
                    status="clarify",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    routing=route_metadata,
                )
                if request.stream:
                    return StreamingResponse(
                        _single_chunk_stream(payload), media_type="text/event-stream"
                    )
                return payload
            routed_context = build_routed_context(catalog, decision)

        knowledge_context = ""
        knowledge_metadata: Optional[Dict[str, Any]] = None
        knowledge_options = options.knowledge if options and options.knowledge else None
        knowledge_enabled = settings.knowledge_api_base is not None and (
            knowledge_options is None or knowledge_options.enabled
        )
        if knowledge_enabled and settings.knowledge_api_base is not None:
            candidate_limit = (
                knowledge_options.candidate_limit
                if knowledge_options and knowledge_options.candidate_limit is not None
                else settings.knowledge_candidate_limit
            )
            result_limit = (
                knowledge_options.limit
                if knowledge_options and knowledge_options.limit is not None
                else settings.knowledge_result_limit
            )
            max_context_chars = (
                knowledge_options.max_context_chars
                if knowledge_options and knowledge_options.max_context_chars is not None
                else settings.knowledge_max_context_chars
            )
            rerank = knowledge_options.rerank if knowledge_options else True
            required = knowledge_options.required if knowledge_options else False
            try:
                retrieved = await retrieve_knowledge(
                    api_base=settings.knowledge_api_base,
                    query=query,
                    candidate_limit=candidate_limit,
                    limit=result_limit,
                    rerank=rerank,
                    max_context_chars=max_context_chars,
                    timeout_seconds=settings.knowledge_timeout_seconds,
                )
                knowledge_context = retrieved.context
                knowledge_metadata = {
                    "status": "ok",
                    "hit_count": len(retrieved.hits),
                    "citations": retrieved.citations,
                }
            except (httpx.HTTPError, ValueError) as exc:
                knowledge_metadata = {"status": "unavailable", "error": str(exc)}
                if required:
                    metrics.record(
                        request_id=request_id,
                        status="error",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        routing=route_metadata,
                        error=str(exc),
                    )
                    raise HTTPException(
                        status_code=502,
                        detail={"message": str(exc), "type": "knowledge_error"},
                    ) from exc

        context = combine_context(routed_context, knowledge_context, message_context)
        rlm = RLM(
            model=settings.model,
            recursive_model=settings.recursive_model,
            api_base=settings.private_api_base.rstrip("/"),
            api_key=settings.private_api_key.get_secret_value(),
            max_depth=(
                options.max_depth
                if options and options.max_depth is not None
                else settings.max_depth
            ),
            max_iterations=(
                options.max_iterations
                if options and options.max_iterations is not None
                else settings.max_iterations
            ),
            repl_timeout=settings.repl_timeout,
            max_output_chars=settings.max_output_chars,
            max_concurrent_subcalls=settings.max_concurrent_subcalls,
            max_total_calls=(
                options.max_total_calls
                if options and options.max_total_calls is not None
                else settings.max_total_calls
            ),
            max_total_tokens=(
                options.max_total_tokens
                if options and options.max_total_tokens is not None
                else settings.max_total_tokens
            ),
            max_total_cost_usd=settings.max_total_cost_usd,
            max_elapsed_seconds=(
                options.max_elapsed_seconds
                if options and options.max_elapsed_seconds is not None
                else settings.max_elapsed_seconds
            ),
            **forwarded_llm_kwargs(request_dict),
        )

        try:
            result = await rlm.acomplete_result(query=query, context=context)
        except RLMError as exc:
            metrics.record(
                request_id=request_id,
                status="error",
                latency_ms=(time.perf_counter() - started) * 1000,
                routing=route_metadata,
                error=str(exc),
            )
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "type": type(exc).__name__},
            ) from exc

        payload = _completion_payload(
            request_id,
            request.model,
            result.answer,
            result.stats,
            route_metadata,
            ingestion_metadata,
            knowledge_metadata,
        )
        metrics.record(
            request_id=request_id,
            status="ok",
            latency_ms=(time.perf_counter() - started) * 1000,
            routing=route_metadata,
            stats=result.stats,
        )
        if request.stream:
            return StreamingResponse(_single_chunk_stream(payload), media_type="text/event-stream")
        return payload

    return app


app = create_app()
