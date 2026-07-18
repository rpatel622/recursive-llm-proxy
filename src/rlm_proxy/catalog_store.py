"""Durable SQLite storage for slots, workstreams, and conversation turns."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Optional

from .models import SlotCatalog, SlotDefinition, StoredTurn, WorkstreamDefinition

_SCHEMA_VERSION = 1


class SlotRegistry:
    """Thread-safe catalog registry backed by SQLite.

    The registry keeps one connection open so ``:memory:`` remains useful in tests.
    Calling :meth:`configure` with the same path is a no-op; changing paths closes
    the previous connection and loads the new database.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._lock = RLock()
        self._path = ""
        self._connection: Optional[sqlite3.Connection] = None
        self.configure(path)

    def configure(self, path: str) -> None:
        normalized = str(Path(path).expanduser()) if path != ":memory:" else path
        with self._lock:
            if self._connection is not None and self._path == normalized:
                return
            if self._connection is not None:
                self._connection.close()
            if normalized != ":memory:":
                Path(normalized).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(normalized, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            self._connection = connection
            self._path = normalized
            self._migrate()

    @property
    def path(self) -> str:
        with self._lock:
            return self._path

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("slot registry is not configured")
        return self._connection

    def _migrate(self) -> None:
        connection = self._require_connection()
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalog_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL,
                    catalog_version INTEGER NOT NULL
                );
                INSERT INTO catalog_meta(singleton, schema_version, catalog_version)
                VALUES (1, 1, 0)
                ON CONFLICT(singleton) DO NOTHING;

                CREATE TABLE IF NOT EXISTS slots (
                    slug TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    position INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workstreams (
                    slot_slug TEXT NOT NULL REFERENCES slots(slug) ON DELETE CASCADE,
                    slug TEXT NOT NULL,
                    name TEXT,
                    description TEXT,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(slot_slug, slug)
                );

                CREATE TABLE IF NOT EXISTS turns (
                    slot_slug TEXT NOT NULL,
                    workstream_slug TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY(slot_slug, workstream_slug, ordinal),
                    FOREIGN KEY(slot_slug, workstream_slug)
                        REFERENCES workstreams(slot_slug, slug) ON DELETE CASCADE
                );
                """
            )
            row = connection.execute(
                "SELECT schema_version FROM catalog_meta WHERE singleton = 1"
            ).fetchone()
            if row is None or int(row[0]) != _SCHEMA_VERSION:
                raise RuntimeError("unsupported slot catalog schema version")

    def version(self) -> int:
        with self._lock:
            row = self._require_connection().execute(
                "SELECT catalog_version FROM catalog_meta WHERE singleton = 1"
            ).fetchone()
            return int(row[0]) if row else 0

    def snapshot(self) -> SlotCatalog:
        with self._lock:
            connection = self._require_connection()
            slots = []
            for slot_row in connection.execute(
                "SELECT slug, name, description FROM slots ORDER BY position, slug"
            ):
                workstreams = []
                for stream_row in connection.execute(
                    """
                    SELECT slug, name, description
                    FROM workstreams
                    WHERE slot_slug = ?
                    ORDER BY position, slug
                    """,
                    (slot_row["slug"],),
                ):
                    turns = [
                        StoredTurn(role=turn_row["role"], content=turn_row["content"])
                        for turn_row in connection.execute(
                            """
                            SELECT role, content
                            FROM turns
                            WHERE slot_slug = ? AND workstream_slug = ?
                            ORDER BY ordinal
                            """,
                            (slot_row["slug"], stream_row["slug"]),
                        )
                    ]
                    workstreams.append(
                        WorkstreamDefinition(
                            slug=stream_row["slug"],
                            name=stream_row["name"],
                            description=stream_row["description"],
                            turns=turns,
                        )
                    )
                slots.append(
                    SlotDefinition(
                        slug=slot_row["slug"],
                        name=slot_row["name"],
                        description=slot_row["description"],
                        workstreams=workstreams,
                    )
                )
            return SlotCatalog(slots=slots, version=self.version())

    def replace(self, catalog: SlotCatalog, expected_version: Optional[int] = None) -> SlotCatalog:
        with self._lock:
            connection = self._require_connection()
            current_version = self.version()
            if expected_version is not None and expected_version != current_version:
                raise ValueError(
                    f"catalog version conflict: expected {expected_version}, current {current_version}"
                )
            next_version = current_version + 1
            with connection:
                connection.execute("DELETE FROM slots")
                for slot_position, slot in enumerate(catalog.slots):
                    connection.execute(
                        "INSERT INTO slots(slug, name, description, position) VALUES (?, ?, ?, ?)",
                        (slot.slug, slot.name, slot.description, slot_position),
                    )
                    for stream_position, stream in enumerate(slot.workstreams):
                        connection.execute(
                            """
                            INSERT INTO workstreams(
                                slot_slug, slug, name, description, position
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                slot.slug,
                                stream.slug,
                                stream.name,
                                stream.description,
                                stream_position,
                            ),
                        )
                        for ordinal, turn in enumerate(stream.turns):
                            connection.execute(
                                """
                                INSERT INTO turns(
                                    slot_slug, workstream_slug, ordinal, role, content
                                ) VALUES (?, ?, ?, ?, ?)
                                """,
                                (slot.slug, stream.slug, ordinal, turn.role, turn.content),
                            )
                connection.execute(
                    "UPDATE catalog_meta SET catalog_version = ? WHERE singleton = 1",
                    (next_version,),
                )
            return self.snapshot()

    def append_turn(
        self,
        slot_slug: str,
        workstream_slug: str,
        turn: StoredTurn,
        expected_version: Optional[int] = None,
    ) -> SlotCatalog:
        with self._lock:
            connection = self._require_connection()
            current_version = self.version()
            if expected_version is not None and expected_version != current_version:
                raise ValueError(
                    f"catalog version conflict: expected {expected_version}, current {current_version}"
                )
            exists = connection.execute(
                """
                SELECT 1 FROM workstreams
                WHERE slot_slug = ? AND slug = ?
                """,
                (slot_slug, workstream_slug),
            ).fetchone()
            if exists is None:
                raise ValueError(f"unknown workstream slug: {slot_slug}/{workstream_slug}")
            row = connection.execute(
                """
                SELECT COALESCE(MAX(ordinal), -1) + 1
                FROM turns
                WHERE slot_slug = ? AND workstream_slug = ?
                """,
                (slot_slug, workstream_slug),
            ).fetchone()
            ordinal = int(row[0])
            with connection:
                connection.execute(
                    """
                    INSERT INTO turns(slot_slug, workstream_slug, ordinal, role, content)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (slot_slug, workstream_slug, ordinal, turn.role, turn.content),
                )
                connection.execute(
                    "UPDATE catalog_meta SET catalog_version = catalog_version + 1 WHERE singleton = 1"
                )
            return self.snapshot()

    def delete_workstream(
        self,
        slot_slug: str,
        workstream_slug: str,
        expected_version: Optional[int] = None,
    ) -> SlotCatalog:
        with self._lock:
            connection = self._require_connection()
            current_version = self.version()
            if expected_version is not None and expected_version != current_version:
                raise ValueError(
                    f"catalog version conflict: expected {expected_version}, current {current_version}"
                )
            with connection:
                cursor = connection.execute(
                    "DELETE FROM workstreams WHERE slot_slug = ? AND slug = ?",
                    (slot_slug, workstream_slug),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"unknown workstream slug: {slot_slug}/{workstream_slug}")
                connection.execute(
                    "UPDATE catalog_meta SET catalog_version = catalog_version + 1 WHERE singleton = 1"
                )
            return self.snapshot()
