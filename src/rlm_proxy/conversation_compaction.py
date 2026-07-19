"""Deterministic rolling-memory compaction policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class CompactableMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CompactionPolicy:
    max_messages: int = 32
    preserve_recent: int = 12
    max_summary_chars: int = 8000

    def validate(self) -> None:
        if self.max_messages < 1:
            raise ValueError("max_messages must be positive")
        if self.preserve_recent < 1:
            raise ValueError("preserve_recent must be positive")
        if self.preserve_recent > self.max_messages:
            raise ValueError("preserve_recent cannot exceed max_messages")
        if self.max_summary_chars < 1:
            raise ValueError("max_summary_chars must be positive")


@dataclass(frozen=True)
class CompactionPlan:
    should_compact: bool
    summarized_messages: Tuple[CompactableMessage, ...]
    retained_messages: Tuple[CompactableMessage, ...]


def plan_compaction(
    messages: Sequence[CompactableMessage], policy: CompactionPolicy
) -> CompactionPlan:
    """Split old messages from the recent context window."""
    policy.validate()
    if len(messages) <= policy.max_messages:
        return CompactionPlan(False, (), tuple(messages))
    split_at = max(0, len(messages) - policy.preserve_recent)
    return CompactionPlan(
        True,
        tuple(messages[:split_at]),
        tuple(messages[split_at:]),
    )


def deterministic_summary(
    previous_summary: str,
    messages: Iterable[CompactableMessage],
    max_chars: int,
) -> str:
    """Produce a stable extractive summary without invoking a model."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    sections: List[str] = []
    previous = previous_summary.strip()
    if previous:
        sections.append("Previous memory:\n" + previous)
    rendered = [
        "%s: %s" % (message.role.strip() or "unknown", _normalize(message.content))
        for message in messages
        if message.content.strip()
    ]
    if rendered:
        sections.append("Compacted turns:\n" + "\n".join(rendered))
    combined = "\n\n".join(sections).strip()
    if len(combined) <= max_chars:
        return combined
    marker = "\n...[truncated]"
    available = max(0, max_chars - len(marker))
    return combined[:available].rstrip() + marker


def compact_context(
    previous_summary: str,
    messages: Sequence[CompactableMessage],
    policy: CompactionPolicy,
) -> Tuple[str, Tuple[CompactableMessage, ...]]:
    plan = plan_compaction(messages, policy)
    if not plan.should_compact:
        return previous_summary, plan.retained_messages
    return (
        deterministic_summary(
            previous_summary,
            plan.summarized_messages,
            policy.max_summary_chars,
        ),
        plan.retained_messages,
    )


def _normalize(value: str) -> str:
    return " ".join(value.split())


__all__ = [
    "CompactableMessage",
    "CompactionPlan",
    "CompactionPolicy",
    "compact_context",
    "deterministic_summary",
    "plan_compaction",
]
