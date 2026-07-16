from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from rlm_proxy.app import create_app
from rlm_proxy.config import Settings, get_settings


def _settings() -> Settings:
    return Settings(
        private_api_base="http://private:8080/v1",
        private_api_key="private-key",
        public_api_key="public-key",
        model="openai/private-model",
    )


def test_chat_completion_contract() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _settings
    fake_result = SimpleNamespace(
        answer="A is 7.",
        stats={"prompt_tokens": 10, "completion_tokens": 4, "llm_calls": 3},
    )

    with patch("rlm_proxy.app.RLM") as rlm_type:
        rlm_type.return_value.acomplete_result = AsyncMock(return_value=fake_result)
        response = TestClient(app).post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer public-key"},
            json={
                "model": "rlm",
                "messages": [
                    {"role": "user", "content": "Record: A=7"},
                    {"role": "user", "content": "What is A?"},
                ],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "A is 7."
    assert body["usage"]["total_tokens"] == 14


def test_auth_is_enforced() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _settings
    response = TestClient(app).get("/v1/models")
    assert response.status_code == 401
