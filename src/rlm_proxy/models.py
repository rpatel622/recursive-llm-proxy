"""Small OpenAI-compatible request and routing models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]], None] = None
    name: Optional[str] = None


class StoredTurn(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str


class WorkstreamDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: Optional[str] = None
    description: Optional[str] = None
    turns: List[StoredTurn] = Field(default_factory=list)


class SlotDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: Optional[str] = None
    description: Optional[str] = None
    workstreams: List[WorkstreamDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_workstreams(self) -> "SlotDefinition":
        slugs = [item.slug for item in self.workstreams]
        if len(slugs) != len(set(slugs)):
            raise ValueError("workstream slugs must be unique within a slot")
        return self


class SlotCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: List[SlotDefinition]
    version: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def unique_slots(self) -> "SlotCatalog":
        slugs = [item.slug for item in self.slots]
        if len(slugs) != len(set(slugs)):
            raise ValueError("slot slugs must be unique")
        return self


class RoutingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "explicit", "clarify_only"] = "auto"
    slot_slug: Optional[str] = None
    workstream_slugs: List[str] = Field(default_factory=list)
    initial_turn_count: int = Field(default=4, gt=0)
    max_turn_count: int = Field(default=64, gt=0)
    allow_multi_workstream: bool = True
    allow_cross_slot: bool = False

    @model_validator(mode="after")
    def validate_bounds(self) -> "RoutingOptions":
        if self.initial_turn_count > self.max_turn_count:
            raise ValueError("initial_turn_count must not exceed max_turn_count")
        if self.mode == "explicit" and not self.slot_slug:
            raise ValueError("explicit routing requires slot_slug")
        return self


class IngestionOptions(BaseModel):
    """Controls rolling preprocessing of oversized final user messages."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    threshold_chars: int = Field(default=24000, gt=0)
    window_chars: int = Field(default=12000, gt=0)
    overlap_chars: int = Field(default=800, ge=0)
    max_windows: int = Field(default=128, gt=0)
    metadata_chars: int = Field(default=4000, gt=0)

    @model_validator(mode="after")
    def validate_window(self) -> "IngestionOptions":
        if self.overlap_chars >= self.window_chars:
            raise ValueError("overlap_chars must be smaller than window_chars")
        return self


class KnowledgeOptions(BaseModel):
    """Controls optional persistent knowledge retrieval for a chat request."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    candidate_limit: Optional[int] = Field(default=None, gt=0)
    limit: Optional[int] = Field(default=None, gt=0)
    rerank: bool = True
    max_context_chars: Optional[int] = Field(default=None, gt=0)
    required: bool = False


class RLMOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: Optional[str] = None
    routing: Optional[RoutingOptions] = None
    ingestion: Optional[IngestionOptions] = None
    knowledge: Optional[KnowledgeOptions] = None
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
