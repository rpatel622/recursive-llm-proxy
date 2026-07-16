"""Tests for the UI-managed proxy lifecycle boundary."""

from __future__ import annotations

import pytest

from rlm_proxy.managed_proxy import ManagedProxy, ProxyLaunchConfig


def make_config(**overrides):
    values = {
        "host": "127.0.0.1",
        "port": 8000,
        "public_api_key": "public-key",
        "private_api_base": "http://127.0.0.1:8080/v1",
        "private_api_key": "private-key",
        "model": "openai/local",
        "recursive_model": "openai/local",
        "max_depth": 2,
        "max_iterations": 20,
    }
    values.update(overrides)
    return ProxyLaunchConfig(**values)


def test_launch_config_builds_client_url():
    assert make_config(host="0.0.0.0", port=9000).url == "http://127.0.0.1:9000"
    assert make_config(host="localhost", port=9001).url == "http://localhost:9001"


def test_launch_config_validates_inputs():
    with pytest.raises(ValueError, match="port"):
        make_config(port=0).validate()
    with pytest.raises(ValueError, match="Private API base"):
        make_config(private_api_base="127.0.0.1:8080/v1").validate()
    with pytest.raises(ValueError, match="Maximum depth"):
        make_config(max_depth=-1).validate()


def test_environment_contains_proxy_settings(monkeypatch):
    monkeypatch.setenv("UNCHANGED_SETTING", "present")
    env = make_config().environment()
    assert env["UNCHANGED_SETTING"] == "present"
    assert env["RLM_PROXY_PUBLIC_API_KEY"] == "public-key"
    assert env["RLM_PROXY_PRIVATE_API_BASE"] == "http://127.0.0.1:8080/v1"
    assert env["RLM_PROXY_PRIVATE_API_KEY"] == "private-key"
    assert env["RLM_PROXY_MODEL"] == "openai/local"
    assert env["RLM_PROXY_MAX_DEPTH"] == "2"


def test_unstarted_manager_reports_stopped():
    status = ManagedProxy().status()
    assert status["running"] is False
    assert status["pid"] is None
    assert status["url"] is None
