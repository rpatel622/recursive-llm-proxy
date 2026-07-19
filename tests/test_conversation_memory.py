from pathlib import Path

import pytest

from rlm_proxy.conversation_memory import ConversationMemoryStore


def test_memory_persists_messages_and_summary(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    first = ConversationMemoryStore(str(path))
    first.create("chat-1")
    first.append("chat-1", "user", "Hello", expected_revision=0)
    first.update_summary("chat-1", "Greeting", expected_revision=1)

    second = ConversationMemoryStore(str(path))
    snapshot = second.get("chat-1")

    assert snapshot.revision == 2
    assert snapshot.summary == "Greeting"
    assert [message.content for message in snapshot.messages] == ["Hello"]


def test_memory_rejects_stale_revision() -> None:
    store = ConversationMemoryStore(":memory:")
    store.create("chat-1")
    store.append("chat-1", "user", "Hello", expected_revision=0)

    with pytest.raises(ValueError, match="revision conflict"):
        store.append("chat-1", "assistant", "Hi", expected_revision=0)


def test_recent_order_and_delete(monkeypatch: object) -> None:
    timestamps = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr("rlm_proxy.conversation_memory.time.time", lambda: next(timestamps))
    store = ConversationMemoryStore(":memory:")
    store.create("older")
    store.create("newer")
    store.append("older", "user", "updated")

    assert [item.conversation_id for item in store.list_recent()] == ["older", "newer"]
    assert store.delete("older") is True
    assert store.delete("older") is False
    with pytest.raises(KeyError):
        store.get("older")
