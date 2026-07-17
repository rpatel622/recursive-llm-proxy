from pathlib import Path

import pytest

from rlm_proxy.managed_llama import LlamaServerLaunchConfig


def test_command_uses_accessibility_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    binary = tmp_path / "llama-server"
    binary.write_text("binary")
    monkeypatch.setattr("rlm_proxy.managed_llama.shutil.which", lambda _: str(binary))

    config = LlamaServerLaunchConfig(model_path=str(model))
    command = config.command()

    assert command[0] == str(binary)
    assert command[command.index("--model") + 1] == str(model.resolve())
    assert command[command.index("--cache-type-k") + 1] == "q8_0"
    assert command[command.index("--cache-type-v") + 1] == "q4_0"
    assert command[command.index("--parallel") + 1] == "1"
    assert command[command.index("--n-gpu-layers") + 1] == "all"
    assert config.url == "http://127.0.0.1:8080/v1"


def test_requires_existing_gguf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "llama-server"
    binary.write_text("binary")
    monkeypatch.setattr("rlm_proxy.managed_llama.shutil.which", lambda _: str(binary))

    with pytest.raises(ValueError, match="does not exist"):
        LlamaServerLaunchConfig(model_path=str(tmp_path / "missing.gguf")).validate()


def test_requires_llama_server_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    monkeypatch.setattr("rlm_proxy.managed_llama.shutil.which", lambda _: None)

    with pytest.raises(ValueError, match="was not found"):
        LlamaServerLaunchConfig(model_path=str(model)).validate()


def test_custom_runtime_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    binary = tmp_path / "server"
    binary.write_text("binary")
    monkeypatch.setattr("rlm_proxy.managed_llama.shutil.which", lambda _: str(binary))

    config = LlamaServerLaunchConfig(
        model_path=str(model),
        context_size=8192,
        parallel=2,
        cache_type_k="f16",
        cache_type_v="f16",
        gpu_layers="20",
    )
    command = config.command()

    assert command[command.index("--ctx-size") + 1] == "8192"
    assert command[command.index("--parallel") + 1] == "2"
    assert command[command.index("--n-gpu-layers") + 1] == "20"
