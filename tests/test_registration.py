"""Tests for the registration DB logic (`cogs/registration.py`).

Current state: fully implemented — covers new vs. re-registration,
conflicting/case-insensitive email claims, malformed email rejection,
year/major upserts, and the modal's structure/pre-fill behavior.
TODO: none open.
Notes: the discord-free core (`upsert_competitor`, `upsert_profile`) is
covered against a real DB — role-granting and nickname-setting live in
discord.py objects that aren't worth mocking. `RegistrationModal` itself is
instantiated directly (no interaction needed) to check it builds a
well-formed Components V2 payload and pre-fills correctly; `on_submit`'s
discord-side calls aren't covered here.
"""

from __future__ import annotations

import pytest

from cogs.registration import (
    MAJOR_OPTIONS,
    YEAR_OPTIONS,
    RegistrationModal,
    upsert_competitor,
    upsert_profile,
)
from utils.errors import EmailAlreadyClaimed, InvalidEmail


async def add_competitor(db, discord_id: int, email: str, name: str = "Test User") -> None:
    await db.execute(
        "INSERT INTO competitors (discord_id, full_name, school_email) VALUES (?, ?, ?)",
        (discord_id, name, email),
    )


class TestUpsertCompetitor:
    async def test_first_registration_is_new(self, db):
        row, is_new = await upsert_competitor(db, 1, "Jane Doe", "jane@uwaterloo.ca")
        assert is_new is True
        assert row["full_name"] == "Jane Doe"
        assert row["school_email"] == "jane@uwaterloo.ca"
        assert row["registered_at"] is not None

    async def test_reregistration_by_same_account_updates_in_place(self, db):
        await upsert_competitor(db, 1, "Jane Doe", "jane@uwaterloo.ca")
        row, is_new = await upsert_competitor(db, 1, "Jane D. Doe", "jane.doe@uwaterloo.ca")

        assert is_new is False
        assert row["full_name"] == "Jane D. Doe"
        assert row["school_email"] == "jane.doe@uwaterloo.ca"

        count = await db.fetch_one("SELECT COUNT(*) AS n FROM competitors")
        assert count["n"] == 1

    async def test_email_claimed_by_different_account_is_rejected(self, db):
        await upsert_competitor(db, 1, "Jane Doe", "jane@uwaterloo.ca")
        with pytest.raises(EmailAlreadyClaimed):
            await upsert_competitor(db, 2, "John Doe", "jane@uwaterloo.ca")

    async def test_email_claim_check_is_case_insensitive(self, db):
        await upsert_competitor(db, 1, "Jane Doe", "jane@uwaterloo.ca")
        with pytest.raises(EmailAlreadyClaimed):
            await upsert_competitor(db, 2, "John Doe", "JANE@UWaterloo.ca")

    async def test_email_is_stored_lowercase(self, db):
        row, _ = await upsert_competitor(db, 1, "Jane Doe", "JANE@UWATERLOO.CA")
        assert row["school_email"] == "jane@uwaterloo.ca"

    async def test_inputs_are_stripped(self, db):
        row, _ = await upsert_competitor(db, 1, "  Jane Doe  ", "  jane@uwaterloo.ca  ")
        assert row["full_name"] == "Jane Doe"
        assert row["school_email"] == "jane@uwaterloo.ca"

    @pytest.mark.parametrize("bad_email", ["not-an-email", "missing-domain@", "@no-local.com", "no-tld@domain"])
    async def test_malformed_email_is_rejected(self, db, bad_email):
        with pytest.raises(InvalidEmail):
            await upsert_competitor(db, 1, "Jane Doe", bad_email)


class TestUpsertProfile:
    async def test_first_write_creates_the_row(self, db):
        await add_competitor(db, 1, "jane@uwaterloo.ca")
        row = await upsert_profile(db, 1, "Junior", "Computer Science")
        assert row["year"] == "Junior"
        assert row["major"] == "Computer Science"

    async def test_rerunning_updates_in_place(self, db):
        await add_competitor(db, 1, "jane@uwaterloo.ca")
        await upsert_profile(db, 1, "Junior", "Computer Science")
        row = await upsert_profile(db, 1, "Senior", "Harpur")

        assert row["year"] == "Senior"
        assert row["major"] == "Harpur"

        count = await db.fetch_one("SELECT COUNT(*) AS n FROM competitor_profiles")
        assert count["n"] == 1


class TestRegistrationModal:
    def test_email_placeholder_is_a_school_address(self):
        assert RegistrationModal.school_email.component.placeholder == "you@binghamton.edu"

    def test_top_level_component_count_is_within_discord_modal_limit(self):
        modal = RegistrationModal(bot=None)
        assert len(modal._children) <= 5

    def test_component_dicts_serialize_without_error(self):
        modal = RegistrationModal(bot=None)
        payloads = [child.to_component_dict() for child in modal._children]
        assert len(payloads) == len(modal._children)

    def test_year_and_major_options_match_the_configured_lists(self):
        modal = RegistrationModal(bot=None)
        assert [option.value for option in modal.year.component.options] == YEAR_OPTIONS
        assert [option.value for option in modal.major.component.options] == MAJOR_OPTIONS

    def test_prefills_name_and_email_from_an_existing_row(self):
        existing = {"full_name": "Jane Doe", "school_email": "jane@uwaterloo.ca"}
        modal = RegistrationModal(bot=None, existing=existing)
        assert modal.full_name.component.default == "Jane Doe"
        assert modal.school_email.component.default == "jane@uwaterloo.ca"

    def test_prefills_year_and_major_from_an_existing_profile(self):
        existing_profile = {"year": "Junior", "major": "Computer Science"}
        modal = RegistrationModal(bot=None, existing_profile=existing_profile)

        selected_year = [o.value for o in modal.year.component.options if o.default]
        selected_major = [o.value for o in modal.major.component.options if o.default]
        assert selected_year == ["Junior"]
        assert selected_major == ["Computer Science"]

    def test_no_prior_registration_leaves_nothing_preselected(self):
        modal = RegistrationModal(bot=None)
        assert modal.full_name.component.default is None
        assert not any(o.default for o in modal.year.component.options)
        assert not any(o.default for o in modal.major.component.options)
