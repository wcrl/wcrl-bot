"""Ops helper: lists competitors who still need to fill in year/major.

Purpose: a quick report for officers — who has a `competitors` row but no
matching `competitor_profiles` row (i.e. registered before year/major
existed, or skipped it) and so still needs to re-run `/register`.

Current state: fully implemented.
TODO: none open.
Notes: read-only connection details live in `scripts/_common.py`. Never
prints `school_email` — same policy as the rest of the codebase.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import add_db_argument, open_readonly  # noqa: E402


def fetch_incomplete_registrations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Competitors with no `competitor_profiles` row yet (missing year/major)."""
    return conn.execute(
        """
        SELECT competitors.discord_id, competitors.full_name, competitors.registered_at
        FROM competitors
        LEFT JOIN competitor_profiles ON competitor_profiles.discord_id = competitors.discord_id
        WHERE competitor_profiles.discord_id IS NULL
        ORDER BY competitors.registered_at
        """
    ).fetchall()


def format_report(rows: list[sqlite3.Row]) -> str:
    """Render the report as plain text, one line per competitor."""
    if not rows:
        return "Everyone registered has filled in their year and major."

    lines = [f"{len(rows)} competitor(s) still need to run /register to add year/major:", ""]
    lines.extend(
        f"- {row['full_name']} (<@{row['discord_id']}>, id {row['discord_id']}) "
        f"— registered {row['registered_at']}"
        for row in rows
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_db_argument(parser)
    args = parser.parse_args()

    conn = open_readonly(args.db)
    try:
        rows = fetch_incomplete_registrations(conn)
    finally:
        conn.close()

    print(format_report(rows))


if __name__ == "__main__":
    main()
