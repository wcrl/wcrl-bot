"""Paths to the bot's hand-edited content files, and a small reader for them.

Purpose: single place defining where `content/CHANGELOG.md` and
`content/DEFAULT_MESSAGE.md` live, so `bot.py` and `cogs/teams.py` don't
each hardcode a path.

Current state: fully implemented.
TODO: none open.
Notes: both files are plain markdown meant to be edited without a code
change. See CLAUDE.md > Changelog & Versioning for how CHANGELOG.md is
maintained; DEFAULT_MESSAGE.md is posted verbatim (no templating) to a
team's channel when it's created.
"""

from __future__ import annotations

from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
CHANGELOG_PATH = CONTENT_DIR / "CHANGELOG.md"
DEFAULT_MESSAGE_PATH = CONTENT_DIR / "DEFAULT_MESSAGE.md"


def read_content_file(path: Path) -> str | None:
    """Return a content file's stripped text, or None if it doesn't exist."""
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()
