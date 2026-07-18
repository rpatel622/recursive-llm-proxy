from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from rlm_proxy.app import create_app
from rlm_proxy.config import Settings, get_settings
from rlm_proxy.knowledge import KnowledgeResult


def _settings() -> Settings:
    return Settings(
        private_api_base="http://private:8080/v1",
        private_api_key="private-key",
        public_api_key="public-key",
        model="openai/private-model",
        knowledge_api_base="http://knowledge:8010",
    )


def test_retrieved_context_and_citations_are_returned() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _settings
    fake_result = SimpleNamespace(answer="Grounded answer", stats={})
    retrieved = KnowledgeResult(
        context="[Source 1: notes.txt]\nGrounded fact",
        citations=[{"index": 1, "source_uri": "file:///notes.txt"}],
        hits=[{"score": 0.9}],
    )

    with (
        patch("rlm_proxy.app.retrieve_knowledge", new=AsyncMock(return_value=retrieved)),
        patch("rlm_proxy.app.RLM") as rlm_type,
    ):
        rlm_type.return_value.acomplete_result = AsyncMock(return_value=fake_result)
        response = TestClient(app).post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer public-key"},
            json={"model": "rlm", "messages": [{"role": "user", "content": "Question"}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["rlm"]["knowledge"]["status"] == "ok"
    assert body["rlm"]["knowledge"]["citations"][0]["source_uri"] == "file:///notes.txt"
    call = rlm_type.return_value.acomplete_result.await_args
    assert "Grounded fact" in call.kwargs["context"]


def test_optional_knowledge_failure_does_not_fail_chat() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _settings
    fake_result = SimpleNamespace(answer="Fallback answer", stats={})

    with (
        patch("rlm_proxy.app.retrieve_knowledge", new=AsyncMock(side_effect=ValueError("offline"))),
        patch("rlm_proxy.app.RLM") as rlm_type,
    ):
        rlm_type.return_value.acomplete_result = AsyncMock(return_value=fake_result)
        response = TestClient(app).post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer public-key"},
            json={"model": "rlm", "messages": [{"role": "user", "content": "Question"}]},
        )

    assert response.status_code == 200
    assert response.json()["rlm"]["knowledge"]["status"] == "unavailable"


def test_required_knowledge_failure_returns_bad_gateway() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _settings

    with patch(
        "rlm_proxy.app.retrieve_knowledge", new=AsyncMock(side_effect=ValueError("offline"))
    ):
        response = TestClient(app).post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer public-key"},
            json={
                "model": "rlm",
                "messages": [{"role": "user", "content": "Question"}],
                "rlm": {"knowledge": {"required": True}},
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["type"] == "knowledge_error"
