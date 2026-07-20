"""OpenAI-compatible HTTP proxy for recursive-llm.

Importing :mod:`rlm_proxy` remains safe when optional proxy dependencies are not
installed. The public ``create_app`` entrypoint imports the FastAPI application
factory only when called.
"""

from __future__ import annotations

from typing import Any


def create_app(*args: Any, **kwargs: Any) -> Any:
    """Create the proxy application without eagerly importing proxy extras."""
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
