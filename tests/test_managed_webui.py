from pathlib import Path

import pytest

from rlm_proxy.managed_webui import WebUILaunchConfig


def test_webui_config_builds_local_openai_environment(tmp_path: Path) -> None:
    config = WebUILaunchConfig(
        proxy_url="http://127.0.0.1:8000",
        proxy_api_key="secret",
        data_dir=str(tmp_path / "webui"),
    )

    env = config.environment()

    assert env["DATA_DIR"] == str((tmp_path / "webui").resolve())
    assert env["OPENAI_API_BASE_URL"] == "http://127.0.0.1:8000/v1"
    assert env["OPENAI_API_BASE_URLS"] == "http://127.0.0.1:8000/v1"
    assert env["OPENAI_API_KEY"] == "secret"
    assert env["OPENAI_API_KEYS"] == "secret"
    assert env["WEBUI_AUTH"] == "False"
    assert env["TASK_MODEL_EXTERNAL"] == "rlm"
    assert env["ENABLE_CONTEXT_COMPACTION"] == "True"
    assert (tmp_path / "webui").is_dir()


def test_webui_config_supports_authenticated_mode(tmp_path: Path) -> None:
    config = WebUILaunchConfig(data_dir=str(tmp_path), auth_enabled=True)
    assert config.environment()["WEBUI_AUTH"] == "True"


@pytest.mark.parametrize("port", [0, 65536])
def test_webui_config_rejects_invalid_ports(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        WebUILaunchConfig(port=port).validate()


def test_webui_config_rejects_invalid_proxy_url() -> None:
    with pytest.raises(ValueError, match="Proxy URL"):
        WebUILaunchConfig(proxy_url="localhost:8000").validate()


def test_webui_public_url_uses_loopback_for_wildcard_host() -> None:
    assert WebUILaunchConfig(host="0.0.0.0", port=3333).url == "http://127.0.0.1:3333"
