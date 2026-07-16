"""OpenAI-compatible HTTP proxy for recursive-llm."""

from .app import create_app

__all__ = ["create_app"]
