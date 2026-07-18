"""Validated proxy configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from RLM_PROXY_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="RLM_PROXY_",
        env_file=".env",
        extra="ignore",
    )

    public_api_key: Optional[SecretStr] = None
    private_api_base: str = Field(min_length=1)
    private_api_key: SecretStr = SecretStr("not-needed")
    model: str = Field(default="openai/local", min_length=1)
    recursive_model: Optional[str] = None

    knowledge_api_base: Optional[str] = None
    knowledge_timeout_seconds: float = Field(default=30.0, gt=0)
    knowledge_candidate_limit: int = Field(default=24, gt=0)
    knowledge_result_limit: int = Field(default=6, gt=0)
    knowledge_max_context_chars: int = Field(default=24000, gt=0)

    max_depth: int = Field(default=2, ge=0)
    max_iterations: int = Field(default=20, gt=0)
    repl_timeout: float = Field(default=5.0, gt=0)
    max_output_chars: int = Field(default=4000, gt=0)
    max_concurrent_subcalls: int = Field(default=4, gt=0)
    max_total_calls: Optional[int] = Field(default=32, gt=0)
    max_total_tokens: Optional[int] = Field(default=None, gt=0)
    max_total_cost_usd: Optional[float] = Field(default=None, gt=0)
    max_elapsed_seconds: Optional[float] = Field(default=300.0, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Required values are supplied by BaseSettings from RLM_PROXY_* variables.
    return Settings()  # type: ignore[call-arg]
