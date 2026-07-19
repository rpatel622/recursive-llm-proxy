"""Tests for native knowledge service supervision."""

from __future__ import annotations

from pathlib import Path

import pytest

from rlm_proxy.managed_knowledge import KnowledgeServiceLaunchConfig
from rlm_proxy.managed_proxy import ProxyLaunchConfig


def test_knowledge_config_uses_persistent_user_data_path(tmp_path: Path) -> None:
    config = KnowledgeServiceLaunchConfig(
        binary="rlm-knowledge-service",
        host="127.0.0.1",
        port=8010,
        data_dir=str(tmp_path),
    )

    assert config.url == "http://127.0.0.1:8010"
    assert config.database_path == tmp_path / "knowledge.sqlite3"
    assert config.log_path == tmp_path / "knowledge-service.log"
    assert config.environment()["RLM_KNOWLEDGE_DB"] == str(tmp_path / "knowledge.sqlite3")


def test_knowledge_config_validates_port() -> None:
    with pytest.raises(ValueError, match="port"):
        KnowledgeServiceLaunchConfig(binary="service", port=0).validate()


def test_proxy_receives_managed_knowledge_url() -> None:
    config = ProxyLaunchConfig(
        host="127.0.0.1",
        port=8000,
        public_api_key="secret",
        private_api_base="http://127.0.0.1:8080/v1",
        private_api_key="not-needed",
        model="openai/local",
        recursive_model="openai/local",
        max_depth=2,
        max_iterations=20,
        knowledge_api_base="http://127.0.0.1:8010",
    )

    assert config.environment()["RLM_PROXY_KNOWLEDGE_API_BASE"] == "http://127.0.0.1:8010"
