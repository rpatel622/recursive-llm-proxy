"""Durable SQLite conversation memory with optimistic revisions."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import List, Optional

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MemoryMessage:
    ordinal: int
    role: str
    content: str
    created_at: float


@dataclass(frozen=True)
class ConversationSnapshot:
    conversation_id: str
    revision: int
    summary: str
    messages: List[MemoryMessage]
    updated_at: float


class ConversationMemoryStore:
    """Thread-safe durable store for append-only messages and summaries."""

    def __init__(self, path: str) -> None:
        self._lock = RLock()
        normalized = str(Path(path).expanduser()) if path != ":memory:" else path
        if normalized != ":memory:":
            Path(normalized).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(normalized, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL
                );
                INSERT INTO memory_meta(singleton, schema_version)
                VALUES (1, 1)
                ON CONFLICT(singleton) DO NOTHING;

                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(conversation_id, ordinal)
                );
                """
            )
            row = self._connection.execute(
                "SELECT schema_version FROM memory_meta WHERE singleton = 1"
            ).fetchone()
            if row is None or int(row[0]) != _SCHEMA_VERSION:
                raise RuntimeError("unsupported conversation memory schema version")

    def create(self, conversation_id: str, summary: str = "") -> ConversationSnapshot:
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise ValueError("conversation id is required")
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO conversations(
                    conversation_id, revision, summary, created_at, updated_at
                ) VALUES (?, 0, ?, ?, ?)
                """,
                (conversation_id, summary, now, now),
            )
        return self.get(conversation_id)

    def get(self, conversation_id: str) -> ConversationSnapshot:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT conversation_id, revision, summary, updated_at
                FROM conversations WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(conversation_id)
            messages = [
                MemoryMessage(
                    ordinal=int(message["ordinal"]),
                    role=str(message["role"]),
                    content=str(message["content"]),
                    created_at=float(message["created_at"]),
                )
                for message in self._connection.execute(
                    """
                    SELECT ordinal, role, content, created_at
                    FROM conversation_messages
                    WHERE conversation_id = ? ORDER BY ordinal
                    """,
                    (conversation_id,),
                )
            ]
            return ConversationSnapshot(
                conversation_id=str(row["conversation_id"]),
                revision=int(row["revision"]),
                summary=str(row["summary"]),
                messages=messages,
                updated_at=float(row["updated_at"]),
            )

    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        expected_revision: Optional[int] = None,
    ) -> ConversationSnapshot:
        if not role.strip() or not content.strip():
            raise ValueError("message role and content are required")
        with self._lock:
            current = self.get(conversation_id)
            self._check_revision(current.revision, expected_revision)
            now = time.time()
            ordinal = len(current.messages)
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO conversation_messages(
                        conversation_id, ordinal, role, content, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (conversation_id, ordinal, role, content, now),
                )
                self._connection.execute(
                    """
                    UPDATE conversations
                    SET revision = revision + 1, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (now, conversation_id),
                )
        return self.get(conversation_id)

    def update_summary(
        self,
        conversation_id: str,
        summary: str,
        expected_revision: Optional[int] = None,
    ) -> ConversationSnapshot:
        with self._lock:
            current = self.get(conversation_id)
            self._check_revision(current.revision, expected_revision)
            now = time.time()
            with self._connection:
                self._connection.execute(
                    """
                    UPDATE conversations
                    SET summary = ?, revision = revision + 1, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (summary, now, conversation_id),
                )
        return self.get(conversation_id)

    def list_recent(self, limit: int = 20) -> List[ConversationSnapshot]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        with self._lock:
            ids = [
                str(row[0])
                for row in self._connection.execute(
                    """
                    SELECT conversation_id FROM conversations
                    ORDER BY updated_at DESC, conversation_id LIMIT ?
                    """,
                    (limit,),
                )
            ]
        return [self.get(conversation_id) for conversation_id in ids]

    def delete(self, conversation_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _check_revision(current: int, expected: Optional[int]) -> None:
        if expected is not None and expected != current:
            raise ValueError(
                "conversation revision conflict: expected %d, current %d" % (expected, current)
            )


__all__ = [
    "ConversationMemoryStore",
    "ConversationSnapshot",
    "MemoryMessage",
]
