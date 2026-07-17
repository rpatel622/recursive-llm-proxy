"""Tests for isolated slot and workstream routing."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from rlm_proxy.models import (
    RoutingOptions,
    SlotCatalog,
    SlotDefinition,
    StoredTurn,
    WorkstreamDefinition,
)
from rlm_proxy.routing import build_routed_context, normalized_catalog, resolve_route


def catalog() -> SlotCatalog:
    return SlotCatalog(
        slots=[
            SlotDefinition(
                slug="engineering",
                workstreams=[
                    WorkstreamDefinition(
                        slug="deployment-prod",
                        turns=[
                            StoredTurn(role="user", content="Production rollback planning"),
                            StoredTurn(
                                role="assistant", content="Use the blue-green rollback path"
                            ),
                        ],
                    ),
                    WorkstreamDefinition(
                        slug="deployment-staging",
                        turns=[StoredTurn(role="user", content="Staging validation")],
                    ),
                ],
            )
        ]
    )


def test_normalized_catalog_generates_display_metadata() -> None:
    value = normalized_catalog(catalog())
    assert value.slots[0].name == "Engineering"
    assert value.slots[0].workstreams[0].name == "Deployment Prod"
    assert "Production rollback" in value.slots[0].workstreams[0].description


def test_duplicate_workstream_slugs_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        SlotDefinition(
            slug="engineering",
            workstreams=[
                WorkstreamDefinition(slug="same"),
                WorkstreamDefinition(slug="same"),
            ],
        )


@pytest.mark.asyncio
async def test_explicit_route_does_not_call_router(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("router should not be called")

    monkeypatch.setattr("rlm_proxy.routing._router_call", fail)
    decision = await resolve_route(
        query="What is the rollback plan?",
        catalog=catalog(),
        options=RoutingOptions(
            mode="explicit",
            slot_slug="engineering",
            workstream_slugs=["deployment-prod"],
        ),
        model="openai/local",
        api_base="http://localhost/v1",
        api_key="test",
    )
    assert decision.status == "route"
    assert decision.slot_slug == "engineering"
    assert decision.workstream_slugs == ("deployment-prod",)
    context = build_routed_context(catalog(), decision)
    assert "deployment-prod" in context
    assert "deployment-staging" not in context


@pytest.mark.asyncio
async def test_router_expands_then_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[int] = []

    async def route(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        turn_count = int(args[3])
        seen.append(turn_count)
        if turn_count < 8:
            return {"action": "expand", "reason": "need more history"}
        return {
            "action": "route",
            "slot_slug": "engineering",
            "workstream_slugs": ["deployment-prod"],
            "reason": "production is explicit",
        }

    monkeypatch.setattr("rlm_proxy.routing._router_call", route)
    decision = await resolve_route(
        query="What is the production rollback plan?",
        catalog=catalog(),
        options=RoutingOptions(initial_turn_count=2, max_turn_count=8),
        model="openai/local",
        api_base="http://localhost/v1",
        api_key="test",
    )
    assert seen == [2, 4, 8]
    assert decision.status == "route"
    assert decision.loaded_turn_count == 8


@pytest.mark.asyncio
async def test_router_clarifies_with_slugs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clarify(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "action": "clarify",
            "candidate_slugs": [
                "engineering/deployment-prod",
                "engineering/deployment-staging",
            ],
            "reason": "environment is unspecified",
        }

    monkeypatch.setattr("rlm_proxy.routing._router_call", clarify)
    decision = await resolve_route(
        query="What is the rollback plan?",
        catalog=catalog(),
        options=RoutingOptions(),
        model="openai/local",
        api_base="http://localhost/v1",
        api_key="test",
    )
    assert decision.status == "clarify"
    assert [item["slug"] for item in decision.candidates] == [
        "engineering/deployment-prod",
        "engineering/deployment-staging",
    ]
