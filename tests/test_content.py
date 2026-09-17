"""Tests for the content-file reader (`services/content.py`).

Current state: fully implemented.
TODO: none open.
Notes: uses pytest's `tmp_path` rather than the real `content/` files so
tests don't depend on their current wording.
"""

from __future__ import annotations

from services.content import CHANGELOG_PATH, DEFAULT_MESSAGE_PATH, read_content_file


class TestReadContentFile:
    def test_missing_file_returns_none(self, tmp_path):
        assert read_content_file(tmp_path / "does-not-exist.md") is None

    def test_existing_file_is_read_and_stripped(self, tmp_path):
        path = tmp_path / "message.md"
        path.write_text("  \nHello there.\n  \n", encoding="utf-8")
        assert read_content_file(path) == "Hello there."


class TestContentPaths:
    def test_paths_point_into_the_content_directory(self):
        assert CHANGELOG_PATH.parent == DEFAULT_MESSAGE_PATH.parent
        assert CHANGELOG_PATH.parent.name == "content"
