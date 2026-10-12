"""Paths to the bot's hand-edited content files, and a small reader for them."""

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
