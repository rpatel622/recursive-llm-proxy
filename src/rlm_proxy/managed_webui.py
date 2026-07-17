"""Lifecycle management for a local Open WebUI cowork interface."""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class WebUILaunchConfig:
    host: str = "127.0.0.1"
    port: int = 3000
    proxy_url: str = "http://127.0.0.1:8000"
    proxy_api_key: str = ""
    data_dir: str = "~/.recursive-llm/open-webui"
    auth_enabled: bool = False
    open_browser: bool = True

    @property
    def url(self) -> str:
        client_host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{client_host}:{self.port}"

    def validate(self) -> None:
        if not self.host.strip():
            raise ValueError("Open WebUI host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("Open WebUI port must be between 1 and 65535")
        if not self.proxy_url.startswith(("http://", "https://")):
            raise ValueError("Proxy URL must begin with http:// or https://")
        if not self.data_dir.strip():
            raise ValueError("Open WebUI data directory is required")

    def environment(self) -> Dict[str, str]:
        data_dir = Path(self.data_dir).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update(
            {
                "DATA_DIR": str(data_dir),
                "ENABLE_OPENAI_API": "True",
                "OPENAI_API_BASE_URL": f"{self.proxy_url.rstrip('/')}/v1",
                "OPENAI_API_BASE_URLS": f"{self.proxy_url.rstrip('/')}/v1",
                "OPENAI_API_KEY": self.proxy_api_key or "local-no-key",
                "OPENAI_API_KEYS": self.proxy_api_key or "local-no-key",
                "OPENAI_API_CONFIGS": '{"0":{"enable":true,"prefix_id":"","model_ids":["rlm"],"tags":["local"]}}',
                "ENABLE_OLLAMA_API": "False",
                "WEBUI_AUTH": "True" if self.auth_enabled else "False",
                "WEBUI_NAME": "Local RLM Cowork",
                "TASK_MODEL_EXTERNAL": "rlm",
                "ENABLE_CONTEXT_COMPACTION": "True",
                "UVICORN_WORKERS": "1",
                "WEBUI_SECRET_KEY": env.get("RLM_COWORK_SECRET_KEY", secrets.token_hex(32)),
            }
        )
        return env


class ManagedWebUI:
    """Own at most one local Open WebUI child process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._config: Optional[WebUILaunchConfig] = None

    def status(self) -> Dict[str, object]:
        with self._lock:
            process = self._process
            config = self._config
            running = process is not None and process.poll() is None
            return {
                "running": running,
                "pid": process.pid if running and process is not None else None,
                "url": config.url if config is not None else None,
                "data_dir": config.data_dir if config is not None else None,
                "auth_enabled": config.auth_enabled if config is not None else None,
                "exit_code": process.poll() if process is not None and not running else None,
            }

    def start(self, config: WebUILaunchConfig, timeout_seconds: float = 90.0) -> Dict[str, object]:
        config.validate()
        self.stop()
        command = [sys.executable, "-m", "open_webui", "serve", "--host", config.host, "--port", str(config.port)]
        process = subprocess.Popen(
            command,
            env=config.environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        with self._lock:
            self._process = process
            self._config = config

        deadline = time.monotonic() + timeout_seconds
        probe_host = "127.0.0.1" if config.host in {"0.0.0.0", "::"} else config.host
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "Open WebUI exited during startup. Install the cowork extra with "
                    "python -m pip install -e '.[proxy,ui,cowork]'"
                )
            try:
                with socket.create_connection((probe_host, config.port), timeout=0.25):
                    if config.open_browser:
                        import webbrowser

                        webbrowser.open(config.url)
                    return self.status()
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise TimeoutError(f"Open WebUI did not listen on {probe_host}:{config.port}")

    def stop(self, timeout_seconds: float = 10.0) -> Dict[str, object]:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return self.status()
        process.terminate()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout_seconds)
        return self.status()


managed_webui = ManagedWebUI()
