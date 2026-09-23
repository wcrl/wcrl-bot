"""Tests for `scripts/list_incomplete_registrations.py`.

Current state: fully implemented — covers the read-only open (including the
missing-file case), the filtering query, and both report-text branches.
TODO: none open.
Notes: uses a real on-disk SQLite file (`tmp_path`) rather than `:memory:`,
since `open_readonly`'s `mode=ro` URI needs an actual file to attach to —
that's also what exercises the same code path used against the bot's real
`data/wcrl.db`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts._common import open_readonly
from scripts.list_incomplete_registrations import fetch_incomplete_registrations, format_report

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


@pytest.fixture
def db_path(tmp_path):
    """A real SQLite file with the bot's schema applied, plus two competitors."""
    path = tmp_path / "wcrl.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (1, 'Jane Doe', 'jane@uwaterloo.ca')"
        )
        conn.execute(
            "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (2, 'John Doe', 'john@uwaterloo.ca')"
        )
        conn.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (2, 'Junior', 'Computer Science')"
        )
        conn.commit()
    finally:
        conn.close()
    return path


class TestOpenReadonly:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            open_readonly(str(tmp_path / "does-not-exist.db"))

    def test_connection_is_actually_read_only(self, db_path):
        conn = open_readonly(str(db_path))
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO competitors (discord_id, full_name, school_email) VALUES (99, 'x', 'x@x.com')")
        finally:
            conn.close()


class TestFetchIncompleteRegistrations:
    def test_only_competitors_missing_a_profile_are_returned(self, db_path):
        conn = open_readonly(str(db_path))
        try:
            rows = fetch_incomplete_registrations(conn)
        finally:
            conn.close()

        assert [row["discord_id"] for row in rows] == [1]
        assert rows[0]["full_name"] == "Jane Doe"

    def test_everyone_complete_returns_no_rows(self, tmp_path):
        path = tmp_path / "complete.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (1, 'Jane Doe', 'jane@uwaterloo.ca')"
        )
        conn.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (1, 'Junior', 'Computer Science')"
        )
        conn.commit()
        conn.close()

        conn = open_readonly(str(path))
        try:
            assert fetch_incomplete_registrations(conn) == []
        finally:
            conn.close()


class TestFormatReport:
    def test_empty_list_reports_everyone_complete(self):
        assert format_report([]) == "Everyone registered has filled in their year and major."

    def test_nonempty_list_names_each_competitor(self, db_path):
        conn = open_readonly(str(db_path))
        try:
            rows = fetch_incomplete_registrations(conn)
        finally:
            conn.close()

        report = format_report(rows)
        assert "1 competitor(s)" in report
        assert "Jane Doe" in report
        assert "<@1>" in report
        assert "john@uwaterloo.ca" not in report
