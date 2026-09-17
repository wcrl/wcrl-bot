"""Tests for changelog parsing and announcement content (`services/announcements.py`).

Current state: fully implemented — covers changelog parsing (single/multiple
entries, subheadings, no heading, skipping a leading `Unreleased` bucket),
the freshness comparison, and both `Announcement` builders.
TODO: none open.
Notes: pure functions only, no discord.py or DB involved — `bot.py` is what
turns an `Announcement` into a `discord.Embed`.
"""

from __future__ import annotations

from services.announcements import (
    Announcement,
    is_release,
    parse_latest_entry,
    should_announce,
    shutdown_announcement,
    startup_announcement,
)


class TestParseLatestEntry:
    def test_single_entry(self):
        text = "# Changelog\n\n## v1.0\n### Registration\n- added a thing\n- fixed a bug\n"
        heading, body = parse_latest_entry(text)
        assert heading == "v1.0"
        assert body == "### Registration\n- added a thing\n- fixed a bug"

    def test_only_the_first_entry_is_returned(self):
        text = "## v1.1\n- newest\n\n## v1.0\n- oldest\n"
        heading, body = parse_latest_entry(text)
        assert heading == "v1.1"
        assert body == "- newest"

    def test_no_heading_returns_none(self):
        assert parse_latest_entry("# Changelog\n\nNothing here yet.\n") is None

    def test_empty_body_is_an_empty_string(self):
        text = "## v1.1\n\n## v1.0\n- old\n"
        heading, body = parse_latest_entry(text)
        assert heading == "v1.1"
        assert body == ""

    def test_skips_a_leading_unreleased_heading(self):
        text = "## Unreleased\n- wip stuff\n\n## v1.0\n- shipped stuff\n"
        heading, body = parse_latest_entry(text)
        assert heading == "v1.0"
        assert body == "- shipped stuff"

    def test_empty_unreleased_bucket_does_not_hide_the_release_below(self):
        # The exact shape right after a bump: a fresh, empty Unreleased on
        # top of the just-renamed version section.
        text = "## Unreleased\n\n## v1.0\n### Registration\n- a feature\n"
        heading, body = parse_latest_entry(text)
        assert heading == "v1.0"
        assert body == "### Registration\n- a feature"

    def test_only_unreleased_present_returns_none(self):
        assert parse_latest_entry("## Unreleased\n- wip stuff\n") is None


class TestIsRelease:
    def test_unreleased_bucket_is_not_a_release(self):
        assert is_release("Unreleased") is False

    def test_a_version_heading_is_a_release(self):
        assert is_release("v1.0") is True


class TestShouldAnnounce:
    def test_new_heading_should_announce(self):
        assert should_announce("v1.1", "v1.0") is True

    def test_unchanged_heading_should_not_announce(self):
        assert should_announce("v1.0", "v1.0") is False

    def test_no_prior_announcement_should_announce(self):
        assert should_announce("v1.0", None) is True


class TestStartupAnnouncement:
    def test_title_is_title_case_with_a_trailing_emoji(self):
        announcement = startup_announcement(None, None)
        assert announcement.title == "WCRL Bot Is Online 🟢"
        assert not announcement.title.startswith("🟢")

    def test_without_changelog_has_no_description(self):
        announcement = startup_announcement(None, None)
        assert announcement.description is None

    def test_with_changelog_includes_heading_and_body(self):
        announcement = startup_announcement("v1.0", "- added a thing")
        assert "v1.0" in announcement.description
        assert "- added a thing" in announcement.description

    def test_is_an_announcement_instance(self):
        assert isinstance(startup_announcement(None, None), Announcement)


class TestShutdownAnnouncement:
    def test_title_is_title_case_with_a_trailing_emoji(self):
        announcement = shutdown_announcement()
        assert announcement.title == "WCRL Bot Is Offline 🔴"
        assert not announcement.title.startswith("🔴")

    def test_has_no_description(self):
        assert shutdown_announcement().description is None
