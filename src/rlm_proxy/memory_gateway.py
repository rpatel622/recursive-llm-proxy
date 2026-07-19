"""Memory-aware OpenAI-compatible chat gateway over the existing proxy app."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .app import create_app
from .conversation_compaction import CompactableMessage, CompactionPolicy, compact_context
from .conversation_memory import ConversationMemoryStore


def _memory_path() -> str:
    return os.getenv(
        "RLM_PROXY_MEMORY_DB_PATH",
        str(Path("~/.recursive-llm/conversations.sqlite3").expanduser()),
    )


def _message_text(message: Dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _memory_context(summary: str, messages: List[CompactableMessage]) -> str:
    sections = []
    if summary.strip():
        sections.append("Conversation memory:\n" + summary.strip())
    if messages:
        rendered = "\n".join("%s: %s" % (item.role, item.content) for item in messages)
        sections.append("Recent conversation:\n" + rendered)
    return "\n\n".join(sections)


def create_memory_gateway() -> FastAPI:
    app = create_app()
    store = ConversationMemoryStore(_memory_path())
    policy = CompactionPolicy(
        max_messages=int(os.getenv("RLM_PROXY_MEMORY_MAX_MESSAGES", "32")),
        preserve_recent=int(os.getenv("RLM_PROXY_MEMORY_PRESERVE_RECENT", "12")),
        max_summary_chars=int(os.getenv("RLM_PROXY_MEMORY_MAX_SUMMARY_CHARS", "8000")),
    )

    @app.post("/v1/memory/chat/completions")
    async def memory_chat(request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail={"message": "request body must be an object"})
        conversation_id = str(payload.pop("conversation_id", "") or uuid.uuid4().hex)
        try:
            snapshot = store.get(conversation_id)
        except KeyError:
            snapshot = store.create(conversation_id)

        retained = [CompactableMessage(item.role, item.content) for item in snapshot.messages]
        memory_context = _memory_context(snapshot.summary, retained)
        rlm = dict(payload.get("rlm") or {})
        existing_context = str(rlm.get("context") or "").strip()
        rlm["context"] = "\n\n".join(
            section for section in [memory_context, existing_context] if section
        )
        payload["rlm"] = rlm

        messages = payload.get("messages") or []
        user_text = ""
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                user_text = _message_text(message)
                break
        if not user_text.strip():
            raise HTTPException(status_code=400, detail={"message": "a user message is required"})

        transport = httpx.ASGITransport(app=app)
        headers = {}
        authorization = request.headers.get("authorization")
        if authorization:
            headers["Authorization"] = authorization
        async with httpx.AsyncClient(transport=transport, base_url="http://memory-gateway") as client:
            response = await client.post("/v1/chat/completions", json=payload, headers=headers)
        if response.status_code >= 400:
            return JSONResponse(status_code=response.status_code, content=response.json())

        result = response.json()
        choices = result.get("choices") or []
        assistant_text = ""
        if choices and isinstance(choices[0], dict):
            assistant_text = str((choices[0].get("message") or {}).get("content") or "")

        current = store.get(conversation_id)
        current = store.append(conversation_id, "user", user_text, current.revision)
        if assistant_text.strip():
            current = store.append(conversation_id, "assistant", assistant_text, current.revision)

        compactable = [CompactableMessage(item.role, item.content) for item in current.messages]
        summary, _ = compact_context(current.summary, compactable, policy)
        if summary != current.summary:
            current = store.update_summary(conversation_id, summary, current.revision)

        result["conversation_id"] = conversation_id
        result["conversation_revision"] = current.revision
        return JSONResponse(content=result)

    @app.get("/v1/memory/conversations")
    async def list_conversations(limit: int = 20) -> Dict[str, Any]:
        return {
            "data": [
                {
                    "conversation_id": item.conversation_id,
                    "revision": item.revision,
                    "summary": item.summary,
                    "message_count": len(item.messages),
                    "updated_at": item.updated_at,
                }
                for item in store.list_recent(limit)
            ]
        }

    @app.get("/v1/memory/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str) -> Dict[str, Any]:
        try:
            item = store.get(conversation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"message": "conversation not found"}) from exc
        return {
            "conversation_id": item.conversation_id,
            "revision": item.revision,
            "summary": item.summary,
            "messages": [message.__dict__ for message in item.messages],
            "updated_at": item.updated_at,
        }

    @app.delete("/v1/memory/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str) -> Dict[str, Any]:
        if not store.delete(conversation_id):
            raise HTTPException(status_code=404, detail={"message": "conversation not found"})
        return {"conversation_id": conversation_id, "deleted": True}

    return app


app = create_memory_gateway()

__all__ = ["app", "create_memory_gateway"]
