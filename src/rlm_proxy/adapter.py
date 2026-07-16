"""Deterministic conversion between OpenAI chat messages and RLM inputs."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import ChatMessage


def _text_content(message: ChatMessage) -> str:
    content = message.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content

    parts: List[str] = []
    for item in content:
        item_type = item.get("type")
        if item_type == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
        else:
            parts.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(parts)


def split_query_context(
    messages: Iterable[ChatMessage], explicit_context: Optional[str]
) -> Tuple[str, str]:
    """Use the final user message as query and everything before it as context."""

    materialized = list(messages)
    final_user_index = next(
        (
            index
            for index in range(len(materialized) - 1, -1, -1)
            if materialized[index].role == "user"
        ),
        None,
    )
    if final_user_index is None:
        raise ValueError("messages must contain at least one user message")

    query = _text_content(materialized[final_user_index]).strip()
    if not query:
        raise ValueError("the final user message must contain text")

    records: List[Dict[str, Any]] = []
    for index, message in enumerate(materialized):
        if index == final_user_index:
            continue
        text = _text_content(message)
        if text:
            records.append({"role": message.role, "name": message.name, "content": text})

    context_parts: List[str] = []
    if explicit_context:
        context_parts.append(explicit_context)
    if records:
        context_parts.append(json.dumps(records, ensure_ascii=False, separators=(",", ":")))

    return query, "\n\n".join(context_parts)


def forwarded_llm_kwargs(request_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Forward only generation controls understood by OpenAI-compatible providers."""

    mapping = {
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "stop": "stop",
        "top_p": "top_p",
        "frequency_penalty": "frequency_penalty",
        "presence_penalty": "presence_penalty",
        "seed": "seed",
    }
    return {
        target: request_dict[source]
        for source, target in mapping.items()
        if request_dict.get(source) is not None
    }
