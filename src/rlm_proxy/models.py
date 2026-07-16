"""Small OpenAI-compatible request models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]], None] = None
    name: Optional[str] = None


class RLMOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Optional[str] = None
    max_depth: Optional[int] = Field(default=None, ge=0)
    max_iterations: Optional[int] = Field(default=None, gt=0)
    max_total_calls: Optional[int] = Field(default=None, gt=0)
    max_total_tokens: Optional[int] = Field(default=None, gt=0)
    max_elapsed_seconds: Optional[float] = Field(default=None, gt=0)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: List[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None
    rlm: Optional[RLMOptions] = None
