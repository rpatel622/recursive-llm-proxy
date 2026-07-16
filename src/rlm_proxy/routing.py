"""In-memory slot catalog and adaptive model-assisted routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List, Optional, Sequence, Tuple

import litellm

from .models import RoutingOptions, SlotCatalog, SlotDefinition, WorkstreamDefinition


@dataclass(frozen=True)
class RouteDecision:
    status: str
    slot_slug: Optional[str]
    workstream_slugs: Tuple[str, ...]
    loaded_turn_count: int
    candidates: Tuple[Dict[str, str], ...] = ()
    reason: str = ""


class SlotRegistry:
    """Thread-safe process-local catalog. Replaceable through the HTTP API."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._catalog = SlotCatalog(slots=[])

    def replace(self, catalog: SlotCatalog) -> None:
        with self._lock:
            self._catalog = catalog.model_copy(deep=True)

    def snapshot(self) -> SlotCatalog:
        with self._lock:
            return self._catalog.model_copy(deep=True)


registry = SlotRegistry()


def _generated_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def normalized_catalog(catalog: SlotCatalog) -> SlotCatalog:
    """Fill omitted display metadata without changing stable slugs."""

    slots: List[SlotDefinition] = []
    for slot in catalog.slots:
        workstreams: List[WorkstreamDefinition] = []
        for stream in slot.workstreams:
            description = stream.description
            if not description:
                sample = " ".join(turn.content.strip() for turn in stream.turns[-4:])
                description = sample[:240] or f"Workstream {stream.slug}"
            workstreams.append(
                stream.model_copy(
                    update={
                        "name": stream.name or _generated_name(stream.slug),
                        "description": description,
                    }
                )
            )
        slot_description = slot.description
        if not slot_description:
            slot_description = "; ".join(item.description or "" for item in workstreams)[:320]
            slot_description = slot_description or f"Slot {slot.slug}"
        slots.append(
            slot.model_copy(
                update={
                    "name": slot.name or _generated_name(slot.slug),
                    "description": slot_description,
                    "workstreams": workstreams,
                }
            )
        )
    return SlotCatalog(slots=slots)


def _find_slot(catalog: SlotCatalog, slug: str) -> SlotDefinition:
    for slot in catalog.slots:
        if slot.slug == slug:
            return slot
    raise ValueError(f"unknown slot slug: {slug}")


def _find_workstreams(slot: SlotDefinition, slugs: Sequence[str]) -> List[WorkstreamDefinition]:
    by_slug = {item.slug: item for item in slot.workstreams}
    missing = [slug for slug in slugs if slug not in by_slug]
    if missing:
        raise ValueError(f"unknown workstream slug(s) in {slot.slug}: {', '.join(missing)}")
    return [by_slug[slug] for slug in slugs]


def _metadata_view(catalog: SlotCatalog, turn_count: int) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for slot in catalog.slots:
        streams: List[Dict[str, Any]] = []
        for stream in slot.workstreams:
            streams.append(
                {
                    "slug": stream.slug,
                    "name": stream.name,
                    "description": stream.description,
                    "loaded_turn_count": min(turn_count, len(stream.turns)),
                    "available_turn_count": len(stream.turns),
                    "recent_turns": [
                        turn.model_dump() for turn in stream.turns[-turn_count:]
                    ],
                }
            )
        result.append(
            {
                "slug": slot.slug,
                "name": slot.name,
                "description": slot.description,
                "workstreams": streams,
            }
        )
    return result


def _parse_json_object(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("router did not return a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("router response must be an object")
    return value


async def _router_call(
    query: str,
    catalog: SlotCatalog,
    options: RoutingOptions,
    turn_count: int,
    model: str,
    api_base: str,
    api_key: str,
) -> Dict[str, Any]:
    prompt = {
        "query": query,
        "rules": {
            "slot_isolation": "Do not combine slots unless allow_cross_slot is true.",
            "multi_workstream": options.allow_multi_workstream,
            "clarify_only": options.mode == "clarify_only",
            "actions": ["route", "expand", "clarify"],
            "output": {
                "action": "route|expand|clarify",
                "slot_slug": "string or null",
                "workstream_slugs": ["slug"],
                "candidate_slugs": ["slot/workstream"],
                "reason": "short explanation",
            },
        },
        "catalog": _metadata_view(catalog, turn_count),
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
                    "Route the request to existing isolated slots and workstreams. "
                    "Return only one JSON object. Expand when more history can resolve ambiguity. "
                    "Clarify when ambiguity remains or cross-slot access would be implicit."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    content = response.choices[0].message.content or ""
    return _parse_json_object(content)


async def resolve_route(
    query: str,
    catalog: SlotCatalog,
    options: RoutingOptions,
    model: str,
    api_base: str,
    api_key: str,
) -> RouteDecision:
    catalog = normalized_catalog(catalog)
    if options.slot_slug:
        slot = _find_slot(catalog, options.slot_slug)
        slugs = options.workstream_slugs or [item.slug for item in slot.workstreams]
        streams = _find_workstreams(slot, slugs)
        return RouteDecision(
            status="route",
            slot_slug=slot.slug,
            workstream_slugs=tuple(item.slug for item in streams),
            loaded_turn_count=options.max_turn_count,
            reason="explicit route",
        )
    if not catalog.slots:
        return RouteDecision("route", None, (), 0, reason="empty catalog")

    turn_count = options.initial_turn_count
    while True:
        raw = await _router_call(
            query, catalog, options, turn_count, model, api_base, api_key
        )
        action = str(raw.get("action", "clarify"))
        slot_slug = raw.get("slot_slug")
        slugs = tuple(str(item) for item in raw.get("workstream_slugs", []))
        reason = str(raw.get("reason", ""))
        candidates = tuple(
            {"slug": str(item)} for item in raw.get("candidate_slugs", [])
        )

        if action == "expand" and turn_count < options.max_turn_count:
            turn_count = min(options.max_turn_count, max(turn_count + 1, turn_count * 2))
            continue
        if action == "route" and options.mode != "clarify_only" and slot_slug:
            slot = _find_slot(catalog, str(slot_slug))
            streams = _find_workstreams(slot, slugs)
            if not options.allow_multi_workstream and len(streams) > 1:
                action = "clarify"
            else:
                return RouteDecision(
                    "route", slot.slug, tuple(item.slug for item in streams), turn_count, reason=reason
                )
        return RouteDecision(
            "clarify", None, (), turn_count, candidates=candidates, reason=reason
        )


def build_routed_context(catalog: SlotCatalog, decision: RouteDecision) -> str:
    if decision.slot_slug is None:
        return ""
    slot = _find_slot(normalized_catalog(catalog), decision.slot_slug)
    streams = _find_workstreams(slot, decision.workstream_slugs)
    payload = {
        "slot": {
            "slug": slot.slug,
            "name": slot.name,
            "description": slot.description,
        },
        "workstreams": [
            {
                "slug": stream.slug,
                "name": stream.name,
                "description": stream.description,
                "turns": [turn.model_dump() for turn in stream.turns],
            }
            for stream in streams
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def clarification_text(decision: RouteDecision) -> str:
    slugs = [item["slug"] for item in decision.candidates if item.get("slug")]
    if not slugs:
        return "I could not resolve the context slot. Provide a slot slug and workstream slug."
    lines = "\n".join(f"- `{slug}`" for slug in slugs)
    return f"I found multiple plausible contexts:\n\n{lines}\n\nWhich slug should I use?"
