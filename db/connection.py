"""aiosqlite connection management — the only path to the database.

Current state: fully implemented.
TODO: none open.
Notes: one shared connection is safe because the bot always runs as a
single replica (CLAUDE.md > Deployment). `foreign_keys` is per-connection
and off by default — the `ON DELETE CASCADE` on team disband depends on
turning it on here. WAL's `-wal`/`-shm` sidecar files must live on the same
mounted volume as the db file itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    """Owns the app's aiosqlite connection and exposes small query helpers."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been awaited yet")
        return self._conn

    async def connect(self) -> None:
        """Open the connection, apply pragmas, and replay the schema."""
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.commit()

        await self.apply_schema()
        log.info("database ready at %s", self.path)

    async def apply_schema(self) -> None:
        await self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await self.conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, tuple(params)) as cursor:
            return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(params)) as cursor:
            return list(await cursor.fetchall())

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Cursor:
        cursor = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cursor
