import sqlite3
from pathlib import Path

import pytest

from rlm_proxy.catalog_store import SlotRegistry
from rlm_proxy.catalog_transfer import backup_catalog_database
from rlm_proxy.conversation_memory import ConversationMemoryStore


def test_catalog_backup_restores_version_and_data(tmp_path: Path) -> None:
    source = tmp_path / "catalog.sqlite3"
    backup = tmp_path / "catalog-backup.sqlite3"
    registry = SlotRegistry(str(source))
    initial = registry.snapshot()
    registry.replace(initial, expected_version=initial.version)
    expected = registry.snapshot()

    backup_catalog_database(registry, backup)
    restored = SlotRegistry(str(backup)).snapshot()

    assert restored.model_dump() == expected.model_dump()


def test_memory_database_survives_online_backup_restore(tmp_path: Path) -> None:
    source = tmp_path / "memory.sqlite3"
    restored_path = tmp_path / "memory-restored.sqlite3"
    store = ConversationMemoryStore(str(source))
    snapshot = store.create("conversation")
    snapshot = store.append("conversation", "user", "hello", snapshot.revision)
    store.append("conversation", "assistant", "world", snapshot.revision)

    with sqlite3.connect(restored_path) as restored_connection:
        store._connection.backup(restored_connection)

    restored = ConversationMemoryStore(str(restored_path)).get("conversation")

    assert [message.content for message in restored.messages] == ["hello", "world"]


def test_memory_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "future-memory.sqlite3"
    store = ConversationMemoryStore(str(path))
    store.create("seed")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE memory_meta SET schema_version = 999 WHERE singleton = 1")
        connection.commit()

    with pytest.raises(
        RuntimeError,
        match="unsupported conversation memory schema version",
    ):
        ConversationMemoryStore(str(path))
