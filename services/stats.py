"""Registration and team stats — the data behind `cogs/stats.py`'s `/data`.

Purpose: gather the same numbers `scripts/db_stats.py` reports for a
maintainer with shell access, but through the bot's own live connection so
officers can pull them from Discord.

Current state: fully implemented.
TODO: none open.
Notes: mirrors the same figures as `scripts/db_stats.py::collect_stats`
rather than sharing code with it — that script intentionally never touches
`db.connection.Database` (its whole point is a connection that provably
cannot write, even accidentally, via `apply_schema()`'s replay), while this
module exists specifically to run inside the bot's event loop against its
one shared `aiosqlite` connection. Both now build their numbers from
`CompetitorRepository`/`TeamRepository` and plain SQL respectively — keep
them in sync by hand if the shape of the stats changes. `discord-free` —
`cogs/stats.py` is what turns this dict into an embed.
"""

from __future__ import annotations

from wcrl_db import Database


async def collect_stats(db: Database) -> dict:
    """Gather registration and team stats into one plain dict."""
    total_competitors = await db.competitors.count()
    with_profile = await db.competitors.count_with_profile()
    year_counts = await db.competitors.count_by_year()
    major_counts = await db.competitors.count_by_major()

    total_teams = await db.teams.count()
    competitors_on_a_team = await db.teams.count_distinct_members()
    teams = [
        (row["name"], row["member_count"])
        for row in await db.teams.list_with_member_counts(order="size")
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
