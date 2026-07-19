"""Supported RC1 process entrypoints."""

from __future__ import annotations

import argparse
import os

import uvicorn


def _serve(app: str, description: str, default_port: int) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


def proxy_main() -> None:
    """Run the stable OpenAI-compatible proxy."""
    _serve("rlm_proxy.app:app", "Run the Local RLM proxy", 8000)


def memory_main() -> None:
    """Run the memory-aware proxy gateway."""
    os.environ.setdefault("RLM_MEMORY_DB", "rlm-memory.sqlite3")
    _serve("rlm_proxy.memory_gateway:app", "Run the Local RLM memory gateway", 8001)


def control_main() -> None:
    """Run the secured administrative control plane."""
    _serve("rlm_proxy.control_plane:app", "Run the Local RLM control plane", 8020)


__all__ = ["control_main", "memory_main", "proxy_main"]
