from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None,
    reason="proxy extras are not installed",
)


def test_memory_gateway_exports_factory() -> None:
    from rlm_proxy.memory_gateway import create_memory_gateway

    app = create_memory_gateway()
    paths = {route.path for route in app.routes}
    assert "/v1/memory/chat/completions" in paths
    assert "/v1/memory/conversations" in paths
    assert "/v1/memory/conversations/{conversation_id}" in paths
