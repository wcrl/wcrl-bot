"""Tests for team name rules and the DB-only team lookups (`cogs/teams.py`).

Current state: fully implemented — covers the normalize/slugify/validate
name helpers, the team_for_member/team_by_name/team_by_channel lookups, the
team-name autocomplete, and disband_team's DB teardown (with a fake guild so
the role/channel deletes are no-ops).
TODO: none open.
Notes: command bodies that touch discord.py objects (role/channel creation,
member management, the EmptyTeamView button) aren't covered here — see
`services/roles.py` as that boundary.
"""

from __future__ import annotations

import pytest

from cogs.teams import (
    disband_team,
    normalize_team_name,
    slugify_team_name,
    team_by_channel,
    team_by_name,
    team_for_member,
    team_name_autocomplete,
    validate_team_name,
)
from utils.errors import InvalidTeamName


class FakeConfig:
    officer_role_id = 1
    team_category_id = 2


class FakeBot:
    def __init__(self, db) -> None:
        self.db = db
        self.config = FakeConfig()


class FakeInteraction:
    def __init__(self, bot) -> None:
        self.client = bot


class FakeGuild:
    """A guild where every role/channel lookup misses — disband_team then only touches the DB."""

    def get_role(self, _role_id):
        return None

    def get_channel(self, _channel_id):
        return None


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

    async def test_team_by_channel_finds_the_right_team(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)

        team = await team_by_channel(db, 2001)  # add_team sets channel_id = 2000 + team_id
        assert team is not None
        assert team["name"] == "Alpha"

    async def test_team_by_channel_returns_none_when_missing(self, db):
        assert await team_by_channel(db, 9999) is None


class TestTeamNameAutocomplete:
    async def _choices(self, db, current):
        return await team_name_autocomplete(FakeInteraction(FakeBot(db)), current)

    async def test_suggests_names_matching_the_typed_fragment(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Bot Squad", owner=1)
        await add_team(db, 2, "Circuit Breakers", owner=1)

        choices = await self._choices(db, "bot")
        assert [c.value for c in choices] == ["Bot Squad"]

    async def test_empty_fragment_lists_every_team(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        await add_team(db, 2, "Beta", owner=1)

        choices = await self._choices(db, "")
        assert sorted(c.value for c in choices) == ["Alpha", "Beta"]

    async def test_like_wildcards_are_matched_literally(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Bot Squad", owner=1)

        assert await self._choices(db, "%") == []


class TestDisbandTeam:
    async def test_deletes_the_team_and_cascades_its_members(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 1)")

        team = await team_by_name(db, "Alpha")
        await disband_team(FakeBot(db), FakeGuild(), team)

        assert await team_by_name(db, "Alpha") is None
        assert await db.fetch_all("SELECT * FROM team_members WHERE team_id = 1") == []
