"""Tests for `services/stats.py` and the `/data` embed (`cogs/stats.py`).

Current state: fully implemented — covers an empty database, a populated
one (registration + team breakdowns, derived arithmetic), and the embed's
field structure including the team-breakdown truncation.
TODO: none open.
Notes: `collect_stats` is tested against the real `db` fixture (aiosqlite,
schema applied), same as `cogs/registration.py`'s and `cogs/teams.py`'s
DB-touching helpers. `build_stats_embed` is a pure function over a plain
dict, so it's tested directly without a live bot or interaction, same
approach as `RegistrationModal` in `tests/test_registration.py`.
"""

from __future__ import annotations

from cogs.stats import TEAM_BREAKDOWN_LIMIT, build_stats_embed
from services.stats import collect_stats


async def add_competitor(db, discord_id: int, email: str, name: str = "Test User") -> None:
    await db.execute(
        "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (?, ?, ?)",
        (discord_id, name, email),
    )


async def add_team(db, team_id: int, name: str, owner: int) -> None:
    await db.execute(
        """
        INSERT INTO teams (team_id, name, name_normalized, role_id, channel_id, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (team_id, name, name.casefold(), 1000 + team_id, 2000 + team_id, owner),
    )


class TestCollectStatsEmpty:
    async def test_empty_database_has_zeroed_stats(self, db):
        stats = await collect_stats(db)

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
    async def _seed(self, db):
        for discord_id, name in [(1, "A"), (2, "B"), (3, "C")]:
            await add_competitor(db, discord_id, f"{name.lower()}@x.edu", name)
        await db.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (1, 'Junior', 'Computer Science')"
        )
        await db.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (2, 'Junior', 'Computer Science')"
        )
        await db.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (3, 'Senior', 'Harpur')"
        )
        await add_team(db, 1, "Alpha", owner=1)
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 1)")
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 2)")

    async def test_registration_totals(self, db):
        await self._seed(db)
        stats = await collect_stats(db)
        assert stats["total_competitors"] == 3
        assert stats["with_profile"] == 3
        assert stats["missing_profile"] == 0

    async def test_year_and_major_breakdowns(self, db):
        await self._seed(db)
        stats = await collect_stats(db)
        assert dict(stats["year_counts"]) == {"Junior": 2, "Senior": 1}
        assert dict(stats["major_counts"]) == {"Computer Science": 2, "Harpur": 1}

    async def test_team_totals_and_derived_arithmetic(self, db):
        await self._seed(db)
        stats = await collect_stats(db)
        assert stats["total_teams"] == 1
        assert stats["competitors_on_a_team"] == 2
        assert stats["competitors_without_team"] == 1
        assert stats["avg_team_size"] == 2.0
        assert stats["teams"] == [("Alpha", 2)]


class TestBuildStatsEmbed:
    def _empty_stats(self) -> dict:
        return {
            "total_competitors": 0,
            "with_profile": 0,
            "missing_profile": 0,
            "year_counts": [],
            "major_counts": [],
            "total_teams": 0,
            "competitors_on_a_team": 0,
            "competitors_without_team": 0,
            "avg_team_size": 0.0,
            "teams": [],
        }

    def test_always_has_a_registration_and_teams_field(self):
        embed = build_stats_embed(self._empty_stats())
        field_names = [field.name for field in embed.fields]
        assert "Registration" in field_names
        assert "Teams" in field_names

    def test_omits_breakdown_fields_when_empty(self):
        embed = build_stats_embed(self._empty_stats())
        field_names = [field.name for field in embed.fields]
        assert "By Year" not in field_names
        assert "By Major" not in field_names
        assert "Team Breakdown" not in field_names

    def test_includes_breakdown_fields_when_present(self):
        stats = self._empty_stats()
        stats["year_counts"] = [("Junior", 2)]
        stats["major_counts"] = [("Computer Science", 2)]
        stats["teams"] = [("Alpha", 2)]

        embed = build_stats_embed(stats)
        fields = {field.name: field.value for field in embed.fields}
        assert "Junior" in fields["By Year"]
        assert "Computer Science" in fields["By Major"]
        assert "Alpha" in fields["Team Breakdown"]

    def test_team_breakdown_is_truncated_with_a_remainder_note(self):
        stats = self._empty_stats()
        stats["teams"] = [(f"Team {i}", 1) for i in range(TEAM_BREAKDOWN_LIMIT + 5)]

        embed = build_stats_embed(stats)
        field = next(f for f in embed.fields if f.name == "Team Breakdown")
        assert field.value.count("Team ") == TEAM_BREAKDOWN_LIMIT
        assert "…and 5 more" in field.value
