"""Ops helper: a snapshot of registration and team stats from the database.

Purpose: one report for officers — how many competitors are registered,
their year/major breakdown, and team sizes — without needing to touch the
bot process or write any SQL by hand.

Current state: fully implemented.
TODO: none open.
Notes: read-only connection details live in `scripts/_common.py`. Year and
major breakdowns are a plain `GROUP BY` over what's actually stored, not a
zero-filled list of `cogs.registration`'s current dropdown options — that
would make an offline report depend on the bot's UI module, and would
silently misreport if a competitor's stored value ever falls outside
whatever the current option list happens to be (e.g. after an option is
renamed) instead of surfacing it. Team counts use `COUNT(DISTINCT
discord_id)` rather than leaning on the one-team-per-competitor unique
index, so this stays correct if that constraint is ever relaxed (see
CLAUDE.md > Teams). Never prints `school_email` — same policy as the rest
of the codebase.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import add_db_argument, open_readonly  # noqa: E402


def collect_stats(conn: sqlite3.Connection) -> dict:
    """Gather registration and team stats into one plain dict."""
    total_competitors = conn.execute("SELECT COUNT(*) AS n FROM competitors").fetchone()["n"]
    with_profile = conn.execute("SELECT COUNT(*) AS n FROM competitor_profiles").fetchone()["n"]

    year_counts = [
        (row["year"], row["n"])
        for row in conn.execute(
            "SELECT year, COUNT(*) AS n FROM competitor_profiles GROUP BY year ORDER BY n DESC, year"
        )
    ]
    major_counts = [
        (row["major"], row["n"])
        for row in conn.execute(
            "SELECT major, COUNT(*) AS n FROM competitor_profiles GROUP BY major ORDER BY n DESC, major"
        )
    ]

    total_teams = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
    competitors_on_a_team = conn.execute(
        "SELECT COUNT(DISTINCT discord_id) AS n FROM team_members"
    ).fetchone()["n"]

    teams = [
        (row["name"], row["member_count"])
        for row in conn.execute(
            """
            SELECT teams.name, COUNT(team_members.discord_id) AS member_count
            FROM teams
            LEFT JOIN team_members ON team_members.team_id = teams.team_id
            GROUP BY teams.team_id
            ORDER BY member_count DESC, teams.name COLLATE NOCASE
            """
        )
    ]

    return {
        "total_competitors": total_competitors,
        "with_profile": with_profile,
        "missing_profile": total_competitors - with_profile,
        "year_counts": year_counts,
        "major_counts": major_counts,
        "total_teams": total_teams,
        "competitors_on_a_team": competitors_on_a_team,
        "competitors_without_team": total_competitors - competitors_on_a_team,
        "avg_team_size": (competitors_on_a_team / total_teams) if total_teams else 0.0,
        "teams": teams,
    }


def format_report(stats: dict) -> str:
    """Render the stats dict as a plain-text report."""
    lines = ["=== Registration ==="]
    lines.append(f"Total competitors: {stats['total_competitors']}")
    lines.append(f"  Year/major on file: {stats['with_profile']}")
    lines.append(f"  Still need to run /register: {stats['missing_profile']}")

    if stats["year_counts"]:
        lines.append("")
        lines.append("By year:")
        lines.extend(f"  {year}: {count}" for year, count in stats["year_counts"])

    if stats["major_counts"]:
        lines.append("")
        lines.append("By major:")
        lines.extend(f"  {major}: {count}" for major, count in stats["major_counts"])

    lines.append("")
    lines.append("=== Teams ===")
    lines.append(f"Total teams: {stats['total_teams']}")
    lines.append(f"Competitors on a team: {stats['competitors_on_a_team']}")
    lines.append(f"Competitors not on a team: {stats['competitors_without_team']}")
    lines.append(f"Average team size: {stats['avg_team_size']:.1f}")

    if stats["teams"]:
        lines.append("")
        lines.append("Team breakdown:")
        lines.extend(
            f"  {name}: {count} member{'s' if count != 1 else ''}" for name, count in stats["teams"]
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_db_argument(parser)
    args = parser.parse_args()

    conn = open_readonly(args.db)
    try:
        stats = collect_stats(conn)
    finally:
        conn.close()

    print(format_report(stats))


if __name__ == "__main__":
    main()
