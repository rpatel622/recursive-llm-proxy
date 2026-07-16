"""FastAPI application exposing recursive-llm as an OpenAI-compatible service."""

from __future__ import annotations

import json
import secrets
import time
import uuid
from typing import Any, AsyncIterator, Dict

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from rlm import RLM
from rlm.errors import RLMError

from .adapter import forwarded_llm_kwargs, split_query_context
from .config import Settings, get_settings
from .models import ChatCompletionRequest


def _verify_auth(
    authorization: str | None = Header(default=None),
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
    request_id: str, model: str, answer: str, stats: Dict[str, Any]
) -> Dict[str, Any]:
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
        "rlm": {"stats": stats},
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
    app = FastAPI(title="recursive-llm OpenAI proxy", version="0.1.0")

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

    @app.post("/v1/chat/completions", dependencies=[Depends(_verify_auth)])
    async def chat_completions(
        request: ChatCompletionRequest,
        settings: Settings = Depends(get_settings),
    ) -> Any:
        request_dict = request.model_dump(exclude_none=True)
        try:
            query, context = split_query_context(
                request.messages,
                request.rlm.context if request.rlm else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc

        options = request.rlm
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
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "type": type(exc).__name__},
            ) from exc

        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        payload = _completion_payload(request_id, request.model, result.answer, result.stats)
        if request.stream:
            return StreamingResponse(_single_chunk_stream(payload), media_type="text/event-stream")
        return payload

    return app


app = create_app()
