"""Lifecycle management for a proxy process launched from the admin UI."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ProxyLaunchConfig:
    host: str
    port: int
    public_api_key: str
    private_api_base: str
    private_api_key: str
    model: str
    recursive_model: str
    max_depth: int
    max_iterations: int
    knowledge_api_base: Optional[str] = None

    @property
    def url(self) -> str:
        client_host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{client_host}:{self.port}"

    def validate(self) -> None:
        if not self.host.strip():
            raise ValueError("Proxy host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("Proxy port must be between 1 and 65535")
        if not self.private_api_base.startswith(("http://", "https://")):
            raise ValueError("Private API base must begin with http:// or https://")
        if self.knowledge_api_base is not None and not self.knowledge_api_base.startswith(
            ("http://", "https://")
        ):
            raise ValueError("Knowledge API base must begin with http:// or https://")
        if not self.model.strip():
            raise ValueError("Model is required")
        if self.max_depth < 0:
            raise ValueError("Maximum depth must be zero or greater")
        if self.max_iterations <= 0:
            raise ValueError("Maximum iterations must be greater than zero")

    def environment(self) -> Dict[str, str]:
        env = dict(os.environ)
        values = {
            "RLM_PROXY_PUBLIC_API_KEY": self.public_api_key,
            "RLM_PROXY_PRIVATE_API_BASE": self.private_api_base.rstrip("/"),
            "RLM_PROXY_PRIVATE_API_KEY": self.private_api_key or "not-needed",
            "RLM_PROXY_MODEL": self.model,
            "RLM_PROXY_RECURSIVE_MODEL": self.recursive_model or self.model,
            "RLM_PROXY_MAX_DEPTH": str(self.max_depth),
            "RLM_PROXY_MAX_ITERATIONS": str(self.max_iterations),
            "RLM_PROXY_KNOWLEDGE_API_BASE": (
                self.knowledge_api_base.rstrip("/") if self.knowledge_api_base else ""
            ),
        }
        for key, value in values.items():
            if value:
                env[key] = value
            else:
                env.pop(key, None)
        return env


class ManagedProxy:
    """Own at most one child uvicorn process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._config: Optional[ProxyLaunchConfig] = None

    def status(self) -> Dict[str, object]:
        with self._lock:
            process = self._process
            config = self._config
            running = process is not None and process.poll() is None
            return {
                "running": running,
                "pid": process.pid if running and process is not None else None,
                "url": config.url if config is not None else None,
                "exit_code": process.poll() if process is not None and not running else None,
            }

    def start(self, config: ProxyLaunchConfig, timeout_seconds: float = 15.0) -> Dict[str, object]:
        config.validate()
        self.stop()
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "rlm_proxy.app:app",
            "--host",
            config.host,
            "--port",
            str(config.port),
        ]
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
                raise RuntimeError(f"Proxy exited during startup with code {process.returncode}")
            try:
                with socket.create_connection((probe_host, config.port), timeout=0.25):
                    return self.status()
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise TimeoutError(f"Proxy did not listen on {probe_host}:{config.port}")

    def stop(self, timeout_seconds: float = 5.0) -> Dict[str, object]:
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


managed_proxy = ManagedProxy()
