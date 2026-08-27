"""Tests for team name rules and the DB-only team lookups (`cogs/teams.py`).

Current state: fully implemented — covers the normalize/slugify/validate
name helpers and the team_for_member/team_by_name lookups.
TODO: none open.
Notes: command bodies that touch discord.py objects (role/channel creation,
member management) aren't covered here — see `services/roles.py` as that
boundary.
"""

from __future__ import annotations

import pytest

from cogs.teams import (
    normalize_team_name,
    slugify_team_name,
    team_by_name,
    team_for_member,
    validate_team_name,
)
from utils.errors import InvalidTeamName


async def add_competitor(db, discord_id: int, email: str) -> None:
    await db.execute(
        "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (?, ?, ?)",
        (discord_id, "Test User", email),
    )


async def add_team(db, team_id: int, name: str, owner: int) -> None:
    await db.execute(
        """
        INSERT INTO teams (team_id, name, name_normalized, role_id, channel_id, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (team_id, name, normalize_team_name(name), 1000 + team_id, 2000 + team_id, owner),
    )


class TestNormalizeTeamName:
    def test_collapses_whitespace_and_casefolds(self):
        assert normalize_team_name("Bot   Squad") == "bot squad"
        assert normalize_team_name("bot squad") == "bot squad"

    def test_different_names_do_not_collide(self):
        assert normalize_team_name("Bot Squad") != normalize_team_name("Bot Squad 2")


class TestSlugifyTeamName:
    def test_replaces_non_alphanumerics_with_hyphens(self):
        assert slugify_team_name("Bot Squad!") == "bot-squad"

    def test_strips_leading_and_trailing_hyphens(self):
        assert slugify_team_name("__Bot Squad__") == "bot-squad"

    def test_truncates_to_90_chars(self):
        assert len(slugify_team_name("a" * 200)) == 90


class TestValidateTeamName:
    def test_accepts_a_normal_name(self):
        assert validate_team_name("Bot Squad") == "Bot Squad"

    def test_collapses_internal_whitespace(self):
        assert validate_team_name("Bot   Squad") == "Bot Squad"

    @pytest.mark.parametrize("name", ["ab", "a" * 33, "!!!", "   "])
    def test_rejects_invalid_names(self, name):
        with pytest.raises(InvalidTeamName):
            validate_team_name(name)


class TestTeamLookups:
    async def test_team_for_member_returns_none_when_unassigned(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        assert await team_for_member(db, 1) is None

    async def test_team_for_member_finds_the_right_team(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 1)")

        team = await team_for_member(db, 1)
        assert team is not None
        assert team["name"] == "Alpha"

    async def test_team_by_name_is_case_and_whitespace_insensitive(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Bot Squad", owner=1)

        assert (await team_by_name(db, "bot   squad"))["team_id"] == 1
        assert (await team_by_name(db, "BOT SQUAD"))["team_id"] == 1

    async def test_team_by_name_returns_none_when_missing(self, db):
        assert await team_by_name(db, "Nonexistent") is None
