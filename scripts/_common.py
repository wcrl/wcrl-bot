"""Shared read-only DB helpers for scripts/ tools."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


def open_readonly(db_path: str) -> sqlite3.Connection:
    """Open the bot's SQLite file strictly read-only; safe alongside a running bot."""
    # Deliberately plain sqlite3, not wcrl_db.Database — that class replays
    # schema.sql on connect, which a read-only report script must never risk,
    # especially alongside a running bot. mode=ro physically cannot write,
    # so this is safe to run concurrently regardless (WAL is what makes
    # concurrent readers like this actually work).
    resolved = Path(db_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"no database at {resolved}")

    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared `--db` flag, defaulting to $DATA_DIR/wcrl.db (from .env) or data/wcrl.db."""
    load_dotenv()
    data_dir = os.getenv("DATA_DIR", "data").strip() or "data"
    parser.add_argument(
        "--db",
        default=os.path.join(data_dir, "wcrl.db"),
        help="Path to the bot's SQLite file (default: $DATA_DIR/wcrl.db, or data/wcrl.db).",
    )
