"""Registration and team stats — the data behind `cogs/stats.py`'s `/data`.

Purpose: gather the same numbers `scripts/db_stats.py` reports for a
maintainer with shell access, but through the bot's own live connection so
officers can pull them from Discord.

Current state: fully implemented.
TODO: none open.
Notes: the SQL here deliberately mirrors `scripts/db_stats.py::collect_stats`
rather than sharing code with it — that script intentionally never touches
`db.connection.Database` (its whole point is a connection that provably
cannot write, even accidentally, via `apply_schema()`'s replay), while this
module exists specifically to run inside the bot's event loop against its
one shared `aiosqlite` connection. Keep the two in sync by hand if the
shape of the stats changes. `discord-free` — `cogs/stats.py` is what turns
this dict into an embed.
"""

from __future__ import annotations

from db.connection import Database


async def collect_stats(db: Database) -> dict:
    """Gather registration and team stats into one plain dict."""
    total_competitors = (await db.fetch_one("SELECT COUNT(*) AS n FROM competitors"))["n"]
    with_profile = (await db.fetch_one("SELECT COUNT(*) AS n FROM competitor_profiles"))["n"]

    year_counts = [
        (row["year"], row["n"])
        for row in await db.fetch_all(
            "SELECT year, COUNT(*) AS n FROM competitor_profiles GROUP BY year ORDER BY n DESC, year"
        )
    ]
    major_counts = [
        (row["major"], row["n"])
        for row in await db.fetch_all(
            "SELECT major, COUNT(*) AS n FROM competitor_profiles GROUP BY major ORDER BY n DESC, major"
        )
    ]

    total_teams = (await db.fetch_one("SELECT COUNT(*) AS n FROM teams"))["n"]
    competitors_on_a_team = (
        await db.fetch_one("SELECT COUNT(DISTINCT discord_id) AS n FROM team_members")
    )["n"]

    teams = [
        (row["name"], row["member_count"])
        for row in await db.fetch_all(
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
