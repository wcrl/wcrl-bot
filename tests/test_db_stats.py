"""Tests for `scripts/db_stats.py`.

Current state: fully implemented — covers an empty database, a populated
one (registration + team breakdowns), and the report text.
TODO: none open.
Notes: uses a real on-disk SQLite file (`tmp_path`), same reasoning as
`tests/test_scripts.py` — `open_readonly`'s `mode=ro` URI needs an actual
file to attach to.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts._common import open_readonly
from scripts.db_stats import collect_stats, format_report

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def make_db(tmp_path, name: str = "wcrl.db") -> Path:
    path = tmp_path / name
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


class TestCollectStatsEmpty:
    def test_empty_database_has_zeroed_stats(self, tmp_path):
        conn = open_readonly(str(make_db(tmp_path)))
        try:
            stats = collect_stats(conn)
        finally:
            conn.close()

        assert stats["total_competitors"] == 0
        assert stats["with_profile"] == 0
        assert stats["missing_profile"] == 0
        assert stats["year_counts"] == []
        assert stats["major_counts"] == []
        assert stats["total_teams"] == 0
        assert stats["competitors_on_a_team"] == 0
        assert stats["competitors_without_team"] == 0
        assert stats["avg_team_size"] == 0.0
        assert stats["teams"] == []


class TestCollectStatsPopulated:
    @pytest.fixture
    def stats(self, tmp_path):
        path = make_db(tmp_path)
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            INSERT INTO competitors (discord_id, full_name, school_email) VALUES
                (1, 'A', 'a@x.edu'), (2, 'B', 'b@x.edu'), (3, 'C', 'c@x.edu');

            INSERT INTO competitor_profiles (discord_id, year, major) VALUES
                (1, 'Junior', 'Computer Science'),
                (2, 'Junior', 'Computer Science'),
                (3, 'Senior', 'Harpur');

            INSERT INTO teams (team_id, name, name_normalized, role_id, channel_id, created_by)
                VALUES (1, 'Alpha', 'alpha', 100, 200, 1);
            INSERT INTO team_members (team_id, discord_id) VALUES (1, 1), (1, 2);
            """
        )
        conn.commit()
        conn.close()

        conn = open_readonly(str(path))
        try:
            yield collect_stats(conn)
        finally:
            conn.close()

    def test_registration_totals(self, stats):
        assert stats["total_competitors"] == 3
        assert stats["with_profile"] == 3
        assert stats["missing_profile"] == 0

    def test_year_and_major_breakdowns(self, stats):
        assert dict(stats["year_counts"]) == {"Junior": 2, "Senior": 1}
        assert dict(stats["major_counts"]) == {"Computer Science": 2, "Harpur": 1}

    def test_team_totals(self, stats):
        assert stats["total_teams"] == 1
        assert stats["competitors_on_a_team"] == 2
        assert stats["competitors_without_team"] == 1
        assert stats["avg_team_size"] == 2.0
        assert stats["teams"] == [("Alpha", 2)]


class TestFormatReport:
    def test_report_includes_key_numbers(self, tmp_path):
        conn = open_readonly(str(make_db(tmp_path)))
        try:
            stats = collect_stats(conn)
        finally:
            conn.close()

        report = format_report(stats)
        assert "Total competitors: 0" in report
        assert "Total teams: 0" in report
        assert "school_email" not in report
