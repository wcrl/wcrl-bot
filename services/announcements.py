"""Startup/shutdown announcement content and changelog-freshness detection.

Purpose: everything the bot needs to decide *what* to post to the
announcement channel on connect/disconnect — kept discord-free so it's
testable without a running bot, per CLAUDE.md's `services/` convention.
Returns plain data (`Announcement`); `bot.py` turns that into a
`discord.Embed` so the message reads as an official post rather than a
plain chat line.

Current state: fully implemented — changelog parsing, the WIP-vs-release
distinction, the "is this entry new" comparison, and the two `Announcement`
builders.
TODO: none open.
Notes: CHANGELOG.md follows Keep a Changelog style: a `## Unreleased`
heading sits at the very top and accumulates changes across as many
deploys as it takes, so it's *not* what should be announced — a bump keeps
it on top (fresh and empty) and inserts the newly-named `## vX.Y` section
right below it. `parse_latest_entry` therefore skips a leading `Unreleased`
heading and returns the first *versioned* `##` section instead (still just
one section — everything from the next `##` heading, or EOF, onward is
ignored; `###` subheadings are included in the body). `is_release()` is a
plain predicate over a heading string, exported mainly so callers/tests
don't have to hardcode the sentinel. Freshness (`should_announce`) is
compared on heading text alone, not a hash of the body, so that
announcement fires once, on the deploy right after a bump. `color` is a
plain int (0xRRGGBB), not a `discord.Color`, to keep this module
import-free of discord.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

UNRELEASED_HEADING = "Unreleased"

ONLINE_COLOR = 0x57F287  # Discord's "green"
OFFLINE_COLOR = 0xED4245  # Discord's "red"


@dataclass(frozen=True)
class Announcement:
    """Content for one embed the bot posts to the announcement channel."""

    title: str
    description: str | None
    color: int


def is_release(heading: str) -> bool:
    """Whether a changelog heading is an actual release, not the WIP `Unreleased` bucket."""
    return heading != UNRELEASED_HEADING


def parse_latest_entry(changelog_text: str) -> tuple[str, str] | None:
    """Return (heading, body) for CHANGELOG.md's first *released* `##` section, or None.

    Skips a leading `## Unreleased` heading — that bucket sits on top by
    convention and is never itself announceable.
    """
    matches = list(_HEADING_RE.finditer(changelog_text))
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        if not is_release(heading):
            continue

        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(changelog_text)
        return heading, changelog_text[body_start:body_end].strip()

    return None


def should_announce(heading: str, last_announced: str | None) -> bool:
    """Whether a changelog entry hasn't already been posted on startup."""
    return heading != last_announced


def startup_announcement(heading: str | None, body: str | None) -> Announcement:
    """Content for the bot-online embed, with a changelog section if there's a new one."""
    description = f"**What's New — {heading}**\n\n{body}" if heading and body else None
    return Announcement(title="WCRL Bot Is Online 🟢", description=description, color=ONLINE_COLOR)


def shutdown_announcement() -> Announcement:
    """Content for the bot-offline embed."""
    return Announcement(title="WCRL Bot Is Offline 🔴", description=None, color=OFFLINE_COLOR)
