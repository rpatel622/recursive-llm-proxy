"""Bounded rolling-window preprocessing for oversized user message dumps."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import litellm

from .models import IngestionOptions


@dataclass(frozen=True)
class IngestionResult:
    query: str
    context: str
    metadata: Dict[str, Any]


def _parse_json_object(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("ingestion model did not return a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("ingestion response must be an object")
    return value


def _natural_units(text: str) -> List[str]:
    """Split at headings, blank lines, list blocks, then sentences as a fallback."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    blocks = [item.strip() for item in re.split(r"\n{2,}", normalized) if item.strip()]
    units: List[str] = []
    for block in blocks:
        if len(block) <= 4000:
            units.append(block)
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\-\[])|\n(?=#+\s|[-*]\s|\d+[.)]\s)", block)
        units.extend(item.strip() for item in sentences if item.strip())
    return units


def natural_windows(text: str, window_chars: int, overlap_chars: int) -> List[str]:
    if window_chars <= 0:
        raise ValueError("window_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= window_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than window_chars")

    units = _natural_units(text)
    if not units:
        return []
    windows: List[str] = []
    current: List[str] = []
    current_len = 0
    for unit in units:
        if len(unit) > window_chars:
            if current:
                windows.append("\n\n".join(current))
                current = []
                current_len = 0
            step = window_chars - overlap_chars
            for start in range(0, len(unit), step):
                piece = unit[start : start + window_chars]
                if piece:
                    windows.append(piece)
                if start + window_chars >= len(unit):
                    break
            continue
        addition = len(unit) + (2 if current else 0)
        if current and current_len + addition > window_chars:
            completed = "\n\n".join(current)
            windows.append(completed)
            tail = completed[-overlap_chars:] if overlap_chars else ""
            current = [tail, unit] if tail else [unit]
            current_len = sum(len(item) for item in current) + 2 * (len(current) - 1)
        else:
            current.append(unit)
            current_len += addition
    if current:
        windows.append("\n\n".join(current))
    return windows


def _fallback_request(text: str) -> str:
    candidates = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    for item in reversed(candidates[-8:]):
        if "?" in item or re.match(
            r"^(please\s+)?(summarize|analyze|compare|extract|identify|find|write|create|explain|review|determine)\b",
            item,
            flags=re.IGNORECASE,
        ):
            return item[-2000:]
    return "Analyze the supplied information and answer the user's implied request."


async def _window_call(
    chunk: str,
    index: int,
    total: int,
    rolling_state: Dict[str, Any],
    model: str,
    api_base: str,
    api_key: str,
    metadata_chars: int,
) -> Dict[str, Any]:
    payload = {
        "window": {"index": index, "total": total, "text": chunk},
        "prior_compact_state": rolling_state,
        "instructions": {
            "request": "Capture an explicit user request if present; otherwise null.",
            "summary": "Summarize this window for later semantic retrieval.",
            "title": "Short natural title for this section.",
            "topics": "Up to 8 concise topics.",
            "entities": "Important named entities, systems, products, people, and dates.",
            "facts": "Up to 12 concrete facts, decisions, constraints, or open questions.",
            "boundary": "Describe how this window begins/ends and whether it continues a prior section.",
            "rolling_state": (
                "Return an updated compact state containing only durable themes, candidate requests, "
                "entities, constraints, and unresolved references. Keep it bounded."
            ),
        },
    }
    response = await litellm.acompletion(
        model=model,
        api_base=api_base,
        api_key=api_key,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Preprocess one bounded window from a potentially huge user message. "
                    "Respect natural document boundaries. Return only JSON with keys request, title, "
                    "summary, topics, entities, facts, boundary, and rolling_state. Do not answer the request."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    raw = response.choices[0].message.content or ""
    result = _parse_json_object(raw)
    state = result.get("rolling_state")
    if isinstance(state, dict):
        encoded = json.dumps(state, ensure_ascii=False)
        if len(encoded) > metadata_chars:
            state = {"summary": encoded[:metadata_chars]}
        result["rolling_state"] = state
    else:
        result["rolling_state"] = {}
    return result


async def preprocess_dump(
    text: str,
    options: IngestionOptions,
    model: str,
    api_base: str,
    api_key: str,
) -> IngestionResult:
    """Turn a giant message into an extracted request plus searchable chunk records."""

    windows = natural_windows(text, options.window_chars, options.overlap_chars)
    if len(windows) > options.max_windows:
        raise ValueError(
            f"message requires {len(windows)} ingestion windows; maximum is {options.max_windows}"
        )

    rolling_state: Dict[str, Any] = {}
    records: List[Dict[str, Any]] = []
    requests: List[str] = []
    for index, chunk in enumerate(windows, start=1):
        analyzed = await _window_call(
            chunk,
            index,
            len(windows),
            rolling_state,
            model,
            api_base,
            api_key,
            options.metadata_chars,
        )
        rolling_state = analyzed.pop("rolling_state", {})
        request = analyzed.get("request")
        if isinstance(request, str) and request.strip():
            requests.append(request.strip())
        records.append(
            {
                "chunk_id": f"dump-{index:04d}",
                "start_window": index,
                "title": str(analyzed.get("title") or f"Dump section {index}"),
                "summary": str(analyzed.get("summary") or ""),
                "topics": list(analyzed.get("topics") or []),
                "entities": list(analyzed.get("entities") or []),
                "facts": list(analyzed.get("facts") or []),
                "boundary": str(analyzed.get("boundary") or ""),
                "text": chunk,
            }
        )

    query = requests[-1] if requests else _fallback_request(text)
    context_object = {
        "kind": "rolling-ingested-user-dump",
        "instructions": (
            "Use chunk metadata to locate relevant raw text. Exact source text is retained in each chunk.text."
        ),
        "global_metadata": rolling_state,
        "chunks": records,
    }
    metadata = {
        "status": "processed",
        "original_chars": len(text),
        "window_count": len(windows),
        "window_chars": options.window_chars,
        "overlap_chars": options.overlap_chars,
        "extracted_request": query,
        "topics": rolling_state.get("topics", []) if isinstance(rolling_state, dict) else [],
        "entities": rolling_state.get("entities", []) if isinstance(rolling_state, dict) else [],
    }
    return IngestionResult(
        query=query,
        context=json.dumps(context_object, ensure_ascii=False, separators=(",", ":")),
        metadata=metadata,
    )


def should_preprocess(text: str, options: IngestionOptions) -> bool:
    return options.enabled and len(text) >= options.threshold_chars
