"""Shared read-only DB helpers for scripts/ tools.

Purpose: the bit every ops script needs — a strictly read-only connection
to the bot's live SQLite file, plus the shared `--db` CLI flag.

Current state: fully implemented.
TODO: none open.
Notes: intentionally not `db.connection.Database` — that class replays
schema.sql on connect (`apply_schema()`), which a read-only report script
has no reason to do and shouldn't risk attempting at all, let alone
alongside a running bot. `mode=ro` at the SQLite level physically cannot
write, so it's safe to run concurrently with the bot regardless of what
else is happening to the file — WAL mode (already enabled by the bot) is
what makes concurrent readers like this actually work.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


def open_readonly(db_path: str) -> sqlite3.Connection:
    """Open the bot's SQLite file strictly read-only; safe alongside a running bot."""
    resolved = Path(db_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"no database at {resolved}")

    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared `--db` flag, defaulting to $DB_PATH (from .env) or data/wcrl.db."""
    load_dotenv()
    parser.add_argument(
        "--db",
        default=os.getenv("DB_PATH", "data/wcrl.db"),
        help="Path to the bot's SQLite file (default: $DB_PATH, or data/wcrl.db).",
    )
