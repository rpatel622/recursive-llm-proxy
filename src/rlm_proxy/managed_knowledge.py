"""Lifecycle management for the native knowledge service."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.request import urlopen


@dataclass(frozen=True)
class KnowledgeServiceLaunchConfig:
    binary: str
    host: str = "127.0.0.1"
    port: int = 8010
    data_dir: str = "~/.recursive-llm/knowledge"

    @property
    def url(self) -> str:
        client_host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{client_host}:{self.port}"

    @property
    def database_path(self) -> Path:
        return Path(self.data_dir).expanduser() / "knowledge.sqlite3"

    @property
    def log_path(self) -> Path:
        return Path(self.data_dir).expanduser() / "knowledge-service.log"

    def validate(self) -> None:
        if not self.binary.strip():
            raise ValueError("Knowledge service binary is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("Knowledge service port must be between 1 and 65535")
        if not self.host.strip():
            raise ValueError("Knowledge service host is required")

    def environment(self) -> Dict[str, str]:
        env = dict(os.environ)
        env["RLM_KNOWLEDGE_BIND"] = f"{self.host}:{self.port}"
        env["RLM_KNOWLEDGE_DB"] = str(self.database_path)
        return env


class ManagedKnowledgeService:
    """Own at most one native knowledge service process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._config: Optional[KnowledgeServiceLaunchConfig] = None
        self._log_handle: Optional[object] = None

    def status(self) -> Dict[str, object]:
        with self._lock:
            process = self._process
            config = self._config
            running = process is not None and process.poll() is None
            return {
                "running": running,
                "pid": process.pid if running and process is not None else None,
                "url": config.url if config is not None else None,
                "database_path": str(config.database_path) if config is not None else None,
                "log_path": str(config.log_path) if config is not None else None,
                "exit_code": process.poll() if process is not None and not running else None,
            }

    def start(
        self,
        config: KnowledgeServiceLaunchConfig,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, object]:
        config.validate()
        self.stop()
        config.database_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = config.log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [config.binary],
            env=config.environment(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with self._lock:
            self._process = process
            self._config = config
            self._log_handle = log_handle

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "Knowledge service exited during startup with code "
                    f"{process.returncode}. See {config.log_path}"
                )
            try:
                with urlopen(f"{config.url}/healthz", timeout=0.5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if response.status == 200 and payload.get("status") == "ok":
                        return self.status()
            except (OSError, ValueError):
                try:
                    probe_host = "127.0.0.1" if config.host in {"0.0.0.0", "::"} else config.host
                    with socket.create_connection((probe_host, config.port), timeout=0.2):
                        pass
                except OSError:
                    pass
            time.sleep(0.2)
        self.stop()
        raise TimeoutError(
            f"Knowledge service did not become healthy at {config.url}; see {config.log_path}"
        )

    def stop(self, timeout_seconds: float = 5.0) -> Dict[str, object]:
        with self._lock:
            process = self._process
            log_handle = self._log_handle
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_seconds)
        if log_handle is not None:
            close = getattr(log_handle, "close", None)
            if close is not None:
                close()
        with self._lock:
            self._log_handle = None
        return self.status()


managed_knowledge_service = ManagedKnowledgeService()
