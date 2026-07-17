"""Lifecycle management for a local llama.cpp server process."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class LlamaServerLaunchConfig:
    model_path: str
    binary: str = "llama-server"
    host: str = "127.0.0.1"
    port: int = 8080
    context_size: int = 16384
    parallel: int = 1
    cache_type_k: str = "q8_0"
    cache_type_v: str = "q4_0"
    gpu_layers: str = "all"

    @property
    def url(self) -> str:
        client_host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{client_host}:{self.port}/v1"

    def resolved_binary(self) -> str:
        candidate = os.path.expanduser(self.binary)
        if os.path.sep in candidate or (os.path.altsep and os.path.altsep in candidate):
            return str(Path(candidate).resolve())
        resolved = shutil.which(candidate)
        if resolved is None:
            raise ValueError(
                "llama-server was not found. Install llama.cpp or pass --llama-binary."
            )
        return resolved

    def validate(self) -> None:
        if not self.model_path.strip():
            raise ValueError("A GGUF model path is required")
        model = Path(os.path.expanduser(self.model_path))
        if not model.is_file():
            raise ValueError(f"GGUF model does not exist: {model}")
        if model.suffix.lower() != ".gguf":
            raise ValueError("Model path must point to a .gguf file")
        self.resolved_binary()
        if not self.host.strip():
            raise ValueError("llama-server host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("llama-server port must be between 1 and 65535")
        if self.context_size <= 0:
            raise ValueError("Context size must be greater than zero")
        if self.parallel <= 0:
            raise ValueError("Parallel slots must be greater than zero")

    def command(self) -> list[str]:
        self.validate()
        return [
            self.resolved_binary(),
            "--model",
            str(Path(os.path.expanduser(self.model_path)).resolve()),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--ctx-size",
            str(self.context_size),
            "--parallel",
            str(self.parallel),
            "--cache-type-k",
            self.cache_type_k,
            "--cache-type-v",
            self.cache_type_v,
            "--n-gpu-layers",
            self.gpu_layers,
        ]


class ManagedLlamaServer:
    """Own at most one local llama-server child process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._config: Optional[LlamaServerLaunchConfig] = None

    def status(self) -> Dict[str, object]:
        with self._lock:
            process = self._process
            config = self._config
            running = process is not None and process.poll() is None
            return {
                "running": running,
                "pid": process.pid if running and process is not None else None,
                "url": config.url if config is not None else None,
                "model_path": config.model_path if config is not None else None,
                "exit_code": process.poll() if process is not None and not running else None,
            }

    def start(
        self, config: LlamaServerLaunchConfig, timeout_seconds: float = 60.0
    ) -> Dict[str, object]:
        self.stop()
        command = config.command()
        process = subprocess.Popen(
            command,
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
                    f"llama-server exited during startup with code {process.returncode}"
                )
            try:
                with socket.create_connection((probe_host, config.port), timeout=0.25):
                    return self.status()
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise TimeoutError(f"llama-server did not listen on {probe_host}:{config.port}")

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


managed_llama_server = ManagedLlamaServer()
