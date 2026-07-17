from __future__ import annotations

from typing import Any, Dict, List

import rlm_proxy.stack_ui as stack_ui


class FakeManager:
    def __init__(self, name: str, events: List[str], fail_start: bool = False) -> None:
        self.name = name
        self.events = events
        self.fail_start = fail_start
        self.running = False

    def start(self, config: Any) -> Dict[str, Any]:
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError(f"{self.name} failed")
        self.running = True
        return self.status()

    def stop(self) -> Dict[str, Any]:
        self.events.append(f"stop:{self.name}")
        self.running = False
        return self.status()

    def status(self) -> Dict[str, Any]:
        return {"running": self.running, "name": self.name}


def _arguments(tmp_path: Any) -> tuple[Any, ...]:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    binary = tmp_path / "llama-server"
    binary.write_text("binary")
    binary.chmod(0o755)
    return (
        str(binary),
        str(model),
        "127.0.0.1",
        8080,
        16384,
        1,
        "q8_0",
        "q4_0",
        "all",
        "127.0.0.1",
        8000,
        "local-key",
        2,
        20,
        "127.0.0.1",
        3000,
        str(tmp_path / "webui"),
        False,
        False,
    )


def test_default_llama_binary_uses_bundle_environment(monkeypatch: Any, tmp_path: Any) -> None:
    binary = tmp_path / "llama-server"
    monkeypatch.setenv("RLM_BUNDLED_LLAMA_SERVER", str(binary))
    assert stack_ui.default_llama_binary() == str(binary)


def test_default_llama_binary_falls_back_to_path(monkeypatch: Any) -> None:
    monkeypatch.delenv("RLM_BUNDLED_LLAMA_SERVER", raising=False)
    assert stack_ui.default_llama_binary() == "llama-server"


def test_complete_stack_starts_in_dependency_order(monkeypatch: Any, tmp_path: Any) -> None:
    events: List[str] = []
    llama = FakeManager("llama", events)
    proxy = FakeManager("proxy", events)
    webui = FakeManager("webui", events)
    monkeypatch.setattr(stack_ui, "managed_llama_server", llama)
    monkeypatch.setattr(stack_ui, "managed_proxy", proxy)
    monkeypatch.setattr(stack_ui, "managed_webui", webui)

    message, proxy_url, key, webui_url, details = stack_ui.start_complete_stack(
        *_arguments(tmp_path)
    )

    assert "running" in message
    assert proxy_url == "http://127.0.0.1:8000"
    assert key == "local-key"
    assert webui_url == "http://127.0.0.1:3000"
    assert all(value["running"] for value in details.values())
    assert events[-3:] == ["start:llama", "start:proxy", "start:webui"]


def test_complete_stack_cleans_up_after_failure(monkeypatch: Any, tmp_path: Any) -> None:
    events: List[str] = []
    llama = FakeManager("llama", events)
    proxy = FakeManager("proxy", events, fail_start=True)
    webui = FakeManager("webui", events)
    monkeypatch.setattr(stack_ui, "managed_llama_server", llama)
    monkeypatch.setattr(stack_ui, "managed_proxy", proxy)
    monkeypatch.setattr(stack_ui, "managed_webui", webui)

    message, _, _, _, details = stack_ui.start_complete_stack(*_arguments(tmp_path))

    assert "failed" in message
    assert not any(value["running"] for value in details.values())
    assert events[-3:] == ["stop:webui", "stop:proxy", "stop:llama"]


def test_stop_complete_stack_uses_reverse_order(monkeypatch: Any) -> None:
    events: List[str] = []
    monkeypatch.setattr(stack_ui, "managed_llama_server", FakeManager("llama", events))
    monkeypatch.setattr(stack_ui, "managed_proxy", FakeManager("proxy", events))
    monkeypatch.setattr(stack_ui, "managed_webui", FakeManager("webui", events))

    message, _ = stack_ui.stop_complete_stack()

    assert message == "Complete local stack stopped"
    assert events == ["stop:webui", "stop:proxy", "stop:llama"]
