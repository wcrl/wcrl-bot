"""Tests for the registration DB logic (`cogs/registration.py`).

Current state: fully implemented — covers new vs. re-registration,
conflicting/case-insensitive email claims, and malformed email rejection.
TODO: none open.
Notes: only the discord-free core (`upsert_competitor`) is covered — the
modal and role-granting live in discord.py objects that aren't worth
mocking; the DB behavior they depend on is what's tested.
"""

from __future__ import annotations

import pytest

from cogs.registration import RegistrationModal, upsert_competitor
from utils.errors import EmailAlreadyClaimed, InvalidEmail


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


class TestRegistrationModal:
    def test_email_placeholder_is_a_school_address(self):
        assert RegistrationModal.school_email.placeholder == "you@binghamton.edu"
