"""Shared pytest fixtures.

Current state: fully implemented (single `db` fixture).
TODO: none open.
Notes: none.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connection import Database  # noqa: E402


@pytest_asyncio.fixture
async def db():
    """A fresh in-memory database with the real schema applied."""
    database = Database(":memory:")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()
