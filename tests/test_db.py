"""Schema constraint tests — the invariants the command logic leans on.

Current state: fully implemented, covers competitors/teams/team_members.
TODO: none open.
Notes: none.
"""

from __future__ import annotations

import aiosqlite
import pytest


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


class TestCompetitors:
    async def test_email_is_unique_across_accounts(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        with pytest.raises(aiosqlite.IntegrityError):
            await add_competitor(db, 2, "a@uwaterloo.ca")

    async def test_email_uniqueness_is_case_insensitive(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        with pytest.raises(aiosqlite.IntegrityError):
            await add_competitor(db, 2, "A@UWaterloo.ca")

    async def test_reregistering_same_account_updates_in_place(self, db):
        await add_competitor(db, 1, "old@uwaterloo.ca", "Old Name")
        await db.execute(
            """
            INSERT INTO competitors (discord_id, full_name, school_email) VALUES (?, ?, ?)
            ON CONFLICT (discord_id) DO UPDATE
                SET full_name = excluded.full_name, school_email = excluded.school_email
            """,
            (1, "New Name", "new@uwaterloo.ca"),
        )
        row = await db.fetch_one("SELECT * FROM competitors WHERE discord_id = 1")
        assert row["full_name"] == "New Name"
        assert row["school_email"] == "new@uwaterloo.ca"

        count = await db.fetch_one("SELECT COUNT(*) AS n FROM competitors")
        assert count["n"] == 1


class TestTeams:
    async def test_normalized_name_is_unique(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Bot Squad", owner=1)
        with pytest.raises(aiosqlite.IntegrityError):
            await add_team(db, 2, "bot squad", owner=1)

    async def test_role_and_channel_ids_are_unique(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """
                INSERT INTO teams (name, name_normalized, role_id, channel_id, created_by)
                VALUES ('Beta', 'beta', 1001, 9999, 1)
                """
            )

    async def test_created_by_must_be_a_competitor(self, db):
        with pytest.raises(aiosqlite.IntegrityError):
            await add_team(db, 1, "Ghost Team", owner=404)


class TestTeamMembers:
    async def test_competitor_can_only_be_on_one_team(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        await add_team(db, 2, "Beta", owner=1)

        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 1)")
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (2, 1)")

    async def test_disband_cascades_to_members(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await add_competitor(db, 2, "b@uwaterloo.ca")
        await add_team(db, 1, "Alpha", owner=1)
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 1)")
        await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (1, 2)")

        await db.execute("DELETE FROM teams WHERE team_id = 1")

        remaining = await db.fetch_all("SELECT * FROM team_members")
        assert remaining == []
        # Competitors outlive their team.
        assert len(await db.fetch_all("SELECT * FROM competitors")) == 2

    async def test_membership_requires_an_existing_team(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute("INSERT INTO team_members (team_id, discord_id) VALUES (99, 1)")


class TestCompetitorProfiles:
    async def test_profile_requires_an_existing_competitor(self, db):
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (99, 'Junior', 'Computer Science')"
            )

    async def test_competitor_can_have_at_most_one_profile_row(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await db.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (1, 'Junior', 'Computer Science')"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (1, 'Senior', 'Harpur')"
            )

    async def test_deleting_competitor_cascades_to_profile(self, db):
        await add_competitor(db, 1, "a@uwaterloo.ca")
        await db.execute(
            "INSERT INTO competitor_profiles (discord_id, year, major) VALUES (1, 'Junior', 'Computer Science')"
        )
        await db.execute("DELETE FROM competitors WHERE discord_id = 1")
        assert await db.fetch_all("SELECT * FROM competitor_profiles") == []


class TestBotState:
    async def test_key_is_unique(self, db):
        await db.execute(
            "INSERT INTO bot_state (key, value) VALUES ('last_announced_changelog', 'v1')"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO bot_state (key, value) VALUES ('last_announced_changelog', 'v2')"
            )

    async def test_value_can_be_updated_via_upsert(self, db):
        await db.execute(
            "INSERT INTO bot_state (key, value) VALUES ('last_announced_changelog', 'v1')"
        )
        await db.execute(
            """
            INSERT INTO bot_state (key, value) VALUES ('last_announced_changelog', 'v2')
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """
        )
        row = await db.fetch_one(
            "SELECT value FROM bot_state WHERE key = 'last_announced_changelog'"
        )
        assert row["value"] == "v2"
