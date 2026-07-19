import pytest

from rlm_proxy.conversation_compaction import (
    CompactableMessage,
    CompactionPolicy,
    compact_context,
    deterministic_summary,
    plan_compaction,
)


def messages(count: int):
    return [CompactableMessage("user", "message %d" % index) for index in range(count)]


def test_plan_preserves_recent_window() -> None:
    plan = plan_compaction(messages(6), CompactionPolicy(max_messages=4, preserve_recent=2))

    assert plan.should_compact is True
    assert [item.content for item in plan.summarized_messages] == [
        "message 0",
        "message 1",
        "message 2",
        "message 3",
    ]
    assert [item.content for item in plan.retained_messages] == ["message 4", "message 5"]


def test_summary_is_stable_and_bounded() -> None:
    value = deterministic_summary(
        "Earlier context",
        [CompactableMessage("assistant", " spaced   content ")],
        48,
    )

    assert len(value) <= 48
    assert value.endswith("...[truncated]")


def test_compact_context_is_noop_under_limit() -> None:
    summary, retained = compact_context(
        "existing",
        messages(2),
        CompactionPolicy(max_messages=4, preserve_recent=2),
    )

    assert summary == "existing"
    assert len(retained) == 2


def test_policy_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        plan_compaction(messages(1), CompactionPolicy(max_messages=2, preserve_recent=3))
