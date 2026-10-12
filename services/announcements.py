"""Startup/shutdown announcement content and changelog-freshness detection."""

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
    color: int  # plain 0xRRGGBB int, not discord.Color, to keep this module discord.py-free


def is_release(heading: str) -> bool:
    """Whether a changelog heading is an actual release, not the WIP `Unreleased` bucket."""
    return heading != UNRELEASED_HEADING


def parse_latest_entry(changelog_text: str) -> tuple[str, str] | None:
    """Return (heading, body) for CHANGELOG.md's first *released* `##` section, or None."""
    matches = list(_HEADING_RE.finditer(changelog_text))
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        # `## Unreleased` sits on top by convention and is never itself announceable.
        if not is_release(heading):
            continue

        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(changelog_text)
        return heading, changelog_text[body_start:body_end].strip()

    return None


def should_announce(heading: str, last_announced: str | None) -> bool:
    """Whether a changelog entry hasn't already been posted on startup."""
    # Compared on heading text alone, not a hash of the body, so this fires
    # exactly once — on the deploy right after a version bump.
    return heading != last_announced


def startup_announcement(heading: str | None, body: str | None) -> Announcement:
    """Content for the bot-online embed, with a changelog section if there's a new one."""
    description = f"**What's New — {heading}**\n\n{body}" if heading and body else None
    return Announcement(title="WCRL Bot Is Online 🟢", description=description, color=ONLINE_COLOR)


def shutdown_announcement() -> Announcement:
    """Content for the bot-offline embed."""
    return Announcement(title="WCRL Bot Is Offline 🔴", description=None, color=OFFLINE_COLOR)
